import asyncio
from app.services.bot_runner import TradingBot


if __name__ == "__main__":
    bot = TradingBot(symbol="DOGEUSDT")  # или другая пара
    asyncio.run(bot.run_loop(interval_seconds=60)) 