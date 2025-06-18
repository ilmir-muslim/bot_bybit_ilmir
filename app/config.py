import os
from dotenv import load_dotenv
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", '7642779617:AAFKW1q-JBEWWVlikf7pjsYSxK1tFehF6jE')
TELEGRAM_USER_ID = os.getenv("TELEGRAM_USER_ID", '6903748145')

BYBIT_API_KEY = os.getenv("BYBIT_API_KEY", "your_api_key")
BYBIT_API_SECRET = os.getenv("BYBIT_API_SECRET", "your_api_secret")
IS_TESTNET = False

DB_URL = os.getenv("DB_URL")