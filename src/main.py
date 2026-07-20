from auth import get_access_token


def main():
    token_data = get_access_token()

    access_token = token_data.get("access_token")

    if access_token:
        print("토큰 발급 성공")
        print(f"토큰 앞부분: {access_token[:8]}...")
        print(f"토큰 타입: {token_data.get('token_type')}")
        print(f"만료 시간: {token_data.get('expires_in')}")
    else:
        print("응답에 access_token이 없습니다.")


if __name__ == "__main__":
    main()