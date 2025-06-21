from app.notifier import send_telegram_message


def log_maker(message: str):
    print(message)
    send_telegram_message(message)
