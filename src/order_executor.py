"""
order_executor.py

승인된 주문을 실행하는 주문 실행 계층.

현재 지원:
- DRY RUN 주문 실행
- 주문 상태 전이
- 실행 결과 저장
- 중복 실행 방지
- 실행 로그 기록

현재 미지원:
- Toss Securities 실제 주문 API 호출

실행 흐름:
APPROVED
    -> EXECUTING
    -> DRY_RUN_EXECUTED

실패 흐름:
APPROVED
    -> EXECUTING
    -> FAILED / REJECTED / TIMEOUT
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from order_store import (
    DEFAULT_DB_PATH,
    InvalidStatusTransitionError,
    OrderConflictError,
    OrderNotFoundError,
    OrderStatus,
    complete_order_execution,
    get_approved_orders,
    get_order,
    mark_order_executing,
    normalize_status,
)


LOG_PATH = Path(__file__).resolve().parent / "executor.log"


def configure_logger() -> logging.Logger:
    """
    Executor 전용 로거를 구성한다.

    동일 모듈이 여러 번 import되어도 핸들러가 중복 추가되지 않도록 한다.
    """

    logger = logging.getLogger("order_executor")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    file_handler = logging.FileHandler(
        LOG_PATH,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    return logger


logger = configure_logger()


class ExecutionMode(str, Enum):
    """주문 실행 방식."""

    DRY_RUN = "DRY_RUN"
    REAL = "REAL"


class ExecutionError(Exception):
    """주문 실행 계층의 기본 예외."""


class UnsupportedExecutionModeError(ExecutionError):
    """아직 지원하지 않는 실행 모드를 호출했을 때 발생."""


class OrderNotExecutableError(ExecutionError):
    """현재 상태상 실행할 수 없는 주문일 때 발생."""


class BrokerRejectedError(ExecutionError):
    """증권사가 주문을 거절했을 때 사용할 예외."""


class BrokerTimeoutError(ExecutionError):
    """증권사 API 호출이 시간 초과됐을 때 사용할 예외."""


@dataclass
class BrokerExecutionResponse:
    """
    브로커 어댑터가 반환하는 표준 실행 응답.

    향후 Toss API 응답도 이 객체로 변환한다.
    """

    success: bool
    broker_order_id: str | None
    executed_price: float | None
    executed_quantity: float | None
    message: str
    raw_response: dict[str, Any] | None = None


@dataclass
class ExecutionResult:
    """외부에 반환하는 주문 실행 결과."""

    success: bool
    order_id: str
    mode: ExecutionMode
    status: OrderStatus
    broker_order_id: str | None
    executed_price: float | None
    executed_quantity: float | None
    message: str
    order: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON 응답에 적합한 딕셔너리로 변환한다."""

        result = asdict(self)
        result["mode"] = self.mode.value
        result["status"] = self.status.value
        return result


class BrokerAdapter(Protocol):
    """
    주문 실행 브로커의 인터페이스.

    나중에 TossBrokerAdapter를 구현하면 Executor 로직을
    수정하지 않고 실제 주문 기능을 연결할 수 있다.
    """

    def execute(
        self,
        order: dict[str, Any],
    ) -> BrokerExecutionResponse:
        """주문을 실행하고 표준 응답을 반환한다."""


class DryRunBrokerAdapter:
    """실제 주문을 전송하지 않는 DRY RUN 브로커."""

    def execute(
        self,
        order: dict[str, Any],
    ) -> BrokerExecutionResponse:
        """
        주문을 가상으로 실행한다.

        실제 시세 조회나 체결 시뮬레이션은 하지 않는다.
        """

        broker_order_id = f"DRY-{uuid.uuid4()}"

        quantity = float(order["quantity"])

        executed_price: float | None = None

        if order["order_type"] == "LIMIT":
            limit_price = order.get("limit_price")

            if limit_price is not None:
                executed_price = float(limit_price)

        return BrokerExecutionResponse(
            success=True,
            broker_order_id=broker_order_id,
            executed_price=executed_price,
            executed_quantity=quantity,
            message="DRY RUN 주문 실행이 완료되었습니다.",
            raw_response={
                "simulated": True,
                "symbol": order["symbol"],
                "side": order["side"],
                "quantity": quantity,
                "order_type": order["order_type"],
                "limit_price": order.get("limit_price"),
            },
        )


class RealBrokerAdapter:
    """
    실제 주문용 브로커 자리표시자.

    Toss 주문 API가 연결되기 전까지는 반드시 실패한다.
    """

    def execute(
        self,
        order: dict[str, Any],
    ) -> BrokerExecutionResponse:
        raise UnsupportedExecutionModeError(
            "REAL 주문 실행은 아직 구현되지 않았습니다. "
            "현재는 DRY_RUN만 사용할 수 있습니다."
        )


class OrderExecutor:
    """승인된 주문을 실행하는 서비스 클래스."""

    def __init__(
        self,
        db_path: str | Path = DEFAULT_DB_PATH,
        dry_run_adapter: BrokerAdapter | None = None,
        real_adapter: BrokerAdapter | None = None,
    ) -> None:
        self.db_path = db_path
        self.dry_run_adapter = (
            dry_run_adapter or DryRunBrokerAdapter()
        )
        self.real_adapter = real_adapter or RealBrokerAdapter()

    def execute_order(
        self,
        order_id: str,
        mode: ExecutionMode | str = ExecutionMode.DRY_RUN,
    ) -> ExecutionResult:
        """
        승인된 주문 한 건을 실행한다.

        1. 주문 조회
        2. APPROVED 상태 확인
        3. EXECUTING 상태로 원자적 변경
        4. 브로커 실행
        5. 최종 상태 및 결과 저장
        """

        normalized_mode = self._normalize_mode(mode)

        logger.info(
            "ORDER_EXECUTION_REQUEST | order_id=%s | mode=%s",
            order_id,
            normalized_mode.value,
        )

        order = get_order(
            order_id=order_id,
            db_path=self.db_path,
        )

        if order is None:
            logger.warning(
                "ORDER_NOT_FOUND | order_id=%s",
                order_id,
            )
            raise OrderNotFoundError(
                f"주문을 찾을 수 없습니다: {order_id}"
            )

        current_status = normalize_status(order["status"])

        if current_status != OrderStatus.APPROVED:
            logger.warning(
                "ORDER_NOT_EXECUTABLE | order_id=%s | status=%s",
                order_id,
                current_status.value,
            )
            raise OrderNotExecutableError(
                "APPROVED 상태의 주문만 실행할 수 있습니다. "
                f"현재 상태: {current_status.value}"
            )

        try:
            executing_order = mark_order_executing(
                order_id=order_id,
                execution_mode=normalized_mode.value,
                broker="TOSS",
                db_path=self.db_path,
            )

        except (OrderConflictError, InvalidStatusTransitionError):
            logger.exception(
                "ORDER_EXECUTION_LOCK_FAILED | order_id=%s",
                order_id,
            )
            raise

        logger.info(
            "ORDER_EXECUTION_STARTED | order_id=%s | symbol=%s "
            "| side=%s | quantity=%s",
            order_id,
            executing_order["symbol"],
            executing_order["side"],
            executing_order["quantity"],
        )

        try:
            adapter = self._get_adapter(normalized_mode)
            broker_response = adapter.execute(executing_order)

            if not broker_response.success:
                raise BrokerRejectedError(
                    broker_response.message
                )

            final_status = (
                OrderStatus.DRY_RUN_EXECUTED
                if normalized_mode == ExecutionMode.DRY_RUN
                else OrderStatus.EXECUTED
            )

            execution_payload = {
                "success": broker_response.success,
                "mode": normalized_mode.value,
                "broker_order_id": (
                    broker_response.broker_order_id
                ),
                "executed_price": (
                    broker_response.executed_price
                ),
                "executed_quantity": (
                    broker_response.executed_quantity
                ),
                "message": broker_response.message,
                "raw_response": broker_response.raw_response,
            }

            completed_order = complete_order_execution(
                order_id=order_id,
                status=final_status,
                execution_result=execution_payload,
                broker_order_id=(
                    broker_response.broker_order_id
                ),
                db_path=self.db_path,
            )

            logger.info(
                "ORDER_EXECUTION_SUCCESS | order_id=%s | status=%s "
                "| broker_order_id=%s",
                order_id,
                final_status.value,
                broker_response.broker_order_id,
            )

            return ExecutionResult(
                success=True,
                order_id=order_id,
                mode=normalized_mode,
                status=final_status,
                broker_order_id=(
                    broker_response.broker_order_id
                ),
                executed_price=(
                    broker_response.executed_price
                ),
                executed_quantity=(
                    broker_response.executed_quantity
                ),
                message=broker_response.message,
                order=completed_order,
            )

        except BrokerRejectedError as exc:
            return self._complete_failure(
                order_id=order_id,
                mode=normalized_mode,
                status=OrderStatus.REJECTED,
                error_code="BROKER_REJECTED",
                error_message=str(exc),
            )

        except BrokerTimeoutError as exc:
            return self._complete_failure(
                order_id=order_id,
                mode=normalized_mode,
                status=OrderStatus.TIMEOUT,
                error_code="BROKER_TIMEOUT",
                error_message=str(exc),
            )

        except UnsupportedExecutionModeError as exc:
            return self._complete_failure(
                order_id=order_id,
                mode=normalized_mode,
                status=OrderStatus.FAILED,
                error_code="UNSUPPORTED_EXECUTION_MODE",
                error_message=str(exc),
            )

        except Exception as exc:
            logger.exception(
                "ORDER_EXECUTION_UNEXPECTED_ERROR | order_id=%s",
                order_id,
            )

            return self._complete_failure(
                order_id=order_id,
                mode=normalized_mode,
                status=OrderStatus.FAILED,
                error_code=type(exc).__name__,
                error_message=str(exc),
            )

    def execute_next_approved(
        self,
        mode: ExecutionMode | str = ExecutionMode.DRY_RUN,
    ) -> ExecutionResult | None:
        """
        가장 오래된 APPROVED 주문 한 건을 실행한다.

        실행할 주문이 없으면 None을 반환한다.
        """

        approved_orders = get_approved_orders(
            limit=100,
            db_path=self.db_path,
        )

        if not approved_orders:
            logger.info("NO_APPROVED_ORDERS")
            return None

        oldest_order = min(
            approved_orders,
            key=lambda order: order["created_at"],
        )

        try:
            return self.execute_order(
                order_id=oldest_order["id"],
                mode=mode,
            )

        except OrderConflictError:
            logger.info(
                "ORDER_ALREADY_CLAIMED | order_id=%s",
                oldest_order["id"],
            )
            return None

    def _complete_failure(
        self,
        order_id: str,
        mode: ExecutionMode,
        status: OrderStatus,
        error_code: str,
        error_message: str,
    ) -> ExecutionResult:
        """실행 실패 상태와 오류 내용을 저장한다."""

        failure_payload = {
            "success": False,
            "mode": mode.value,
            "error_code": error_code,
            "error_message": error_message,
        }

        completed_order = complete_order_execution(
            order_id=order_id,
            status=status,
            execution_result=failure_payload,
            error_code=error_code,
            error_message=error_message,
            db_path=self.db_path,
        )

        logger.error(
            "ORDER_EXECUTION_FAILED | order_id=%s | status=%s "
            "| error_code=%s | error_message=%s",
            order_id,
            status.value,
            error_code,
            error_message,
        )

        return ExecutionResult(
            success=False,
            order_id=order_id,
            mode=mode,
            status=status,
            broker_order_id=None,
            executed_price=None,
            executed_quantity=None,
            message="주문 실행에 실패했습니다.",
            order=completed_order,
            error_code=error_code,
            error_message=error_message,
        )

    def _get_adapter(
        self,
        mode: ExecutionMode,
    ) -> BrokerAdapter:
        """실행 방식에 맞는 브로커 어댑터를 반환한다."""

        if mode == ExecutionMode.DRY_RUN:
            return self.dry_run_adapter

        if mode == ExecutionMode.REAL:
            return self.real_adapter

        raise UnsupportedExecutionModeError(
            f"지원하지 않는 실행 모드입니다: {mode}"
        )

    @staticmethod
    def _normalize_mode(
        mode: ExecutionMode | str,
    ) -> ExecutionMode:
        """문자열 또는 Enum을 ExecutionMode로 변환한다."""

        if isinstance(mode, ExecutionMode):
            return mode

        try:
            return ExecutionMode(
                str(mode).strip().upper()
            )
        except ValueError as exc:
            raise ValueError(
                "실행 모드는 DRY_RUN 또는 REAL이어야 합니다."
            ) from exc


_default_executor = OrderExecutor()


def execute_order(
    order_id: str,
    mode: ExecutionMode | str = ExecutionMode.DRY_RUN,
) -> ExecutionResult:
    """기본 Executor를 이용해 주문 한 건을 실행한다."""

    return _default_executor.execute_order(
        order_id=order_id,
        mode=mode,
    )


def execute_next_approved(
    mode: ExecutionMode | str = ExecutionMode.DRY_RUN,
) -> ExecutionResult | None:
    """기본 Executor를 이용해 승인 주문 한 건을 실행한다."""

    return _default_executor.execute_next_approved(
        mode=mode,
    )