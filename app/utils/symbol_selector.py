# app/services/symbol_selector.py
import numpy as np
from app.services.bybit_service import BybitService
from app.strategies.ma_crossover import MovingAverageStrategy
from app.utils.log_helper import log_maker

class SymbolSelector:
    def __init__(self, symbols: list, volatility_window: int = 24):
        self.symbols = symbols
        self.window = volatility_window
        self.bybit = BybitService()
        self.strategies = {s: MovingAverageStrategy(s) for s in symbols}
        self.scores = {}  # Для хранения текущих баллов
        
    def calculate_volatility_score(self, symbol: str) -> float:
        """Оценка привлекательности монеты 0-100 баллов"""
        candles = self.bybit.get_candles(symbol, "60", limit=self.window)
        if not candles:
            return 0
            
        # 1. Историческая волатильность
        closes = [c['close'] for c in candles]
        if len(closes) < 2:
            return 0
            
        returns = np.diff(np.log(closes))
        volatility = np.std(returns) * 100 if returns else 0
        
        # 2. Объемы
        volumes = [c['volume'] for c in candles[-6:]]
        if not volumes:
            volume_ratio = 1
        else:
            min_vol = min(volumes) if min(volumes) > 0 else 1
            volume_ratio = max(volumes) / min_vol
        
        # 3. Текущий тренд (EMA slope)
        try:
            strategy = self.strategies[symbol]
            strategy.should_trade(candles)  # обновляем состояние EMA
            if strategy.prev_medium_ema and strategy.prev_medium_ema > 0:
                slope = (strategy.prev_short_ema - strategy.prev_medium_ema) / strategy.prev_medium_ema
            else:
                slope = 0
        except Exception as e:
            log_maker(f"⚠️ Ошибка расчета тренда для {symbol}: {e}")
            slope = 0
        
        # Композитный балл
        return (volatility * 70) + (volume_ratio * 20) + (abs(slope) * 1000 * 10)

    def select_best_symbol(self, current_symbol: str = None):
        """Выбор символа с повышающим коэффициентом для текущего"""
        scores = {}
        for symbol in self.symbols:
            try:
                score = self.calculate_volatility_score(symbol)
                
                # Повышаем бал текущего символа на 10%
                if symbol == current_symbol:
                    score *= 1.1
                    
                scores[symbol] = score
            except Exception as e:
                log_maker(f"⚠️ Ошибка оценки {symbol}: {e}")
                scores[symbol] = 0
        
        self.scores = scores  # Сохраняем для использования в боте
        best_symbol = max(scores, key=scores.get)
        return best_symbol, scores[best_symbol]