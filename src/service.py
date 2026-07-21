from typing import Any

from api import get_accounts, get_holdings
from auth import get_access_token
from portfolio import PortfolioAnalyzer


def to_float(value: Any) -> float | None:
    """문자열 또는 숫자를 float로 안전하게 변환한다."""

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_first_account_seq(access_token: str) -> int:
    """조회 가능한 첫 번째 계좌의 accountSeq를 반환한다."""

    accounts_data = get_accounts(access_token)
    accounts = accounts_data.get("result", [])

    if not accounts:
        raise RuntimeError(
            "조회 가능한 토스증권 계좌가 없습니다."
        )

    account_seq = accounts[0].get("accountSeq")

    if account_seq is None:
        raise RuntimeError(
            "계좌 응답에서 accountSeq를 찾을 수 없습니다."
        )

    return int(account_seq)


def get_portfolio() -> dict:
    """토스증권 계좌의 자산 요약과 보유 종목을 반환한다."""

    token_data = get_access_token()
    access_token = token_data.get("access_token")

    if not access_token:
        raise RuntimeError(
            "토스증권 액세스 토큰 발급에 실패했습니다."
        )

    account_seq = get_first_account_seq(
        access_token
    )

    holdings_data = get_holdings(
        access_token,
        account_seq,
    )

    result = holdings_data.get("result", {})
    items = result.get("items", [])

    total_purchase = result.get(
        "totalPurchaseAmount",
        {},
    )

    market_value = (
        result.get("marketValue", {})
        .get("amount", {})
    )

    holdings = []

    for item in items:
        item_market_value = item.get(
            "marketValue",
            {},
        )

        profit_loss = item.get(
            "profitLoss",
            {},
        )

        daily_profit_loss = item.get(
            "dailyProfitLoss",
            {},
        )

        holdings.append(
            {
                "symbol": item.get("symbol"),
                "name": item.get("name"),
                "market_country": item.get(
                    "marketCountry"
                ),
                "currency": item.get("currency"),
                "quantity": to_float(
                    item.get("quantity")
                ),
                "average_purchase_price": to_float(
                    item.get(
                        "averagePurchasePrice"
                    )
                ),
                "last_price": to_float(
                    item.get("lastPrice")
                ),
                "purchase_amount": to_float(
                    item_market_value.get(
                        "purchaseAmount"
                    )
                ),
                "market_value": to_float(
                    item_market_value.get(
                        "amount"
                    )
                ),
                "profit_loss_amount": to_float(
                    profit_loss.get("amount")
                ),
                "profit_loss_rate": to_float(
                    profit_loss.get("rate")
                ),
                "daily_profit_loss_amount": (
                    to_float(
                        daily_profit_loss.get(
                            "amount"
                        )
                    )
                ),
                "daily_profit_loss_rate": (
                    to_float(
                        daily_profit_loss.get(
                            "rate"
                        )
                    )
                ),
            }
        )

    return {
        "summary": {
            "total_purchase_krw": to_float(
                total_purchase.get("krw")
            ),
            "total_purchase_usd": to_float(
                total_purchase.get("usd")
            ),
            "market_value_krw": to_float(
                market_value.get("krw")
            ),
            "market_value_usd": to_float(
                market_value.get("usd")
            ),
            "holding_count": len(holdings),
        },
        "holdings": holdings,
    }


def get_holding(symbol: str) -> dict | None:
    """심벌과 일치하는 보유 종목 하나를 반환한다."""

    normalized_symbol = symbol.strip().upper()

    if not normalized_symbol:
        return None

    portfolio = get_portfolio()

    for holding in portfolio["holdings"]:
        holding_symbol = str(
            holding.get("symbol", "")
        ).upper()

        if holding_symbol == normalized_symbol:
            return holding

    return None


def get_portfolio_analysis() -> dict:
    """현재 보유 종목의 비중과 손익을 분석한다."""

    portfolio = get_portfolio()
    holdings = portfolio.get("holdings", [])

    analyzer = PortfolioAnalyzer()

    return analyzer.analyze(holdings)