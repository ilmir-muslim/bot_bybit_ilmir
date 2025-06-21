import asyncio
from app.notifier import send_telegram_message
from app.services.bot_runner import TradingBot
from app.utils.log_helper import log_maker
from init_db import init_db  

if __name__ == "__main__":
    try:
        init_db()
        send_telegram_message("⚙️ [INIT] run_bot.py стартовал")

        bot = TradingBot(symbol="SOLUSDT")
        send_telegram_message("🤖 [BOT] run_loop начинается")
        bot.run_loop(interval_seconds=60)

    except Exception as e:
        import traceback
        log_maker(f"💀 [FATAL] Бот упал при запуске:\n{e}\n{traceback.format_exc()}")


