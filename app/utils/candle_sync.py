import time
import math


class CandleSynchronizer:
    def __init__(self, interval_minutes: int = 5):
        self.interval_seconds = interval_minutes * 60

    def get_next_execution_time(self):
        current_time = time.time()
        next_candle = (
            math.ceil(current_time / self.interval_seconds) * self.interval_seconds
        )
        return next_candle

    def time_until_next_execution(self):
        return self.get_next_execution_time() - time.time()

    def sync(self):
        sleep_time = self.time_until_next_execution()
        if sleep_time > 0:
            time.sleep(sleep_time)

    def time_until_next_candle(self):  # <-- Добавьте этот метод
        """Возвращает количество секунд до начала следующей свечи"""
        current_time = time.time()
        next_candle_start = math.ceil(current_time / self.interval_seconds) * self.interval_seconds
        return next_candle_start - current_time
        
    def sync(self):
        """Ожидает начала следующей свечи"""
        sleep_time = self.time_until_next_candle()
        if sleep_time > 0:
            time.sleep(sleep_time)