from __future__ import annotations

import json
from typing import Any, Literal
from urllib.parse import quote

import httpx
from openai import OpenAI

from config import OPENAI_API_KEY, OPENAI_MODEL
from order_executor import (
    ExecutionMode,
    execute_order,
)
from order_store import (
    approve_order,
    cancel_order,
    create_order,
    get_approved_orders,
    get_pending_orders,
)


FASTAPI_BASE_URL = "http://127.0.0.1:8001"


SYSTEM_INSTRUCTIONS = """
너는 사용자의 토스증권 포트폴리오를 조회하고,
안전한 주문 시뮬레이션을 관리하는 투자 비서다.

현재 주문 기능은 시뮬레이션 단계다.
어떤 경우에도 실제 토스증권 주문은 전송되지 않는다.

주문 상태 흐름:
PENDING
→ APPROVED
→ EXECUTING
→ DRY_RUN_EXECUTED

규칙:
1. 계좌 또는 보유 종목 정보가 필요하면 반드시 제공된 도구를 호출한다.

2. 실제 조회 결과에 없는 숫자를 추측하지 않는다.

3. 종목을 언급할 때 가능하면 종목명과 티커를 함께 표기한다.

4. 수익률은 API가 반환한 소수 값을 백분율로 변환한다.
   예: 0.0524는 +5.24%, -0.031은 -3.10%.

5. 사용자가 매수 또는 매도를 요청하면
   create_order_preview 도구를 호출한다.

6. 매도 요청은 가능한 한 먼저
   get_holding_by_symbol 도구로 보유 여부와 수량을 확인한다.

7. 사용자가 승인, 승인해줘, 확정, 확정해줘 등의 의사를 표현하면
   approve_order_preview 도구를 호출한다.

8. 사용자가 실행, 실행해줘, 주문 실행, DRY RUN 실행 등의
   의사를 표현하면 execute_order_preview 도구를 호출한다.

9. 승인과 실행은 서로 다른 단계다.
   승인됐다고 해서 실행됐다고 말하지 않는다.

10. 사용자가 취소, 주문 취소, 주문하지 마 등의 의사를 표현하면
    cancel_order_preview 도구를 호출한다.

11. 주문 ID를 말하지 않은 승인, 취소, 실행 요청도
    각각 해당 도구를 호출한다.

12. 대상 주문이 한 건이면 시스템이 자동으로 선택할 수 있다.

13. 대상 주문이 여러 건이면 임의로 선택하지 않는다.
    사용자가 선택할 수 있도록 주문 목록과 주문 ID를 안내한다.

14. 주문 승인 결과가 APPROVED라면
    아직 DRY RUN도 실행되지 않았음을 분명히 설명한다.

15. 주문 실행 결과가 DRY_RUN_EXECUTED라면
    시뮬레이션이 완료됐다고 설명한다.

16. DRY RUN 이후에도 실제 증권 주문은 전송되지 않는다.

17. 실제 주문이 체결됐거나 토스증권으로 전송됐다고
    절대 표현하지 않는다.

18. 주문 가격이나 예상 주문 금액을 알 수 없다면 추측하지 않는다.

19. 시장가 주문은 현재가가 조회되지 않았다면
    예상 주문 금액을 임의로 계산하지 않는다.

20. 지정가 주문의 예상 주문 금액은
    지정가 × 주문 수량으로 계산된 값임을 명확히 한다.

21. 투자 판단과 사실 조회를 명확히 구분한다.

22. 도구가 실패했다면 성공한 것처럼 답하지 않는다.

23. 한국어로 자연스럽고 이해하기 쉽게 답한다.

24. 포트폴리오 비중이나 집중도 분석 요청에는
    analyze_current_portfolio 도구를 사용한다.

25. 서로 다른 통화의 금액은 환율 정보 없이 합산하지 않는다.
""".strip()


TOOLS = [
    {
        "type": "function",
        "name": "get_portfolio_summary",
        "description": (
            "사용자의 전체 토스증권 포트폴리오를 조회한다. "
            "전체 평가금액, 매입금액, 보유 종목 수, "
            "모든 종목의 수량, 현재가, 손익, 수익률이 "
            "필요할 때 사용한다."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_holding_by_symbol",
        "description": (
            "특정 티커 또는 종목 코드를 현재 보유하고 있는지 조회한다. "
            "특정 종목의 수량, 평단가, 현재가, 평가금액, "
            "손익 또는 수익률을 묻는 경우 사용한다. "
            "매도 요청을 검증할 때도 사용한다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": (
                        "미국 주식 티커 또는 한국 주식 종목 코드. "
                        "예: ZVOL, PLTR, NVDA, 000020, 005930"
                    ),
                },
            },
            "required": ["symbol"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "analyze_current_portfolio",
        "description": (
            "현재 보유 종목의 통화별 수익, 종목 비중, 집중도, "
            "상위 보유 종목과 데이터 누락 여부를 분석한다. "
            "포트폴리오 구성, 쏠림 또는 분산 상태를 묻는 경우 사용한다."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "check_server_health",
        "description": (
            "토스증권 조회용 FastAPI 서버가 "
            "정상 실행 중인지 확인한다."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "create_order_preview",
        "description": (
            "주식 매수 또는 매도 요청을 실제로 전송하지 않고 "
            "PENDING 상태의 주문 미리보기로 저장한다. "
            "사용자가 특정 종목을 몇 주 매수하거나 매도해 달라고 "
            "요청한 경우 반드시 사용한다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": (
                        "미국 주식 티커 또는 한국 주식 종목 코드."
                    ),
                },
                "side": {
                    "type": "string",
                    "enum": ["buy", "sell"],
                    "description": "매수는 buy, 매도는 sell.",
                },
                "quantity": {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "description": "주문 수량.",
                },
                "order_type": {
                    "type": "string",
                    "enum": ["market", "limit"],
                    "description": (
                        "시장가는 market, 지정가는 limit. "
                        "사용자가 주문 유형을 말하지 않았다면 market."
                    ),
                },
                "limit_price": {
                    "type": ["number", "null"],
                    "description": (
                        "지정가 주문 가격. "
                        "시장가 주문이면 null."
                    ),
                },
            },
            "required": [
                "symbol",
                "side",
                "quantity",
                "order_type",
                "limit_price",
            ],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_pending_order_previews",
        "description": (
            "현재 PENDING 상태인 주문 미리보기 목록을 조회한다. "
            "사용자가 승인 대기 주문이나 주문 ID를 묻는 경우 사용한다."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "approve_order_preview",
        "description": (
            "PENDING 상태인 주문 미리보기를 APPROVED 상태로 변경한다. "
            "승인은 실행과 다르며 실제 증권 주문은 전송하지 않는다. "
            "사용자가 승인, 확정 등의 의사를 표현한 경우 사용한다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": ["string", "null"],
                    "description": (
                        "승인할 주문 ID. "
                        "사용자가 주문 ID를 말하지 않았다면 null."
                    ),
                },
            },
            "required": ["order_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "cancel_order_preview",
        "description": (
            "PENDING 상태인 주문 미리보기를 취소한다. "
            "사용자가 취소하거나 주문하지 말라고 요청한 경우 사용한다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": ["string", "null"],
                    "description": (
                        "취소할 주문 ID. "
                        "사용자가 주문 ID를 말하지 않았다면 null."
                    ),
                },
            },
            "required": ["order_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "execute_order_preview",
        "description": (
            "APPROVED 상태인 주문을 DRY RUN으로 실행한다. "
            "실제 토스증권 주문은 전송하지 않는다. "
            "사용자가 실행, 주문 실행, DRY RUN 실행 등의 "
            "의사를 표현한 경우 사용한다."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": ["string", "null"],
                    "description": (
                        "실행할 주문 ID. "
                        "사용자가 주문 ID를 말하지 않았다면 null."
                    ),
                },
            },
            "required": ["order_id"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


def create_client() -> OpenAI:
    """환경변수의 API 키로 OpenAI 클라이언트를 생성한다."""

    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY가 설정되지 않았습니다. "
            ".env 파일을 확인하세요."
        )

    return OpenAI(
        api_key=OPENAI_API_KEY,
    )


def request_fastapi(path: str) -> dict[str, Any]:
    """로컬 FastAPI 서버를 GET 방식으로 호출한다."""

    url = f"{FASTAPI_BASE_URL}{path}"

    try:
        response = httpx.get(
            url,
            timeout=30.0,
        )

        response.raise_for_status()

    except httpx.ConnectError as error:
        raise RuntimeError(
            "FastAPI 서버에 연결할 수 없습니다. "
            "8001번 포트에서 서버가 실행 중인지 확인하세요."
        ) from error

    except httpx.HTTPStatusError as error:
        try:
            error_data = error.response.json()
        except ValueError:
            error_data = {
                "detail": error.response.text,
            }

        return {
            "success": False,
            "status_code": error.response.status_code,
            "error": error_data,
        }

    except httpx.RequestError as error:
        raise RuntimeError(
            f"FastAPI 요청 중 오류가 발생했습니다: {error}"
        ) from error

    try:
        response_data = response.json()
    except ValueError:
        return {
            "success": False,
            "status_code": response.status_code,
            "error": "FastAPI 서버가 JSON 형식이 아닌 응답을 반환했습니다.",
            "response_text": response.text,
        }

    if isinstance(response_data, dict):
        return response_data

    return {
        "success": True,
        "data": response_data,
    }


def normalize_optional_order_id(
    order_id_value: Any,
) -> str | None:
    """
    도구 입력의 주문 ID를 정리한다.

    주문 ID는 UUID일 수 있으므로 대문자로 변환하지 않는다.
    """

    if order_id_value is None:
        return None

    order_id = str(order_id_value).strip()

    if not order_id:
        return None

    return order_id


def create_order_preview(
    symbol: str,
    side: Literal["buy", "sell"],
    quantity: float,
    order_type: Literal["market", "limit"],
    limit_price: float | None,
) -> dict[str, Any]:
    """
    주문 내용을 검증하고 SQLite에 PENDING 주문으로 저장한다.

    실제 주문은 전송하지 않는다.
    """

    normalized_symbol = symbol.strip().upper()

    if not normalized_symbol:
        return {
            "success": False,
            "error": "종목 티커 또는 종목 코드가 필요합니다.",
        }

    if quantity <= 0:
        return {
            "success": False,
            "error": "주문 수량은 0보다 커야 합니다.",
        }

    if order_type == "limit":
        if limit_price is None:
            return {
                "success": False,
                "error": "지정가 주문에는 주문 가격이 필요합니다.",
            }

        if limit_price <= 0:
            return {
                "success": False,
                "error": "지정가는 0보다 커야 합니다.",
            }

    if order_type == "market" and limit_price is not None:
        return {
            "success": False,
            "error": "시장가 주문에는 지정가를 입력할 수 없습니다.",
        }

    estimated_order_amount: float | None = None

    if order_type == "limit" and limit_price is not None:
        estimated_order_amount = round(
            quantity * limit_price,
            4,
        )

    try:
        order = create_order(
            symbol=normalized_symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
            estimated_order_amount=estimated_order_amount,
            metadata={
                "source": "openai_assistant",
                "preview_only": True,
                "simulation_only": True,
            },
        )
    except Exception as error:
        return {
            "success": False,
            "error": (
                "주문 미리보기를 저장하는 중 오류가 발생했습니다: "
                f"{error}"
            ),
        }

    return {
        "success": True,
        "preview_only": True,
        "simulation_only": True,
        "actual_order_submitted": False,
        "status": order.get("status", "PENDING"),
        "warning": (
            "이 주문은 데이터베이스에 PENDING 상태의 "
            "미리보기로만 저장되었습니다. "
            "토스증권으로 실제 주문은 전송되지 않았습니다."
        ),
        "order": order,
    }


def get_pending_order_previews() -> dict[str, Any]:
    """현재 PENDING 상태인 주문 목록을 반환한다."""

    try:
        pending_orders = get_pending_orders()
    except Exception as error:
        return {
            "success": False,
            "error": (
                "승인 대기 주문을 조회하는 중 오류가 발생했습니다: "
                f"{error}"
            ),
        }

    return {
        "success": True,
        "count": len(pending_orders),
        "pending_orders": pending_orders,
        "actual_order_submitted": False,
    }


def approve_order_preview(
    order_id: str | None,
) -> dict[str, Any]:
    """
    PENDING 주문을 승인한다.

    주문 ID가 없고 PENDING 주문이 정확히 한 건이면 자동 선택한다.
    """

    selected_order_id = order_id

    if selected_order_id is None:
        try:
            pending_orders = get_pending_orders()
        except Exception as error:
            return {
                "success": False,
                "error": (
                    "승인 대기 주문을 조회하는 중 오류가 발생했습니다: "
                    f"{error}"
                ),
            }

        if not pending_orders:
            return {
                "success": False,
                "error": "승인할 PENDING 주문이 없습니다.",
                "pending_order_count": 0,
            }

        if len(pending_orders) > 1:
            return {
                "success": False,
                "error": (
                    "승인 대기 주문이 여러 개 있습니다. "
                    "승인할 주문 ID를 지정해 주세요."
                ),
                "pending_order_count": len(pending_orders),
                "pending_orders": pending_orders,
            }

        selected_order_id = str(pending_orders[0]["id"])

    try:
        approved_order = approve_order(selected_order_id)
    except Exception as error:
        return {
            "success": False,
            "order_id": selected_order_id,
            "error": (
                "주문을 승인하는 중 오류가 발생했습니다: "
                f"{error}"
            ),
        }

    return {
        "success": True,
        "simulation_only": True,
        "actual_order_submitted": False,
        "dry_run_executed": False,
        "warning": (
            "주문은 승인됐지만 아직 실행되지 않았습니다. "
            "실행하려면 별도로 주문 실행을 요청해야 합니다. "
            "실행하더라도 현재는 DRY RUN만 수행됩니다."
        ),
        "order": approved_order,
    }


def cancel_order_preview(
    order_id: str | None,
) -> dict[str, Any]:
    """
    PENDING 주문을 취소한다.

    주문 ID가 없고 PENDING 주문이 정확히 한 건이면 자동 선택한다.
    """

    selected_order_id = order_id

    if selected_order_id is None:
        try:
            pending_orders = get_pending_orders()
        except Exception as error:
            return {
                "success": False,
                "error": (
                    "승인 대기 주문을 조회하는 중 오류가 발생했습니다: "
                    f"{error}"
                ),
            }

        if not pending_orders:
            return {
                "success": False,
                "error": "취소할 PENDING 주문이 없습니다.",
                "pending_order_count": 0,
            }

        if len(pending_orders) > 1:
            return {
                "success": False,
                "error": (
                    "승인 대기 주문이 여러 개 있습니다. "
                    "취소할 주문 ID를 지정해 주세요."
                ),
                "pending_order_count": len(pending_orders),
                "pending_orders": pending_orders,
            }

        selected_order_id = str(pending_orders[0]["id"])

    try:
        cancelled_order = cancel_order(selected_order_id)
    except Exception as error:
        return {
            "success": False,
            "order_id": selected_order_id,
            "error": (
                "주문을 취소하는 중 오류가 발생했습니다: "
                f"{error}"
            ),
        }

    return {
        "success": True,
        "simulation_only": True,
        "actual_order_submitted": False,
        "warning": (
            "주문 미리보기가 취소되었습니다. "
            "토스증권으로 실제 주문은 전송되지 않았습니다."
        ),
        "order": cancelled_order,
    }


def execute_order_preview(
    order_id: str | None,
) -> dict[str, Any]:
    """
    APPROVED 주문을 DRY RUN으로 실행한다.

    주문 ID가 없고 APPROVED 주문이 정확히 한 건이면 자동 선택한다.
    """

    selected_order_id = order_id

    if selected_order_id is None:
        try:
            approved_orders = get_approved_orders(
                limit=10,
            )
        except Exception as error:
            return {
                "success": False,
                "error": (
                    "승인된 주문을 조회하는 중 오류가 발생했습니다: "
                    f"{error}"
                ),
            }

        if not approved_orders:
            return {
                "success": False,
                "error": "실행할 APPROVED 주문이 없습니다.",
                "approved_order_count": 0,
            }

        if len(approved_orders) > 1:
            return {
                "success": False,
                "error": (
                    "승인된 주문이 여러 개 있습니다. "
                    "실행할 주문 ID를 지정해 주세요."
                ),
                "approved_order_count": len(approved_orders),
                "approved_orders": approved_orders,
            }

        selected_order_id = str(approved_orders[0]["id"])

    try:
        execution_result = execute_order(
            order_id=selected_order_id,
            mode=ExecutionMode.DRY_RUN,
        )
    except Exception as error:
        return {
            "success": False,
            "order_id": selected_order_id,
            "execution_mode": ExecutionMode.DRY_RUN.value,
            "actual_order_submitted": False,
            "error": (
                "DRY RUN 주문 실행 중 오류가 발생했습니다: "
                f"{error}"
            ),
        }

    result_data = execution_result.to_dict()

    return {
        **result_data,
        "simulation_only": True,
        "actual_order_submitted": False,
        "warning": (
            "DRY RUN 시뮬레이션 결과입니다. "
            "토스증권으로 실제 주문은 전송되지 않았습니다."
        ),
    }


def execute_tool(
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """모델이 요청한 도구를 실제 Python 함수에 연결한다."""

    if tool_name == "get_portfolio_summary":
        return request_fastapi("/portfolio")

    if tool_name == "get_holding_by_symbol":
        symbol = str(
            arguments.get("symbol", "")
        ).strip().upper()

        if not symbol:
            return {
                "success": False,
                "error": "종목 티커 또는 종목 코드가 필요합니다.",
            }

        encoded_symbol = quote(
            symbol,
            safe="",
        )

        return request_fastapi(
            f"/holdings/{encoded_symbol}"
        )

    if tool_name == "analyze_current_portfolio":
        return request_fastapi("/portfolio/analysis")

    if tool_name == "check_server_health":
        return request_fastapi("/health")

    if tool_name == "get_pending_order_previews":
        return get_pending_order_previews()

    if tool_name == "approve_order_preview":
        order_id = normalize_optional_order_id(
            arguments.get("order_id")
        )

        return approve_order_preview(
            order_id=order_id,
        )

    if tool_name == "cancel_order_preview":
        order_id = normalize_optional_order_id(
            arguments.get("order_id")
        )

        return cancel_order_preview(
            order_id=order_id,
        )

    if tool_name == "execute_order_preview":
        order_id = normalize_optional_order_id(
            arguments.get("order_id")
        )

        return execute_order_preview(
            order_id=order_id,
        )

    if tool_name == "create_order_preview":
        symbol = str(
            arguments.get("symbol", "")
        )

        side = str(
            arguments.get("side", "")
        ).strip().lower()

        order_type = str(
            arguments.get("order_type", "")
        ).strip().lower()

        quantity_value = arguments.get("quantity")
        limit_price_value = arguments.get("limit_price")

        if side not in {"buy", "sell"}:
            return {
                "success": False,
                "error": "주문 방향은 buy 또는 sell이어야 합니다.",
            }

        if order_type not in {"market", "limit"}:
            return {
                "success": False,
                "error": (
                    "주문 유형은 market 또는 limit이어야 합니다."
                ),
            }

        try:
            quantity = float(quantity_value)
        except (TypeError, ValueError):
            return {
                "success": False,
                "error": "올바른 주문 수량이 필요합니다.",
            }

        if limit_price_value is None:
            limit_price = None
        else:
            try:
                limit_price = float(limit_price_value)
            except (TypeError, ValueError):
                return {
                    "success": False,
                    "error": "올바른 지정가가 필요합니다.",
                }

        return create_order_preview(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            limit_price=limit_price,
        )

    return {
        "success": False,
        "error": f"지원하지 않는 도구입니다: {tool_name}",
    }


def ask_investment_assistant(
    user_message: str,
) -> str:
    """사용자 질문을 받고 필요하면 도구를 호출해 답변한다."""

    message = user_message.strip()

    if not message:
        return "질문을 입력해 주세요."

    client = create_client()

    input_items: list[Any] = [
        {
            "role": "user",
            "content": message,
        }
    ]

    try:
        response = client.responses.create(
            model=OPENAI_MODEL,
            instructions=SYSTEM_INSTRUCTIONS,
            tools=TOOLS,
            tool_choice="auto",
            input=input_items,
        )
    except Exception as error:
        return (
            "OpenAI API 요청 중 오류가 발생했습니다: "
            f"{error}"
        )

    for _ in range(8):
        function_calls = [
            item
            for item in response.output
            if item.type == "function_call"
        ]

        if not function_calls:
            answer = response.output_text.strip()

            if answer:
                return answer

            return "AI 응답을 생성하지 못했습니다."

        input_items.extend(response.output)

        for function_call in function_calls:
            try:
                arguments = json.loads(
                    function_call.arguments
                )
            except (json.JSONDecodeError, TypeError):
                arguments = {}

            try:
                tool_result = execute_tool(
                    function_call.name,
                    arguments,
                )
            except Exception as error:
                tool_result = {
                    "success": False,
                    "error": (
                        "도구를 실행하는 중 예상하지 못한 "
                        f"오류가 발생했습니다: {error}"
                    ),
                }

            input_items.append(
                {
                    "type": "function_call_output",
                    "call_id": function_call.call_id,
                    "output": json.dumps(
                        tool_result,
                        ensure_ascii=False,
                        default=str,
                    ),
                }
            )

        try:
            response = client.responses.create(
                model=OPENAI_MODEL,
                instructions=SYSTEM_INSTRUCTIONS,
                tools=TOOLS,
                tool_choice="auto",
                input=input_items,
            )
        except Exception as error:
            return (
                "도구 실행 결과를 OpenAI API에 전달하는 중 "
                f"오류가 발생했습니다: {error}"
            )

    return (
        "도구 호출이 너무 많이 반복되어 응답을 중단했습니다. "
        "질문을 조금 더 구체적으로 입력해 주세요."
    )