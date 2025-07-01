import requests
from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_TOKEN_TRADES, TELEGRAM_USER_ID

def send_telegram_message(message: str, buy_sell: bool = False):
    if buy_sell:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN_TRADES}/sendMessage"
    else:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": TELEGRAM_USER_ID,
        "text": message
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")
        
