import requests


BASE_URL = "https://openapi.tossinvest.com"


def get_accounts(access_token: str) -> dict:
    """토스증권 계좌 목록을 조회한다."""

    url = f"{BASE_URL}/api/v1/accounts"

    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=10,
    )

    response.raise_for_status()

    return response.json()

def get_holdings(access_token: str, account_seq: int) -> dict:
    """보유 주식을 조회한다."""

    url = f"{BASE_URL}/api/v1/holdings"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-Tossinvest-Account": str(account_seq),
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=10,
    )

    response.raise_for_status()

    return response.json()