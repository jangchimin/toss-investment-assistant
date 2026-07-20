"""
order_store.py

주문 정보와 주문 상태를 SQLite에 저장하는 영속성 계층.

이 모듈의 책임:
- 주문 생성
- 주문 조회
- 주문 상태 변경
- 주문 실행 결과 저장
- 기존 데이터베이스 스키마 마이그레이션

이 모듈이 하지 않는 일:
- 자연어 주문 해석
- 주문 수량 계산
- Toss API 호출
- DRY RUN 실행
- 실제 매매 실행

주문 실행은 order_executor.py에서 담당한다.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Iterator


DEFAULT_DB_PATH = Path(__file__).resolve().parent / "orders.db"


class OrderStatus(str, Enum):
    """주문 처리 상태."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    EXECUTING = "EXECUTING"

    DRY_RUN_EXECUTED = "DRY_RUN_EXECUTED"
    EXECUTED = "EXECUTED"

    FAILED = "FAILED"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"

    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


TERMINAL_STATUSES = {
    OrderStatus.DRY_RUN_EXECUTED,
    OrderStatus.EXECUTED,
    OrderStatus.FAILED,
    OrderStatus.REJECTED,
    OrderStatus.TIMEOUT,
    OrderStatus.CANCELLED,
    OrderStatus.EXPIRED,
}


ALLOWED_STATUS_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.PENDING: {
        OrderStatus.APPROVED,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
    },
    OrderStatus.APPROVED: {
        OrderStatus.EXECUTING,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
    },
    OrderStatus.EXECUTING: {
        OrderStatus.DRY_RUN_EXECUTED,
        OrderStatus.EXECUTED,
        OrderStatus.FAILED,
        OrderStatus.REJECTED,
        OrderStatus.TIMEOUT,
    },
    OrderStatus.DRY_RUN_EXECUTED: set(),
    OrderStatus.EXECUTED: set(),
    OrderStatus.FAILED: set(),
    OrderStatus.REJECTED: set(),
    OrderStatus.TIMEOUT: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.EXPIRED: set(),
}


class OrderStoreError(Exception):
    """주문 저장소 기본 예외."""


class OrderNotFoundError(OrderStoreError):
    """주문을 찾지 못했을 때 발생."""


class InvalidStatusTransitionError(OrderStoreError):
    """허용되지 않은 상태 변경을 시도했을 때 발생."""


class OrderConflictError(OrderStoreError):
    """동시에 상태가 변경되어 요청을 처리할 수 없을 때 발생."""


def utc_now_iso() -> str:
    """현재 UTC 시각을 ISO 8601 문자열로 반환한다."""

    return datetime.now(timezone.utc).isoformat()


def normalize_status(status: OrderStatus | str) -> OrderStatus:
    """문자열 또는 OrderStatus 값을 OrderStatus로 변환한다."""

    if isinstance(status, OrderStatus):
        return status

    try:
        return OrderStatus(str(status).strip().upper())
    except ValueError as exc:
        valid_statuses = ", ".join(status.value for status in OrderStatus)
        raise ValueError(
            f"유효하지 않은 주문 상태입니다: {status}. "
            f"사용 가능한 상태: {valid_statuses}"
        ) from exc


def serialize_json(value: Any) -> str | None:
    """값을 JSON 문자열로 변환한다."""

    if value is None:
        return None

    return json.dumps(
        value,
        ensure_ascii=False,
        default=str,
    )


def deserialize_json(value: str | None) -> Any:
    """JSON 문자열을 Python 객체로 변환한다."""

    if value is None or value == "":
        return None

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


@contextmanager
def get_connection(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> Iterator[sqlite3.Connection]:
    """
    SQLite 연결을 생성하고 안전하게 종료한다.

    쓰기 작업 중 예외가 발생하면 자동으로 롤백한다.
    """

    resolved_path = Path(db_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        resolved_path,
        timeout=30,
    )

    connection.row_factory = sqlite3.Row

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 30000")

        yield connection
        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def table_exists(
    connection: sqlite3.Connection,
    table_name: str,
) -> bool:
    """SQLite 테이블 존재 여부를 확인한다."""

    row = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def get_existing_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    """테이블의 현재 컬럼 목록을 반환한다."""

    rows = connection.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return {row["name"] for row in rows}


def initialize_database(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    """
    주문 데이터베이스와 필요한 인덱스를 생성한다.

    기존 orders 테이블이 있다면 누락된 컬럼을 자동 추가한다.
    """

    with get_connection(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                order_type TEXT NOT NULL,
                limit_price REAL,
                estimated_order_amount REAL,
                currency TEXT NOT NULL DEFAULT 'USD',

                status TEXT NOT NULL DEFAULT 'PENDING',

                execution_mode TEXT,
                broker TEXT,
                broker_order_id TEXT,

                execution_result_json TEXT,
                error_code TEXT,
                error_message TEXT,

                metadata_json TEXT,

                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                approved_at TEXT,
                executing_at TEXT,
                executed_at TEXT,
                cancelled_at TEXT,
                expired_at TEXT
            )
            """
        )

        migrate_orders_table(connection)

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_orders_status
            ON orders(status)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_orders_symbol
            ON orders(symbol)
            """
        )

        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_orders_created_at
            ON orders(created_at)
            """
        )


def migrate_orders_table(
    connection: sqlite3.Connection,
) -> None:
    """
    이전 버전 orders 테이블에 누락된 컬럼을 추가한다.

    SQLite의 ALTER TABLE ADD COLUMN을 이용한 단순 마이그레이션이다.
    기존 주문 데이터는 유지된다.
    """

    if not table_exists(connection, "orders"):
        return

    existing_columns = get_existing_columns(
        connection,
        "orders",
    )

    columns_to_add: dict[str, str] = {
        "currency": "TEXT NOT NULL DEFAULT 'USD'",
        "execution_mode": "TEXT",
        "broker": "TEXT",
        "broker_order_id": "TEXT",
        "execution_result_json": "TEXT",
        "error_code": "TEXT",
        "error_message": "TEXT",
        "metadata_json": "TEXT",
        "approved_at": "TEXT",
        "executing_at": "TEXT",
        "executed_at": "TEXT",
        "cancelled_at": "TEXT",
        "expired_at": "TEXT",
    }

    for column_name, column_definition in columns_to_add.items():
        if column_name not in existing_columns:
            connection.execute(
                f"""
                ALTER TABLE orders
                ADD COLUMN {column_name} {column_definition}
                """
            )


def row_to_order(row: sqlite3.Row | None) -> dict[str, Any] | None:
    """SQLite Row를 사용자 친화적인 주문 딕셔너리로 변환한다."""

    if row is None:
        return None

    order = dict(row)

    order["metadata"] = deserialize_json(
        order.pop("metadata_json", None)
    )

    order["execution_result"] = deserialize_json(
        order.pop("execution_result_json", None)
    )

    return order


def create_order(
    symbol: str,
    side: str,
    quantity: int | float,
    order_type: str,
    limit_price: int | float | None = None,
    estimated_order_amount: int | float | None = None,
    currency: str = "USD",
    metadata: dict[str, Any] | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """
    새로운 주문을 PENDING 상태로 생성한다.

    Planner에서 검증된 주문 정보가 들어오는 것을 전제로 한다.
    """

    initialize_database(db_path)

    order_id = str(uuid.uuid4())
    now = utc_now_iso()

    normalized_symbol = str(symbol).strip().upper()
    normalized_side = str(side).strip().upper()
    normalized_order_type = str(order_type).strip().upper()
    normalized_currency = str(currency).strip().upper()

    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO orders (
                id,
                symbol,
                side,
                quantity,
                order_type,
                limit_price,
                estimated_order_amount,
                currency,
                status,
                metadata_json,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_id,
                normalized_symbol,
                normalized_side,
                float(quantity),
                normalized_order_type,
                (
                    float(limit_price)
                    if limit_price is not None
                    else None
                ),
                (
                    float(estimated_order_amount)
                    if estimated_order_amount is not None
                    else None
                ),
                normalized_currency,
                OrderStatus.PENDING.value,
                serialize_json(metadata or {}),
                now,
                now,
            ),
        )

    created_order = get_order(
        order_id=order_id,
        db_path=db_path,
    )

    if created_order is None:
        raise OrderStoreError(
            "주문을 생성했지만 다시 조회하지 못했습니다."
        )

    return created_order


def get_order(
    order_id: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any] | None:
    """주문 ID로 주문 한 건을 조회한다."""

    initialize_database(db_path)

    with get_connection(db_path) as connection:
        row = connection.execute(
            """
            SELECT *
            FROM orders
            WHERE id = ?
            """,
            (order_id,),
        ).fetchone()

    return row_to_order(row)


def get_orders_by_status(
    status: OrderStatus | str,
    limit: int = 100,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    """특정 상태의 주문 목록을 최신순으로 조회한다."""

    initialize_database(db_path)

    normalized_status = normalize_status(status)

    if limit <= 0:
        raise ValueError("limit은 0보다 커야 합니다.")

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM orders
            WHERE status = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (
                normalized_status.value,
                limit,
            ),
        ).fetchall()

    return [
        order
        for row in rows
        if (order := row_to_order(row)) is not None
    ]


def get_pending_orders(
    limit: int = 100,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    """PENDING 주문 목록을 조회한다."""

    return get_orders_by_status(
        status=OrderStatus.PENDING,
        limit=limit,
        db_path=db_path,
    )


def get_approved_orders(
    limit: int = 100,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    """APPROVED 주문 목록을 조회한다."""

    return get_orders_by_status(
        status=OrderStatus.APPROVED,
        limit=limit,
        db_path=db_path,
    )


def get_executing_orders(
    limit: int = 100,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    """EXECUTING 주문 목록을 조회한다."""

    return get_orders_by_status(
        status=OrderStatus.EXECUTING,
        limit=limit,
        db_path=db_path,
    )


def list_orders(
    limit: int = 100,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[dict[str, Any]]:
    """전체 주문을 최신순으로 조회한다."""

    initialize_database(db_path)

    if limit <= 0:
        raise ValueError("limit은 0보다 커야 합니다.")

    with get_connection(db_path) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM orders
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [
        order
        for row in rows
        if (order := row_to_order(row)) is not None
    ]


def transition_order_status(
    order_id: str,
    new_status: OrderStatus | str,
    expected_status: OrderStatus | str | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
    extra_updates: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    주문 상태를 원자적으로 변경한다.

    expected_status가 주어지면 현재 상태가 해당 값과 일치할 때만 변경된다.
    이를 이용해 중복 실행과 동시 실행 문제를 방지한다.
    """

    initialize_database(db_path)

    target_status = normalize_status(new_status)

    with get_connection(db_path) as connection:
        current_row = connection.execute(
            """
            SELECT *
            FROM orders
            WHERE id = ?
            """,
            (order_id,),
        ).fetchone()

        if current_row is None:
            raise OrderNotFoundError(
                f"주문을 찾을 수 없습니다: {order_id}"
            )

        current_status = normalize_status(
            current_row["status"]
        )

        if expected_status is not None:
            normalized_expected_status = normalize_status(
                expected_status
            )

            if current_status != normalized_expected_status:
                raise OrderConflictError(
                    f"주문 상태가 예상과 다릅니다. "
                    f"예상={normalized_expected_status.value}, "
                    f"현재={current_status.value}"
                )

        allowed_targets = ALLOWED_STATUS_TRANSITIONS.get(
            current_status,
            set(),
        )

        if target_status not in allowed_targets:
            raise InvalidStatusTransitionError(
                f"허용되지 않은 주문 상태 변경입니다: "
                f"{current_status.value} → {target_status.value}"
            )

        now = utc_now_iso()

        update_values: dict[str, Any] = {
            "status": target_status.value,
            "updated_at": now,
        }

        if target_status == OrderStatus.APPROVED:
            update_values["approved_at"] = now

        elif target_status == OrderStatus.EXECUTING:
            update_values["executing_at"] = now

        elif target_status in {
            OrderStatus.DRY_RUN_EXECUTED,
            OrderStatus.EXECUTED,
            OrderStatus.FAILED,
            OrderStatus.REJECTED,
            OrderStatus.TIMEOUT,
        }:
            update_values["executed_at"] = now

        elif target_status == OrderStatus.CANCELLED:
            update_values["cancelled_at"] = now

        elif target_status == OrderStatus.EXPIRED:
            update_values["expired_at"] = now

        if extra_updates:
            allowed_extra_fields = {
                "execution_mode",
                "broker",
                "broker_order_id",
                "execution_result_json",
                "error_code",
                "error_message",
                "metadata_json",
            }

            invalid_fields = (
                set(extra_updates) - allowed_extra_fields
            )

            if invalid_fields:
                raise ValueError(
                    "허용되지 않은 업데이트 필드입니다: "
                    + ", ".join(sorted(invalid_fields))
                )

            update_values.update(extra_updates)

        set_clause = ", ".join(
            f"{column_name} = ?"
            for column_name in update_values
        )

        parameters = list(update_values.values())
        parameters.extend(
            [
                order_id,
                current_status.value,
            ]
        )

        cursor = connection.execute(
            f"""
            UPDATE orders
            SET {set_clause}
            WHERE id = ?
              AND status = ?
            """,
            parameters,
        )

        if cursor.rowcount != 1:
            raise OrderConflictError(
                "주문 상태가 다른 작업에 의해 변경되었습니다."
            )

    updated_order = get_order(
        order_id=order_id,
        db_path=db_path,
    )

    if updated_order is None:
        raise OrderStoreError(
            "상태를 변경했지만 주문을 다시 조회하지 못했습니다."
        )

    return updated_order


def approve_order(
    order_id: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """PENDING 주문을 APPROVED 상태로 변경한다."""

    return transition_order_status(
        order_id=order_id,
        new_status=OrderStatus.APPROVED,
        expected_status=OrderStatus.PENDING,
        db_path=db_path,
    )


def cancel_order(
    order_id: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """
    PENDING 또는 APPROVED 주문을 취소한다.

    EXECUTING 이후의 주문은 이 함수로 취소할 수 없다.
    """

    order = get_order(
        order_id=order_id,
        db_path=db_path,
    )

    if order is None:
        raise OrderNotFoundError(
            f"주문을 찾을 수 없습니다: {order_id}"
        )

    current_status = normalize_status(order["status"])

    if current_status not in {
        OrderStatus.PENDING,
        OrderStatus.APPROVED,
    }:
        raise InvalidStatusTransitionError(
            f"{current_status.value} 상태의 주문은 "
            "취소할 수 없습니다."
        )

    return transition_order_status(
        order_id=order_id,
        new_status=OrderStatus.CANCELLED,
        expected_status=current_status,
        db_path=db_path,
    )


def expire_order(
    order_id: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """PENDING 또는 APPROVED 주문을 만료 처리한다."""

    order = get_order(
        order_id=order_id,
        db_path=db_path,
    )

    if order is None:
        raise OrderNotFoundError(
            f"주문을 찾을 수 없습니다: {order_id}"
        )

    current_status = normalize_status(order["status"])

    if current_status not in {
        OrderStatus.PENDING,
        OrderStatus.APPROVED,
    }:
        raise InvalidStatusTransitionError(
            f"{current_status.value} 상태의 주문은 "
            "만료 처리할 수 없습니다."
        )

    return transition_order_status(
        order_id=order_id,
        new_status=OrderStatus.EXPIRED,
        expected_status=current_status,
        db_path=db_path,
    )


def mark_order_executing(
    order_id: str,
    execution_mode: str,
    broker: str = "TOSS",
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """
    APPROVED 주문을 EXECUTING 상태로 변경한다.

    Executor가 주문을 가져간 직후 호출한다.
    """

    normalized_mode = str(
        execution_mode
    ).strip().upper()

    if normalized_mode not in {
        "DRY_RUN",
        "REAL",
    }:
        raise ValueError(
            "execution_mode는 DRY_RUN 또는 REAL이어야 합니다."
        )

    return transition_order_status(
        order_id=order_id,
        new_status=OrderStatus.EXECUTING,
        expected_status=OrderStatus.APPROVED,
        db_path=db_path,
        extra_updates={
            "execution_mode": normalized_mode,
            "broker": str(broker).strip().upper(),
            "error_code": None,
            "error_message": None,
        },
    )


def complete_order_execution(
    order_id: str,
    status: OrderStatus | str,
    execution_result: dict[str, Any] | None = None,
    broker_order_id: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """
    EXECUTING 주문의 최종 실행 결과를 저장한다.

    허용되는 최종 상태:
    - DRY_RUN_EXECUTED
    - EXECUTED
    - FAILED
    - REJECTED
    - TIMEOUT
    """

    final_status = normalize_status(status)

    allowed_final_statuses = {
        OrderStatus.DRY_RUN_EXECUTED,
        OrderStatus.EXECUTED,
        OrderStatus.FAILED,
        OrderStatus.REJECTED,
        OrderStatus.TIMEOUT,
    }

    if final_status not in allowed_final_statuses:
        raise ValueError(
            "실행 완료 상태는 DRY_RUN_EXECUTED, EXECUTED, "
            "FAILED, REJECTED, TIMEOUT 중 하나여야 합니다."
        )

    return transition_order_status(
        order_id=order_id,
        new_status=final_status,
        expected_status=OrderStatus.EXECUTING,
        db_path=db_path,
        extra_updates={
            "broker_order_id": broker_order_id,
            "execution_result_json": serialize_json(
                execution_result
            ),
            "error_code": error_code,
            "error_message": error_message,
        },
    )


def update_order_metadata(
    order_id: str,
    metadata: dict[str, Any],
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, Any]:
    """주문의 부가 정보를 갱신한다."""

    initialize_database(db_path)

    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE orders
            SET metadata_json = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                serialize_json(metadata),
                utc_now_iso(),
                order_id,
            ),
        )

        if cursor.rowcount != 1:
            raise OrderNotFoundError(
                f"주문을 찾을 수 없습니다: {order_id}"
            )

    updated_order = get_order(
        order_id=order_id,
        db_path=db_path,
    )

    if updated_order is None:
        raise OrderStoreError(
            "메타데이터를 변경했지만 주문을 다시 조회하지 못했습니다."
        )

    return updated_order


initialize_database()