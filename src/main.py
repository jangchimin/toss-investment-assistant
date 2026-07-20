from api import get_accounts, get_holdings
from auth import get_access_token


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

    print("총 매입금액(KRW):", total_purchase.get("krw"))
    print("총 매입금액(USD):", total_purchase.get("usd"))

    print("평가금액(KRW):", market_value.get("krw"))
    print("평가금액(USD):", market_value.get("usd"))


if __name__ == "__main__":
    main()