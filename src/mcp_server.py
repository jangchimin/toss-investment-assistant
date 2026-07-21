from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP


FASTAPI_BASE_URL = "http://127.0.0.1:8001"

mcp = FastMCP(
    name="Toss Investment Assistant",
    instructions=(
        "토스증권 계좌와 보유 종목 정보를 조회하고 "
        "포트폴리오를 분석하는 투자 도구입니다. "
        "매수, 매도 또는 계좌 변경은 수행하지 않습니다."
    ),
    stateless_http=True,
    json_response=True,
)


def request_api(path: str) -> dict[str, Any]:
    """로컬 FastAPI 서버를 호출하고 JSON 응답을 반환한다."""

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
        detail = error.response.text

        raise RuntimeError(
            f"FastAPI 요청에 실패했습니다: "
            f"{error.response.status_code} {detail}"
        ) from error

    except httpx.RequestError as error:
        raise RuntimeError(
            "FastAPI 요청 중 네트워크 오류가 발생했습니다: "
            f"{error}"
        ) from error

    return response.json()


@mcp.tool()
def get_portfolio_summary() -> dict[str, Any]:
    """
    토스증권 계좌의 전체 자산 요약과 보유 종목을 조회한다.

    다음 정보를 반환한다.
    - 국내 및 미국 주식 총 매입금액
    - 국내 및 미국 주식 평가금액
    - 보유 종목 개수
    - 종목별 수량, 현재가, 손익, 수익률
    """

    return request_api("/portfolio")


@mcp.tool()
def analyze_current_portfolio() -> dict[str, Any]:
    """
    현재 보유 종목의 비중과 손익을 분석한다.

    다음 정보를 반환한다.
    - 통화별 총 매입금액
    - 통화별 총 평가금액
    - 통화별 총 평가손익과 수익률
    - 종목별 평가금액 비중

    원화와 달러는 환율 없이 합산하지 않는다.
    """

    return request_api("/portfolio/analysis")


@mcp.tool()
def get_holding_by_symbol(
    symbol: str,
) -> dict[str, Any]:
    """
    티커 또는 종목 심벌로 특정 보유 종목을 조회한다.

    예:
    - 미국 주식: ZVOL, PLTR, NVDA
    - 한국 주식: 000020, 005930
    """

    normalized_symbol = symbol.strip().upper()

    if not normalized_symbol:
        raise ValueError(
            "조회할 티커 또는 종목 심벌을 입력해야 합니다."
        )

    return request_api(
        f"/holdings/{normalized_symbol}"
    )


@mcp.tool()
def check_server_health() -> dict[str, Any]:
    """FastAPI 서버의 실행 상태를 확인한다."""

    return request_api("/health")


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
    )