import time
import json
import logging
from app.services.coin_ranker import CoinRanker
from app.services.coin_selector import CoinSelector
from app.utils.log_helper import log_maker

class CoinRotator:
    def __init__(
        self, 
        initial_coins: list, 
        trading_system,
        rotation_interval: int = 86400,  # 24 часа в секундах
        min_hold_candles: int = 12       # Минимальное время удержания (в свечах)
    ):
        self.coin_list = initial_coins
        self.trading_system = trading_system
        self.rotation_interval = rotation_interval
        self.min_hold_candles = min_hold_candles
        self.ranker = CoinRanker()
        self.selector = CoinSelector(initial_coins)
        self.logger = logging.getLogger("coin_rotator")
        self.logger.setLevel(logging.INFO)
        
        # Загружаем состояние
        self.state = self.trading_system.state
        self.logger.info(f"⚙️ Инициализирован ротатор для {initial_coins}")
        self.logger.info(f"  • Интервал ротации: {rotation_interval/3600} часов")
        self.logger.info(f"  • Минимальное удержание: {min_hold_candles} свечей")

    def should_rotate(self) -> bool:
        """Определяет, нужно ли выполнять ротацию"""
        # Если есть открытая позиция - ротация запрещена
        if self.trading_system.position_open_time > 0:
            return False
            
        # Рассчитываем время удержания в свечах
        current_time = time.time()
        hold_time = current_time - self.state.get("last_rotation_time", 0)
        hold_candles = hold_time / (self.trading_system.strategy.interval * 60)
        
        # Проверяем минимальное время удержания
        if hold_candles < self.min_hold_candles:
            self.logger.info(f"⏱ Удерживаем {self.state['current_coin']} ещё {self.min_hold_candles - int(hold_candles)} свеч")
            return False
            
        # Проверяем интервал ротации
        if hold_time < self.rotation_interval:
            return False
            
        return True

    def rotate_coins(self) -> str:
        """Основная логика ротации монет"""
        # Проверяем необходимость ротации
        if not self.should_rotate():
            return self.state["current_coin"]
            
        # Получаем лучшие монеты из ранкера
        best_coins = self.ranker.get_best_coins(top_n=5)
        
        # Получаем оценку монет от селектора
        scores = self.selector.evaluate_coins()
        top_scores = [coin for coin, _ in scores[:5]]
        
        # Комбинируем результаты
        candidates = set(best_coins + top_scores)
        self.logger.info(f"🏆 Кандидаты на ротацию: {candidates}")
        
        # Выбираем лучшую монету (исключая текущую)
        current_coin = self.state["current_coin"]
        candidates.discard(current_coin)
        
        if not candidates:
            self.logger.info("⏭️ Нет подходящих кандидатов для ротации")
            return current_coin
            
        # Выбираем монету с максимальным приоритетом в ранкере
        new_coin = best_coins[0]
        
        # Обновляем состояние
        self.state["current_coin"] = new_coin
        self.state["last_rotation_time"] = time.time()
        self.trading_system.save_state()
        
        # Фиксируем выбор в ранкере
        self.ranker.record_selection(new_coin)
        
        self.logger.info(f"🔄 Ротация с {current_coin} на {new_coin}")
        return new_coin
    
    def set_current_coin(self, coin: str):
        """Устанавливает текущую монету"""
        if coin in self.coin_list:
            self.state["current_coin"] = coin
            self.trading_system.save_state()
            self.logger.info(f"⚙️ Установлена текущая монета: {coin}")

    def update_activity(self):
        """Обновляет время последней активности (вызывается каждый цикл)"""
        # Для будущего использования, если понадобится
        pass