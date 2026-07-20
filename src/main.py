from api import get_accounts, get_holdings
from auth import get_access_token


def to_float(value) -> float | None:
    """문자열이나 숫자를 float로 변환한다."""

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def format_number(value) -> str:
    """수량을 보기 좋은 숫자 형식으로 변환한다."""

    number = to_float(value)

    if number is None:
        return "-"

    if number.is_integer():
        return f"{int(number):,}"

    return f"{number:,.6f}".rstrip("0").rstrip(".")


def format_money(value, currency: str) -> str:
    """통화에 맞춰 금액을 표시한다."""

    number = to_float(value)

    if number is None:
        return "-"

    if currency == "KRW":
        return f"{number:,.0f}원"

    if currency == "USD":
        return f"${number:,.2f}"

    return f"{number:,.2f} {currency}"


def format_rate(value) -> str:
    """API의 소수형 수익률을 백분율로 표시한다."""

    number = to_float(value)

    if number is None:
        return "-"

    return f"{number * 100:+.2f}%"


def get_flag(country: str) -> str:
    """시장 국가에 맞는 국기를 반환한다."""

    if country == "KR":
        return "🇰🇷"

    if country == "US":
        return "🇺🇸"

    return "🌐"


def main():
    token_data = get_access_token()
    access_token = token_data.get("access_token")

    if not access_token:
        print("토큰 발급 실패")
        return

    print("토큰 발급 성공")

    accounts_data = get_accounts(access_token)
    accounts = accounts_data.get("result", [])

    if not accounts:
        print("조회된 계좌가 없습니다.")
        return

    print("계좌 목록 조회 성공")
    print(f"계좌 개수: {len(accounts)}")

    account_seq = accounts[0]["accountSeq"]

    holdings_data = get_holdings(
        access_token,
        account_seq,
    )

    print("보유 주식 조회 성공")

    summary = holdings_data.get("result", {})

    total_purchase = summary.get("totalPurchaseAmount", {})
    market_value = summary.get("marketValue", {}).get("amount", {})

    print()
    print("=" * 50)
    print("자산 요약")
    print("=" * 50)
    print(
        "총 매입금액(KRW):",
        format_money(total_purchase.get("krw"), "KRW"),
    )
    print(
        "총 매입금액(USD):",
        format_money(total_purchase.get("usd"), "USD"),
    )
    print(
        "평가금액(KRW):",
        format_money(market_value.get("krw"), "KRW"),
    )
    print(
        "평가금액(USD):",
        format_money(market_value.get("usd"), "USD"),
    )

    items = summary.get("items", [])

    print()
    print("=" * 50)
    print(f"보유 종목 목록 ({len(items)}개)")
    print("=" * 50)

    if not items:
        print("보유 중인 종목이 없습니다.")
        return

    for item in items:
        country = item.get("marketCountry", "")
        currency = item.get("currency", "")
        flag = get_flag(country)

        market_value_data = item.get("marketValue", {})
        profit_loss_data = item.get("profitLoss", {})
        daily_profit_loss_data = item.get("dailyProfitLoss", {})

        print()
        print(
            f"{flag} {item.get('name', '-')} "
            f"({item.get('symbol', '-')})"
        )
        print(f"보유수량     : {format_number(item.get('quantity'))}주")
        print(
            "평균 매입가  :",
            format_money(
                item.get("averagePurchasePrice"),
                currency,
            ),
        )
        print(
            "현재가       :",
            format_money(
                item.get("lastPrice"),
                currency,
            ),
        )
        print(
            "매입금액     :",
            format_money(
                market_value_data.get("purchaseAmount"),
                currency,
            ),
        )
        print(
            "평가금액     :",
            format_money(
                market_value_data.get("amount"),
                currency,
            ),
        )
        print(
            "평가손익     :",
            format_money(
                profit_loss_data.get("amount"),
                currency,
            ),
        )
        print(
            "수익률       :",
            format_rate(
                profit_loss_data.get("rate"),
            ),
        )
        print(
            "오늘 손익    :",
            format_money(
                daily_profit_loss_data.get("amount"),
                currency,
            ),
        )
        print(
            "오늘 등락률  :",
            format_rate(
                daily_profit_loss_data.get("rate"),
            ),
        )
        print("-" * 50)


if __name__ == "__main__":
    main()