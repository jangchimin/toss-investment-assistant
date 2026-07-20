"""
order_planner.py

AI가 해석한 주문 정보를 실제 주문 시스템에서 사용할 수 있는
표준 주문 계획(OrderPlan)으로 변환하고 검증한다.

이 모듈은 다음 작업만 담당한다.

1. 종목 코드 정규화
2. 매수/매도 방향 정규화
3. 시장가/지정가 주문 유형 정규화
4. 수량 및 가격 검증
5. 예상 주문 금액 계산
6. 주문 저장소에 넘길 수 있는 딕셔너리 생성

중요:
- 실제 Toss 주문 API를 호출하지 않는다.
- SQLite에 직접 저장하지 않는다.
- 주문 실행도 하지 않는다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from enum import Enum
from typing import Any


class OrderSide(str, Enum):
    """주문 방향."""

    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """주문 유형."""

    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass
class OrderPlan:
    """
    검증이 완료된 주문 계획.

    Attributes:
        symbol:
            종목 티커. 예: PLTR, NVDA, MSFT

        side:
            BUY 또는 SELL

        quantity:
            주문 수량

        order_type:
            MARKET 또는 LIMIT

        limit_price:
            지정가 주문 가격.
            시장가 주문일 때는 None.

        estimated_order_amount:
            예상 주문 금액.
            가격 정보가 없으면 None.

        currency:
            주문 통화. 현재 기본값은 USD.

        metadata:
            향후 주문 출처, 사용자 요청문 등의 정보를 저장하기 위한 필드.
    """

    symbol: str
    side: OrderSide
    quantity: Decimal
    order_type: OrderType
    limit_price: Decimal | None = None
    estimated_order_amount: Decimal | None = None
    currency: str = "USD"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """
        OrderPlan을 JSON 및 SQLite 저장에 적합한 딕셔너리로 변환한다.

        Decimal과 Enum은 그대로 JSON 직렬화할 수 없기 때문에
        문자열 또는 기본 자료형으로 변환한다.
        """

        result = asdict(self)

        result["side"] = self.side.value
        result["order_type"] = self.order_type.value
        result["quantity"] = decimal_to_number(self.quantity)

        if self.limit_price is not None:
            result["limit_price"] = decimal_to_number(self.limit_price)

        if self.estimated_order_amount is not None:
            result["estimated_order_amount"] = decimal_to_number(
                self.estimated_order_amount
            )

        return result


@dataclass
class ValidationResult:
    """
    주문 계획 검증 결과.

    valid:
        주문이 유효한지 여부

    order:
        유효한 경우 생성된 OrderPlan

    errors:
        주문을 생성할 수 없는 이유

    warnings:
        주문 실행은 가능하지만 사용자가 확인해야 할 내용
    """

    valid: bool
    order: OrderPlan | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """ValidationResult를 딕셔너리로 변환한다."""

        return {
            "valid": self.valid,
            "order": self.order.to_dict() if self.order else None,
            "errors": self.errors,
            "warnings": self.warnings,
        }


def normalize_symbol(symbol: Any) -> str:
    """
    종목 코드를 대문자로 정규화한다.

    예:
        "pltr" -> "PLTR"
        " NVDA " -> "NVDA"
    """

    if symbol is None:
        return ""

    return str(symbol).strip().upper()


def normalize_side(side: Any) -> OrderSide | None:
    """
    매수/매도 값을 OrderSide로 변환한다.

    영어와 일부 한국어 표현을 허용한다.
    """

    if side is None:
        return None

    normalized = str(side).strip().upper()

    buy_aliases = {
        "BUY",
        "B",
        "매수",
        "구매",
        "산다",
        "사기",
    }

    sell_aliases = {
        "SELL",
        "S",
        "매도",
        "판매",
        "판다",
        "팔기",
    }

    if normalized in buy_aliases:
        return OrderSide.BUY

    if normalized in sell_aliases:
        return OrderSide.SELL

    return None


def normalize_order_type(order_type: Any) -> OrderType | None:
    """
    주문 유형을 OrderType으로 변환한다.

    영어와 일부 한국어 표현을 허용한다.
    """

    if order_type is None:
        return None

    normalized = str(order_type).strip().upper().replace(" ", "_")

    market_aliases = {
        "MARKET",
        "MARKET_ORDER",
        "MKT",
        "시장가",
        "시장가주문",
    }

    limit_aliases = {
        "LIMIT",
        "LIMIT_ORDER",
        "LMT",
        "지정가",
        "지정가주문",
    }

    if normalized in market_aliases:
        return OrderType.MARKET

    if normalized in limit_aliases:
        return OrderType.LIMIT

    return None


def parse_positive_decimal(
    value: Any,
    field_name: str,
    errors: list[str],
) -> Decimal | None:
    """
    값을 양수 Decimal로 변환한다.

    변환할 수 없거나 0 이하인 경우 errors에 메시지를 추가한다.
    """

    if value is None:
        errors.append(f"{field_name} 값이 필요합니다.")
        return None

    if isinstance(value, bool):
        errors.append(f"{field_name} 값이 올바르지 않습니다.")
        return None

    try:
        parsed = Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError, TypeError):
        errors.append(f"{field_name} 값이 숫자가 아닙니다: {value}")
        return None

    if not parsed.is_finite():
        errors.append(f"{field_name} 값은 유한한 숫자여야 합니다.")
        return None

    if parsed <= 0:
        errors.append(f"{field_name} 값은 0보다 커야 합니다.")
        return None

    return parsed


def decimal_to_number(value: Decimal) -> int | float:
    """
    Decimal을 int 또는 float로 변환한다.

    소수점이 없으면 int,
    소수점이 있으면 float로 반환한다.
    """

    if value == value.to_integral_value():
        return int(value)

    return float(value)


def calculate_estimated_order_amount(
    quantity: Decimal,
    price: Decimal | None,
) -> Decimal | None:
    """
    수량과 가격을 이용해 예상 주문 금액을 계산한다.

    가격이 없는 시장가 주문은 계산할 수 없으므로 None을 반환한다.
    """

    if price is None:
        return None

    amount = quantity * price

    return amount.quantize(
        Decimal("0.01"),
        rounding=ROUND_DOWN,
    )


def validate_symbol(
    symbol: str,
    errors: list[str],
    warnings: list[str],
) -> None:
    """
    종목 코드 형식을 검증한다.

    현재 버전에서는 실제 거래 가능 종목 조회까지는 하지 않는다.
    """

    if not symbol:
        errors.append("종목 코드가 필요합니다.")
        return

    if len(symbol) > 15:
        errors.append("종목 코드가 너무 깁니다.")
        return

    allowed_characters = set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-"
    )

    if any(character not in allowed_characters for character in symbol):
        errors.append(
            "종목 코드는 영문, 숫자, 점(.), 하이픈(-)만 사용할 수 있습니다."
        )
        return

    if symbol[0] in {".", "-"}:
        errors.append("종목 코드는 점이나 하이픈으로 시작할 수 없습니다.")
        return

    warnings.append(
        "현재 Planner는 종목 코드 형식만 확인합니다. "
        "실제 거래 가능 종목 여부는 주문 실행 전에 별도로 확인해야 합니다."
    )


def validate_quantity(
    quantity: Decimal,
    warnings: list[str],
    allow_fractional: bool,
) -> None:
    """
    주문 수량을 검증한다.

    allow_fractional=False이면 정수 수량만 허용한다.
    """

    if not allow_fractional and quantity != quantity.to_integral_value():
        warnings.append(
            "소수점 수량이 입력되었습니다. "
            "증권사 또는 종목에 따라 소수점 주문이 지원되지 않을 수 있습니다."
        )


def create_order_plan(
    symbol: Any,
    side: Any,
    quantity: Any,
    order_type: Any = "MARKET",
    limit_price: Any = None,
    current_price: Any = None,
    currency: str = "USD",
    allow_fractional: bool = False,
    metadata: dict[str, Any] | None = None,
) -> ValidationResult:
    """
    주문 입력값을 검증하고 OrderPlan을 생성한다.

    Args:
        symbol:
            종목 코드

        side:
            BUY 또는 SELL

        quantity:
            주문 수량

        order_type:
            MARKET 또는 LIMIT

        limit_price:
            지정가 주문 가격

        current_price:
            시장가 주문의 예상 금액을 계산할 때 사용할 참고 가격.
            실제 체결가는 아니다.

        currency:
            주문 통화

        allow_fractional:
            소수점 수량 허용 여부

        metadata:
            추가 정보

    Returns:
        ValidationResult

    Examples:
        create_order_plan(
            symbol="PLTR",
            side="BUY",
            quantity=5,
            order_type="MARKET",
        )

        create_order_plan(
            symbol="NVDA",
            side="SELL",
            quantity=2,
            order_type="LIMIT",
            limit_price=180,
        )
    """

    errors: list[str] = []
    warnings: list[str] = []

    normalized_symbol = normalize_symbol(symbol)
    normalized_side = normalize_side(side)
    normalized_order_type = normalize_order_type(order_type)

    validate_symbol(
        symbol=normalized_symbol,
        errors=errors,
        warnings=warnings,
    )

    if normalized_side is None:
        errors.append(
            "주문 방향은 BUY 또는 SELL이어야 합니다."
        )

    if normalized_order_type is None:
        errors.append(
            "주문 유형은 MARKET 또는 LIMIT이어야 합니다."
        )

    parsed_quantity = parse_positive_decimal(
        value=quantity,
        field_name="주문 수량",
        errors=errors,
    )

    if parsed_quantity is not None:
        validate_quantity(
            quantity=parsed_quantity,
            warnings=warnings,
            allow_fractional=allow_fractional,
        )

    parsed_limit_price: Decimal | None = None
    parsed_current_price: Decimal | None = None

    if normalized_order_type == OrderType.LIMIT:
        parsed_limit_price = parse_positive_decimal(
            value=limit_price,
            field_name="지정가",
            errors=errors,
        )

        if current_price is not None:
            parsed_current_price = parse_positive_decimal(
                value=current_price,
                field_name="현재가",
                errors=errors,
            )

    elif normalized_order_type == OrderType.MARKET:
        if limit_price is not None:
            errors.append(
                "시장가 주문에는 지정가를 입력할 수 없습니다."
            )

        if current_price is not None:
            parsed_current_price = parse_positive_decimal(
                value=current_price,
                field_name="현재가",
                errors=errors,
            )
        else:
            warnings.append(
                "시장가 주문의 참고 현재가가 없어 "
                "예상 주문 금액을 계산하지 못했습니다."
            )

    normalized_currency = str(currency).strip().upper()

    if not normalized_currency:
        errors.append("통화 정보가 필요합니다.")
    elif len(normalized_currency) != 3:
        errors.append(
            "통화 코드는 USD, KRW처럼 3자리여야 합니다."
        )

    if errors:
        return ValidationResult(
            valid=False,
            order=None,
            errors=errors,
            warnings=warnings,
        )

    if (
        normalized_side is None
        or normalized_order_type is None
        or parsed_quantity is None
    ):
        return ValidationResult(
            valid=False,
            order=None,
            errors=["주문 계획을 생성할 수 없습니다."],
            warnings=warnings,
        )

    calculation_price: Decimal | None

    if normalized_order_type == OrderType.LIMIT:
        calculation_price = parsed_limit_price
    else:
        calculation_price = parsed_current_price

    estimated_order_amount = calculate_estimated_order_amount(
        quantity=parsed_quantity,
        price=calculation_price,
    )

    if (
        normalized_order_type == OrderType.MARKET
        and parsed_current_price is not None
    ):
        warnings.append(
            "시장가 주문의 예상 금액은 참고 현재가를 이용한 추정치이며, "
            "실제 체결 금액과 다를 수 있습니다."
        )

    order_plan = OrderPlan(
        symbol=normalized_symbol,
        side=normalized_side,
        quantity=parsed_quantity,
        order_type=normalized_order_type,
        limit_price=parsed_limit_price,
        estimated_order_amount=estimated_order_amount,
        currency=normalized_currency,
        metadata=metadata or {},
    )

    return ValidationResult(
        valid=True,
        order=order_plan,
        errors=[],
        warnings=warnings,
    )


def create_market_order_plan(
    symbol: Any,
    side: Any,
    quantity: Any,
    current_price: Any = None,
    currency: str = "USD",
    allow_fractional: bool = False,
    metadata: dict[str, Any] | None = None,
) -> ValidationResult:
    """시장가 주문 계획을 생성하는 편의 함수."""

    return create_order_plan(
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type=OrderType.MARKET.value,
        limit_price=None,
        current_price=current_price,
        currency=currency,
        allow_fractional=allow_fractional,
        metadata=metadata,
    )


def create_limit_order_plan(
    symbol: Any,
    side: Any,
    quantity: Any,
    limit_price: Any,
    currency: str = "USD",
    allow_fractional: bool = False,
    metadata: dict[str, Any] | None = None,
) -> ValidationResult:
    """지정가 주문 계획을 생성하는 편의 함수."""

    return create_order_plan(
        symbol=symbol,
        side=side,
        quantity=quantity,
        order_type=OrderType.LIMIT.value,
        limit_price=limit_price,
        current_price=None,
        currency=currency,
        allow_fractional=allow_fractional,
        metadata=metadata,
    )


def planner_result_for_order_store(
    result: ValidationResult,
) -> dict[str, Any]:
    """
    검증 결과를 order_store.create_order()에 전달하기 좋은 형태로 변환한다.

    검증에 실패한 결과가 들어오면 ValueError를 발생시킨다.
    """

    if not result.valid or result.order is None:
        error_message = "; ".join(result.errors) or "유효하지 않은 주문입니다."
        raise ValueError(error_message)

    order = result.order.to_dict()

    return {
        "symbol": order["symbol"],
        "side": order["side"],
        "quantity": order["quantity"],
        "order_type": order["order_type"],
        "limit_price": order["limit_price"],
        "estimated_order_amount": order["estimated_order_amount"],
    }