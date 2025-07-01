import os
import json
import time
from app.services.coin_ranker import CoinRanker
from app.services.model_trainer import ModelTrainer
from app.services.bybit_service import BybitService
from app.strategies.ma_crossover import MovingAverageStrategy
from app.strategies.neural_strategy import NeuralStrategy
from app.utils.log_helper import log_maker
from app.services.coin_rotator import CoinRotator

class TradingSystem:
    def __init__(self, coin_list):
        self.coin_list = coin_list
        self.state = self.load_state()
        self.bybit = BybitService()
        self.ranker = CoinRanker()
        self.model_trainer = ModelTrainer(coin_list)
        self.rotator = CoinRotator(coin_list, trading_system=self)
        self.position_open_time = self.state.get("position_open_time", 0)
        self.position_coin = self.state.get("position_coin", "")
        self.max_hold_hours = 24
        
        # Инициализация системы
        self.ranker.add_new_coins(coin_list)
        self.current_coin = self.state.get("current_coin", coin_list[0])
        self.current_symbol = f"{self.current_coin}USDT"
        self._init_strategy()  # Вызываем инициализацию стратегии
        
        # Автоматическое обучение моделей при запуске
        self.train_missing_models()
        self.model_trainer.start_periodic_retraining()
        
        log_maker(f"⚙️ Торговая система инициализирована. Текущая монета: {self.current_coin}")
    
    def train_missing_models(self):
        """Обучение моделей для монет, у которых они отсутствуют"""
        for coin in self.coin_list:
            model_path = f"models/{coin}_neural_model.keras"
            if not os.path.exists(model_path):
                log_maker(f"🧠 Модель для {coin} отсутствует. Добавляю в очередь обучения.")
                self.model_trainer.add_to_queue(coin, force_retrain=True)
    
    def load_state(self):
        try:
            with open("bot_state.json", "r") as f:
                return json.load(f)
        except:
            return {"current_coin": self.coin_list[0]}

    def save_state(self):
        """Сохраняет текущее состояние системы"""
        self.state = {
            "current_coin": self.current_coin,
            "position_open_time": self.position_open_time,
            "position_coin": self.position_coin
        }
        with open("bot_state.json", "w") as f:
            json.dump(self.state, f, indent=2)

    def _init_strategy(self):
        """Инициализирует стратегию с автоматическим выбором типа"""
        # Формируем символ и путь к модели
        symbol = f"{self.current_coin}USDT"
        model_base = f"models/{self.current_coin}_neural_model"
        model_file = f"{model_base}.keras"
        
        try:
            # Пытаемся использовать нейросетевую стратегию, если модель доступна
            if os.path.exists(model_file):
                self.strategy = NeuralStrategy(
                    symbol, 
                    bybit_service=self.bybit,
                    model_path=model_base,
                    rotator=self.rotator,
                    trading_system=self
                )
                log_maker(f"🧠 Используется нейросетевая стратегия для {symbol}")
            else:
                # Fallback на MA стратегию
                log_maker(f"🔄 Модель для {symbol} не найдена. Использую MA стратегию")
                self.strategy = MovingAverageStrategy(
                    symbol, 
                    "3", 
                    rotator=self.rotator,
                    trading_system=self
                )
                
                # Запускаем обучение модели в фоне
                self.model_trainer.add_to_queue(self.current_coin, force_retrain=True)
        except Exception as e:
            # Двойной fallback на случай ошибки инициализации
            log_maker(f"🔥 Ошибка инициализации стратегии: {e}. Использую базовую MA.")
            self.strategy = MovingAverageStrategy(
                symbol, 
                "3", 
                rotator=self.rotator,
                trading_system=self
            )
    
    def health_check(self):
        return {
            "current_coin": self.current_coin,
            "position_open": self.position_open_time > 0,
            "position_hours": (time.time() - self.position_open_time) / 3600 if self.position_open_time else 0
        }

    def start(self):
        log_maker("🚀 Система торговли запущена")

    def stop(self):
        log_maker("🛑 Система торговли остановлена")

    def switch_coin(self, new_coin: str):
        """Переключает торгуемую монету"""
        self.current_coin = new_coin
        self.current_symbol = f"{new_coin}USDT"  # Обновляем символ
        self.save_state()
        self._init_strategy()

    def check_force_close(self) -> bool:
        """Проверяет необходимость принудительного закрытия позиции"""
        if self.position_open_time == 0:
            return False
            
        # Рассчитываем время удержания в часах
        hold_hours = (time.time() - self.position_open_time) / 3600
        return hold_hours >= self.max_hold_hours