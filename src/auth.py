import requests

from config import CLIENT_ID, CLIENT_SECRET


TOKEN_URL = "https://openapi.tossinvest.com/oauth2/token"


def get_access_token():
    """토스 OAuth2 Access Token 발급"""

    payload = {
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded"
    }

    response = requests.post(
        TOKEN_URL,
        data=payload,
        headers=headers,
        timeout=10,
    )

    response.raise_for_status()

    return response.json()