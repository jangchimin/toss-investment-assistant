from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    RateLimitError,
)

from ai_assistant import ask_investment_assistant


def main():
    print("=" * 60)
    print("Toss Investment Assistant")
    print("자연어로 토스증권 계좌를 조회할 수 있습니다.")
    print("종료하려면 exit 또는 quit를 입력하세요.")
    print("=" * 60)

    while True:
        print()
        user_message = input("나: ").strip()

        if user_message.lower() in {
            "exit",
            "quit",
            "종료",
        }:
            print("투자 비서를 종료합니다.")
            break

        if not user_message:
            continue

        try:
            answer = ask_investment_assistant(
                user_message
            )

        except AuthenticationError:
            answer = (
                "OpenAI API 키 인증에 실패했습니다. "
                ".env의 OPENAI_API_KEY를 확인하세요."
            )

        except RateLimitError:
            answer = (
                "OpenAI API 사용 한도 또는 결제 설정을 "
                "확인해야 합니다."
            )

        except APIConnectionError:
            answer = (
                "OpenAI API 서버에 연결하지 못했습니다. "
                "인터넷 연결을 확인하세요."
            )

        except APIStatusError as error:
            answer = (
                "OpenAI API 요청에 실패했습니다. "
                f"상태 코드: {error.status_code}"
            )

        except RuntimeError as error:
            answer = str(error)

        print()
        print("AI:", answer)


if __name__ == "__main__":
    main()