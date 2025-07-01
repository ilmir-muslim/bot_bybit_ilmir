import numpy as np
import time
from app.strategies.base import Strategy
from app.strategies.ma_crossover import MovingAverageStrategy
from app.utils.log_helper import log_maker
from app.strategies.neural_network.model import NeuralPredictor

class NeuralStrategy(Strategy):
    def __init__(
        self, 
        symbol: str, 
        bybit_service, 
        model_path: str = "models/neural_model",
        base_threshold: float = 0.25,
        volatility_factor: float = 0.5,
        rotator=None,
        trading_system=None,
        interval: str = "5"
    ):
        coin = symbol.replace('USDT', '')
        self.symbol = symbol
        self.bybit = bybit_service
        self.position_coin = coin
        
        model_base_path = f"models/{coin}_neural_model"
        
        self.base_threshold = base_threshold
        self.volatility_factor = volatility_factor
        self.predictor = NeuralPredictor(
            sequence_length=30,  
            prediction_steps=3
        )
        self.rotator = rotator
        self.trading_system = trading_system
        self.interval = interval 
        
        try:
            self.predictor.load(model_base_path)
            log_maker(f"🧠 Нейросетевая модель загружена из {model_base_path}")
            log_maker(f"  • Длина последовательности: {self.predictor.sequence_length} свечей")
            log_maker(f"  • Прогноз на шагов: {self.predictor.prediction_steps}")
            log_maker(f"  • Базовый порог: {base_threshold:.1f}%, Коэф. волатильности: {volatility_factor}")
        except Exception as e:
            log_maker(f"🔥 Критическая ошибка инициализации стратегии: {e}")
            # Fallback на MA стратегию
            self.strategy = MovingAverageStrategy(
                symbol, 
                "3", 
                rotator=rotator,
                trading_system=trading_system
            )
        
        self.min_order_qty = bybit_service.get_min_order_qty(symbol)
        log_maker(f"  • Минимальный лот: {self.min_order_qty}")
        self.last_candle_time = 0

    def calculate_volatility(self, candles: list, lookback: int = 20) -> float:
        ranges = []
        for i in range(-lookback, 0):
            candle = candles[i]
            candle_range = (candle['high'] - candle['low']) / candle['close']
            ranges.append(candle_range)
        return np.mean(ranges) * 100

    def should_trade(self, candles: list) -> str:
        if not hasattr(self, 'rotator') or self.rotator is None:
            return log_maker("⚠️ Rotator не инициализирован в стратегии")

        # Убрали фильтр объема свечи
        # Сохранили проверку конфликта монет
        current_coin = self.symbol.replace('USDT', '')
        if current_coin != self.position_coin:
            return log_maker(f"⚠️ Конфликт монет: стратегия {current_coin} vs состояние {self.position_coin}")
            
        # Проверка минимальной длины данных
        if len(candles) < self.predictor.sequence_length:
            return log_maker(f"🧠⚠️ Недостаточно данных: {len(candles)} < {self.predictor.sequence_length}")
            
            
        try:
            # Основной блок анализа
            start_time = time.time()
            current_price = self.bybit.get_reliable_price(self.symbol)
            if current_price is None:
                return log_maker("❌ Не удалось получить текущую цену")
                
                
            volatility = self.calculate_volatility(candles)
            adaptive_threshold = self.base_threshold + (volatility * self.volatility_factor)
            buy_threshold = adaptive_threshold
            sell_threshold = -adaptive_threshold
            
            data = np.array([
                [c['open'], c['high'], c['low'], c['close'], c['volume']] 
                for c in candles[-self.predictor.sequence_length:]
            ])
            
            predictions = self.predictor.predict(data)
            predicted_changes = []
            prediction_details = []
            
            for i, pred_price in enumerate(predictions, 1):
                change = (pred_price - current_price) / current_price * 100
                predicted_changes.append(change)
                prediction_details.append({
                    "step": i,
                    "price": pred_price,
                    "change_pct": change
                })
            
            max_change = max(predicted_changes, key=abs) if predicted_changes else 0
            signal = None
            reason = ""
            
            if max_change > buy_threshold:
                signal = "BUY"
                reason = f"рост +{max_change:.2f}% > порога {buy_threshold:.2f}%"
            elif max_change < sell_threshold:
                signal = "SELL"
                reason = f"падение {max_change:.2f}% < порога {sell_threshold:.2f}%"
            
            predictions_str = "\n ".join(
                [f"{p['step']} шаг: {p['change_pct']:+.2f}%" 
                for p in prediction_details]
            )
            
            # Формируем лог ВСЕГДА
            analysis_time = time.time() - start_time
            log_text = (
                f"🧠 Анализ {self.symbol} | Цена: {current_price:.4f} | Волатильность: {volatility:.2f}%\n"
                f"  • Адаптивные пороги: BUY > {buy_threshold:.2f}%, SELL < {sell_threshold:.2f}%\n"
                f"  • Прогнозы: {predictions_str}\n"
                f"  • Макс. изменение: {max_change:+.2f}% ({reason})\n"
                f"  • Решение: {'СИГНАЛ ' + signal if signal else 'НЕТ СИГНАЛА'}\n"
                f"  • Время анализа: {analysis_time:.2f} сек"
            )
            
            # Проверяем баланс для рекомендаций
            coin = self.symbol.replace('USDT', '')
            position_qty = self.bybit.get_balance(coin)
            
            # Добавляем рекомендации по пропуску (не блокируем сигнал)
            if signal == "SELL" and position_qty < self.min_order_qty:
                log_text += f"\n  • 🧠⏩ Рекомендация: Пропуск SELL (позиция {position_qty} < {self.min_order_qty})"
                
            if signal == "BUY" and position_qty >= self.min_order_qty:
                log_text += f"\n  • 🧠⏩ Рекомендация: Пропуск BUY (уже есть позиция {position_qty})"
                
            log_maker(log_text)
            
            # Возвращаем сигнал независимо от позиции
            return signal
                
        except Exception as e:
            log_maker(f"🧠❌ Критическая ошибка нейросети: {str(e)}")
            import traceback
            return log_maker(f"Трейсбек: {traceback.format_exc()}")
            

    def execute_trade(self, action: str, executor):
        if action == "BUY":
            log_maker(f"🧠🟢 Исполняю BUY по {self.symbol}")
            executor.execute_buy(trading_system=self.trading_system)
        elif action == "SELL":
            log_maker(f"🧠🔴 Исполняю SELL по {self.symbol}")
            executor.execute_sell(strategy=self)