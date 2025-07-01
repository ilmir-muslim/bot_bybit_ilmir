from app.notifier import send_telegram_message


def log_maker(message: str, buy_sell: bool = False):
    print(message)
    send_telegram_message(message, buy_sell=buy_sell)

def log_error(message: str):
    """Логирует критические ошибки"""
    error_message = f"🔥 [CRITICAL] {message}"
    print(error_message)
    send_telegram_message(error_message, buy_sell=True)