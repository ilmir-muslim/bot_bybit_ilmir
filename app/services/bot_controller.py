import threading
import time
from app.notifier import send_telegram_message
from app.services.bot_runner import TradingBot
from app.utils.log_helper import log_maker


class BotController:
    def __init__(self):
        self.thread = None
        self._running = threading.Event()
        self.bot = TradingBot()

    def start(self):
        if self.thread and self.thread.is_alive():
            return  # уже запущен
        self._running.set()
        self.thread = threading.Thread(target=self._run_bot_loop, daemon=True)
        self.thread.start()

    def stop(self):
        if self.thread:
            self._running.clear()
            self.thread.join(timeout=5)

    def status(self):
        return "running" if self._running.is_set() else "stopped"

    def _run_bot_loop(self):
        while self._running.is_set():
            try:
                self.bot.run_once()
                time.sleep(10)
            except Exception as e:
                log_maker(f"🚨 [ERROR] Ошибка в основном цикле бота:\n{e}")
                time.sleep(10)


bot_controller = BotController()
