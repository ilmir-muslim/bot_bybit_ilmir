import time
import traceback
from app.trading.data_provider import DataProvider
from app.trading.order_executor import OrderExecutor
from app.utils.log_helper import log_maker
from app.utils.candle_sync import CandleSynchronizer

class TradingBot:
    def __init__(self, strategy, symbol: str, interval: str, controller=None):
        self.symbol = symbol
        self.interval = int(interval)
        self.strategy = strategy
        self.controller = controller
        self.data_provider = DataProvider(symbol, interval)
        if controller:
            self.data_provider.controller = controller
        self.order_executor = OrderExecutor(symbol)
        self.synchronizer = CandleSynchronizer(self.interval)
        self._running = False
        self.first_run = True
        log_maker(f"🤖 Торговый бот инициализирован для {symbol}")
        log_maker(f"  • Стратегия: {type(strategy).__name__}")
        log_maker(f"  • Интервал: {interval} минут")
        log_maker(f"  • Синхронизация со свечами: включена")

    def run_once(self):
        start_time = time.time()
        try:
            # Проверяем наличие rotator перед вызовом
            if hasattr(self.strategy, 'rotator') and self.strategy.rotator is not None:
                self.strategy.rotator.update_activity()

            # Проверяем актуальные позиции через API
            open_positions = self.order_executor.bybit.get_open_positions()
            if open_positions:
                current_coin = open_positions[0]['coin']
                if current_coin != self.symbol.replace('USDT', ''):
                    log_maker(f"🔄 Обнаружено расхождение: позиция {current_coin} vs бот {self.symbol}")
                    self.controller.switch_coin(current_coin)
                    return  # Пропускаем цикл для переинициализации
            
            # Синхронизация со свечами
            sleep_time = self.synchronizer.time_until_next_candle()
            max_wait = 60 if self.first_run else 300
            self.first_run = False
            
            if sleep_time > 1:
                actual_wait = min(sleep_time, max_wait)
                if actual_wait > 5:
                    log_maker(f"⏱ Ожидание свечи: {actual_wait:.1f} сек")
                time.sleep(actual_wait)
            
            # Получение балансов
            coin = self.symbol.replace("USDT", "")
            usdt_balance = self.order_executor.bybit.get_balance("USDT")
            coin_balance = self.order_executor.bybit.get_balance(coin)
            log_maker(f"💰 Баланс: {usdt_balance:.2f} USDT, {coin_balance:.4f} {coin}")
            
            # Получение данных
            candles = self.data_provider.get_candles(limit=100)
            
            if not candles or len(candles) < 10:
                log_maker(f"⛔ Недостаточно данных: {len(candles)} свечей")
                return
                
            # Анализ и торговля
            action = self.strategy.should_trade(candles)
            
            if action:
                log_maker(f"⚡ Сигнал: {action}")
                self.strategy.execute_trade(action, self.order_executor)
                
        except Exception as e:
            log_maker(f"💥 Ошибка: {type(e).__name__} - {str(e)}")
            traceback.print_exc()
        finally:
            total_duration = time.time() - start_time
            log_maker(f"⏱ Цикл завершен за {total_duration:.2f} сек")
            time.sleep(max(10, self.interval * 60 - total_duration))
            
    def start(self):
        self._running = True
        log_maker(f"▶️ [BOT] Запущен ({type(self.strategy).__name__} стратегия)")
        while self._running:
            self.run_once()

    def stop(self):
        self._running = False
        log_maker("⏹️ [BOT] Остановлен")