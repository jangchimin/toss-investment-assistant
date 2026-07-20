import os

from dotenv import load_dotenv


load_dotenv()


CLIENT_ID = os.getenv("TOSS_CLIENT_ID")
CLIENT_SECRET = os.getenv("TOSS_CLIENT_SECRET")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv(
    "OPENAI_MODEL",
    "gpt-5-mini",
)