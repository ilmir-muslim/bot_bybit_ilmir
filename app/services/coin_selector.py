import numpy as np
from app.services.bybit_service import BybitService
from app.utils.log_helper import log_maker
from typing import Dict, List, Optional, Tuple
import math
import concurrent.futures
import time

class CoinSelector:
    def __init__(self, coin_list: List[str]):
        self.coin_list = coin_list
        self.bybit = BybitService()
        self.cache: Dict[str, dict] = {}
        self.timeout = 25  # Увеличим таймаут до 25 секунд
        self.max_workers = 4  # Оптимальное количество потоков
        self.last_update = 0
        self.update_interval = 3600  # Обновлять данные раз в час
        
    def calculate_volatility(self, closes: List[float]) -> float:
        """Рассчитывает волатильность как стандартное отклонение процентных изменений"""
        if len(closes) < 2:
            return 0.0
            
        # Рассчитываем процентные изменения
        returns = []
        for i in range(1, len(closes)):
            if closes[i-1] != 0:  # Защита от деления на ноль
                ret = (closes[i] - closes[i-1]) / closes[i-1]
                returns.append(ret)
        
        if len(returns) < 2:
            return 0.0
            
        # Возвращаем стандартное отклонение в процентах
        return np.std(returns) * 100
        
    def sigmoid_normalize(self, value: float, midpoint: float, steepness: float = 10) -> float:
        """Нормализует значение через сигмоиду с защитой от переполнения"""
        try:
            x = steepness * (value - midpoint)
            # Защита от слишком больших значений
            if x > 100:
                return 1.0
            elif x < -100:
                return 0.0
            return 1 / (1 + math.exp(-x))
        except:
            return 0.5  # Возвращаем нейтральное значение при ошибке
        
    def calculate_metrics(self, symbol: str) -> Optional[dict]:
        """Рассчитывает метрики для одной монеты с повторными попытками"""
        for attempt in range(3):  # 3 попытки
            try:
                # Получаем свечи за последние 4 часа (15-минутные)
                candles = self.bybit.get_candles(symbol, interval="15", limit=16)
                
                if not candles or len(candles) < 15:
                    if attempt == 2:  # Последняя попытка
                        log_maker(f"⚠️ Недостаточно данных для {symbol}")
                        return None
                    time.sleep(2)  # Пауза перед повторной попыткой
                    continue
                    
                closes = [c['close'] for c in candles]
                volumes = [c['volume'] for c in candles]
                highs = [c['high'] for c in candles]
                lows = [c['low'] for c in candles]
                
                # Рассчитываем показатели
                volatility = self.calculate_volatility(closes)
                
                # Тренд (наклон линии регрессии)
                x = np.arange(len(closes))
                slope = np.polyfit(x, closes, 1)[0]
                mean_price = np.mean(closes)
                trend_strength = (slope / mean_price) * 100 if mean_price != 0 else 0
                
                # Отношение объема к среднему
                if len(volumes) >= 5:
                    avg_volume = np.mean(volumes[-5:])
                    volume_ratio = volumes[-1] / avg_volume if avg_volume != 0 else 1.0
                else:
                    volume_ratio = 1.0
                
                # ATR (Average True Range)
                atr = self._calculate_atr(highs, lows, closes)
                
                # Соотношение риск/прибыль (на основе ATR)
                risk_reward = (atr / closes[-1]) * 100 if closes[-1] != 0 else 0
                
                return {
                    'volatility': volatility,
                    'trend_strength': trend_strength,
                    'volume_ratio': volume_ratio,
                    'risk_reward': risk_reward,
                    'price': closes[-1],
                    'atr': atr
                }
                
            except Exception as e:
                if attempt == 2:  # Последняя попытка
                    log_maker(f"🔥 Ошибка расчета метрик для {symbol}: {str(e)}")
                    return None
                time.sleep(1)  # Пауза перед повторной попыткой
    
    def _calculate_atr(self, highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
        """Расчет Average True Range"""
        if len(highs) < period or len(closes) < 2:
            return 0.0
        
        tr_values = []
        for i in range(1, len(highs)):
            tr1 = highs[i] - lows[i]
            tr2 = abs(highs[i] - closes[i-1])
            tr3 = abs(lows[i] - closes[i-1])
            tr = max(tr1, tr2, tr3)
            tr_values.append(tr)
        
        return np.mean(tr_values[-period:]) if tr_values else 0.0
    
    def evaluate_coins(self) -> List[Tuple[str, float]]:
        """Оценивает все монеты с использованием параллельных запросов"""
        # Используем кэш, если данные не устарели
        current_time = time.time()
        if current_time - self.last_update < self.update_interval:
            return self._get_cached_scores()
        
        scores = []
        self.cache = {}  # Очищаем кэш перед обновлением
        
        # Используем ThreadPoolExecutor для параллельных запросов
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_coin = {
                executor.submit(self._evaluate_coin, coin): coin
                for coin in self.coin_list
            }
            
            for future in concurrent.futures.as_completed(future_to_coin, timeout=self.timeout):
                coin = future_to_coin[future]
                try:
                    # Добавляем таймаут для каждого future
                    result = future.result(timeout=15)
                    if result:
                        scores.append(result)
                except Exception as e:
                    # Логируем только серьезные ошибки
                    if "Not supported symbols" not in str(e):
                        log_maker(f"⚠️ Ошибка оценки {coin}: {str(e)}")
                    else:
                        # Для "Not supported symbols" просто возвращаем 0 оценку
                        scores.append((coin, 0.0))
        
        # Сортируем по убыванию оценки
        scores.sort(key=lambda x: x[1], reverse=True)
        self.last_update = current_time
        return scores
    
    def _get_cached_scores(self) -> List[Tuple[str, float]]:
        """Возвращает оценки из кэша"""
        scores = []
        for coin in self.coin_list:
            if coin in self.cache:
                scores.append((coin, self.cache[coin]['score']))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores
    
    def _evaluate_coin(self, coin: str) -> Optional[Tuple[str, float]]:
        """Внутренний метод для оценки одной монеты"""
        symbol = f"{coin}USDT"
        metrics = self.calculate_metrics(symbol)
        
        if not metrics:
            return None
            
        # Весовые коэффициенты
        weights = {
            'volatility': 0.4,
            'trend_strength': 0.3,
            'volume_ratio': 0.2,
            'risk_reward': 0.1
        }
        
        # Нормализация значений через сигмоиду
        normalized = {
            'volatility': self.sigmoid_normalize(metrics['volatility'], 1.0),
            'trend_strength': self.sigmoid_normalize(metrics['trend_strength'], 0.5),
            'volume_ratio': min(max(metrics['volume_ratio'], 0.5), 3.0) / 3.0,
            'risk_reward': self.sigmoid_normalize(metrics['risk_reward'], 1.0)
        }
        
        # Рассчет итоговой оценки
        score = sum(normalized[k] * weights[k] for k in weights)
        
        # Кэшируем результаты
        self.cache[coin] = {
            'metrics': metrics,
            'score': score,
            'normalized': normalized,
            'timestamp': time.time()
        }
        
        return (coin, score)
    
    def get_best_coin(self) -> Optional[str]:
        """Возвращает лучшую монету для торговли"""
        scores = self.evaluate_coins()
        if not scores:
            return None
        return scores[0][0]
    
    def get_coin_report(self, coin: str) -> Optional[dict]:
        """Возвращает детальный отчет по монете"""
        return self.cache.get(coin)