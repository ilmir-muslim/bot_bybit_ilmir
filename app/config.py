import os
from dotenv import load_dotenv
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_BOT_TOKEN_TRADES = os.getenv("TELEGRAM_BOT_TOKEN_TRADES")
TELEGRAM_USER_ID = os.getenv("TELEGRAM_USER_ID")

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "your_api_key")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "your_api_secret")
IS_TESTNET = False

symbol = "SOLUSDT"