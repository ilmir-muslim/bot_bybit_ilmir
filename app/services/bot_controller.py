import os
import json
import time
import threading
import logging
from app.services.bot_runner import TradingBot
from app.services.bybit_service import BybitService
from app.strategies import NeuralStrategy, MovingAverageStrategy
from app.utils.log_helper import log_maker, log_error

class BotController:
    def __init__(self, strategy_type='neural', rotator=None):
        self.thread = None
        self.strategy_type = strategy_type
        self._running = threading.Event()
        self.bybit = BybitService()
        self.state = self.load_bot_state()
        self.rotator = rotator
        
        # Проверка открытых позиций через API
        open_positions = self.bybit.get_open_positions()
        if open_positions:
            self.symbol = open_positions[0]['symbol']
            self.position_coin = open_positions[0]['coin']
            log_maker(f"⚡ Обнаружена открытая позиция: {self.symbol}")
        else:
            self.symbol = self._clean_symbol(self.state.get("current_coin", "SOL"))
            self.position_coin = self.symbol.replace('USDT', '')
        
        # Инициализация стратегии
        self.interval = "5" if strategy_type == 'neural' else "3"
        self.strategy = self._initialize_strategy()
        self.bot = TradingBot(
            strategy=self.strategy,
            symbol=self.symbol, 
            interval=self.interval,
            controller=self
        )
        
        log_maker(f"⚙️ Стратегия: {type(self.strategy).__name__}, интервал: {self.interval} минут")
        self.save_bot_state()

    def load_bot_state(self) -> dict:
        """Загружает состояние бота из файла"""
        try:
            with open("bot_state.json", "r") as f:
                return json.load(f)
        except:
            return {
                "current_coin": "SOL",
                "symbol": "SOLUSDT",
                "position_coin": "SOL"
            }

    def _clean_symbol(self, symbol_str: str) -> str:
        """Форматирование символа"""
        base = symbol_str.replace('USDT', '')
        return f"{base}USDT"
    
    def _initialize_strategy(self):
        """Инициализация торговой стратегии"""
        coin = self.symbol.replace('USDT', '')
        model_base_path = f"models/{coin}_neural_model"
        
        # Выбор между нейросетевой и MA стратегией
        if self.strategy_type != 'neural':
            return MovingAverageStrategy(
                self.symbol, 
                self.interval,
                trading_system=self
            )
        
        try:
            strategy = NeuralStrategy(
                self.symbol, 
                bybit_service=self.bybit,
                model_path=model_base_path,
                rotator=self.rotator,  
                trading_system=self,
                interval=self.interval
            )
            log_maker(f"🧠 Нейросетевая стратегия загружена для {self.symbol}")
            return strategy
        except Exception as e:
            log_error(f"❌ Ошибка инициализации нейросетевой стратегии: {e}")
            log_maker("🔄 Использую MovingAverage стратегию как fallback")
            return MovingAverageStrategy(
                self.symbol, 
                self.interval,
                trading_system=self
            )
    
    def save_bot_state(self):
        """Сохранение состояния системы"""
        state = {
            "current_coin": self.position_coin,
            "symbol": self.symbol,
            "position_coin": self.position_coin
        }
        with open("bot_state.json", "w") as f:
            json.dump(state, f, indent=2)

    def switch_coin(self, new_coin: str):
        """Переключение на новую монету"""
        log_maker(f"🔄 Переключение на {new_coin}")
        self.position_coin = new_coin
        self.symbol = f"{new_coin}USDT"
        
        # Переинициализация стратегии для новой монеты
        self.strategy = self._initialize_strategy()
        
        # Пересоздание торгового бота
        self.bot = TradingBot(
            strategy=self.strategy,
            symbol=self.symbol,
            interval=self.interval,
            controller=self
        )
        
        self.save_bot_state()
        log_maker(f"✅ Переключено на {new_coin}")

    def start(self):
        """Запуск торгового бота"""
        if self.thread and self.thread.is_alive():
            return
        self._running.set()
        self.thread = threading.Thread(target=self._run_bot_loop, daemon=True)
        self.thread.start()
        log_maker("▶️ Бот запущен")

    def stop(self):
        """Остановка торгового бота"""
        if self.thread:
            self._running.clear()
            self.thread.join(timeout=5)
        log_maker("⏹️ Бот остановлен")

    def status(self):
        """Статус работы бота"""
        return "running" if self._running.is_set() else "stopped"

    def _run_bot_loop(self):
        """Основной цикл работы бота"""
        while self._running.is_set():
            try:
                self.bot.run_once()
            except Exception as e:
                log_error(f"🚨 Критическая ошибка в основном цикле: {str(e)}")
                time.sleep(60)

# Глобальный экземпляр контроллера
bot_controller = BotController()