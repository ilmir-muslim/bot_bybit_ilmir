import pytest
from app.services.coin_selector import CoinSelector
from unittest.mock import MagicMock, patch
import numpy as np
import random

# Фиксируем seed для воспроизводимости
random.seed(42)
np.random.seed(42)

# SOL: Очень сильный тренд + умеренная волатильность
MOCK_CANDLES_SOL = [
    {'open': 100 + i*10, 'high': 110 + i*10, 'low': 90 + i*10, 'close': 105 + i*10, 'volume': 30000 + i*3000}
    for i in range(15)
]

# ADA: Очень низкая волатильность + слабый тренд
MOCK_CANDLES_ADA = [
    {'open': 50, 'high': 50.05, 'low': 49.95, 'close': 50.02, 'volume': 5000}
    for _ in range(15)
]

# DOGE: Умеренная волатильность + без тренда
MOCK_CANDLES_DOGE = [
    {
        'open': max(0.01, 0.1 + random.uniform(-0.05, 0.05)),
        'high': max(0.01, 0.1 + random.uniform(-0.05, 0.05) + 0.08),
        'low': max(0.01, 0.1 + random.uniform(-0.05, 0.05) - 0.08),
        'close': max(0.01, 0.1 + random.uniform(-0.05, 0.05)),
        'volume': 1000000 + random.randint(-300000, 300000)
    }
    for _ in range(15)
]

@pytest.fixture
def coin_selector():
    selector = CoinSelector(["SOL", "ADA", "DOGE"])
    return selector

def test_volatility_calculation(coin_selector):
    """Тест корректности расчета волатильности"""
    # Низкая волатильность
    closes_steady = [100, 100.5, 101, 100.75, 101.25, 101.5]
    vol_steady = coin_selector.calculate_volatility(closes_steady)
    
    # Высокая волатильность
    closes_volatile = [100, 115, 90, 120, 85, 100]  # Уменьшили размах
    vol_volatile = coin_selector.calculate_volatility(closes_volatile)
    
    # Проверяем соотношение
    assert vol_volatile > vol_steady * 10
    
    # Проверяем абсолютные значения
    assert 0.1 < vol_steady < 1.0  # ~0.5% волатильность
    assert 10 < vol_volatile < 25  # ~15% волатильность
    
    # Проверка защиты от деления на ноль
    closes_zero = [0, 0, 0, 0, 0]
    vol_zero = coin_selector.calculate_volatility(closes_zero)
    assert vol_zero == 0.0

def test_calculate_metrics(coin_selector):
    """Тест корректности расчета метрик"""
    with patch.object(coin_selector.bybit, 'get_candles', return_value=MOCK_CANDLES_SOL):
        metrics = coin_selector.calculate_metrics("SOLUSDT")
        
        assert metrics is not None
        assert metrics['volatility'] > 0.1
        assert metrics['trend_strength'] > 1.0
        assert metrics['volume_ratio'] > 1.0
        assert metrics['risk_reward'] > 0.1
        assert metrics['price'] == MOCK_CANDLES_SOL[-1]['close']

def test_evaluate_coins(coin_selector):
    """Тест оценки монет с разными характеристиками"""
    def side_effect(symbol, *args, **kwargs):
        if "SOL" in symbol:
            return MOCK_CANDLES_SOL
        elif "ADA" in symbol:
            return MOCK_CANDLES_ADA
        else:  # DOGE
            return MOCK_CANDLES_DOGE
    
    with patch.object(coin_selector.bybit, 'get_candles', side_effect=side_effect):
        scores = coin_selector.evaluate_coins()
        
        # Проверяем что SOL имеет наивысший балл
        assert len(scores) == 3
        
        # SOL должна иметь самую высокую оценку
        assert scores[0][0] == "SOL"
        
        # DOGE должна быть второй
        assert scores[1][0] == "DOGE"
        
        # ADA должна быть последней
        assert scores[2][0] == "ADA"
        
        # Разница между SOL и DOGE должна быть значительной
        assert scores[0][1] - scores[1][1] > 0.2

def test_get_best_coin(coin_selector):
    """Тест выбора лучшей монеты"""
    def side_effect(symbol, *args, **kwargs):
        if "SOL" in symbol:
            return MOCK_CANDLES_SOL
        elif "ADA" in symbol:
            return MOCK_CANDLES_ADA
        else:  # DOGE
            return MOCK_CANDLES_DOGE
    
    with patch.object(coin_selector.bybit, 'get_candles', side_effect=side_effect):
        best_coin = coin_selector.get_best_coin()
        assert best_coin == "SOL"

def test_normalization(coin_selector):
    """Тест нормализации значений"""
    # Создаем заведомо высокие метрики
    metrics = {
        'volatility': 5.0,
        'trend_strength': 2.0,
        'volume_ratio': 3.0,
        'risk_reward': 3.0,
        'price': 100,
        'atr': 3.0
    }
    
    # Ожидаемая оценка будет близка к 1.0
    expected_score = 0.95
    
    with patch.object(coin_selector, 'calculate_metrics', return_value=metrics):
        scores = coin_selector.evaluate_coins()
        
        assert scores[0][1] == pytest.approx(expected_score, abs=0.05)

def test_coin_with_insufficient_data(coin_selector):
    """Тест обработки монет с недостаточными данными"""
    def side_effect(symbol, *args, **kwargs):
        if "SOL" in symbol:
            return []  # Нет данных
        elif "ADA" in symbol:
            return MOCK_CANDLES_ADA[:5]  # Мало данных
        else:  # DOGE
            return MOCK_CANDLES_DOGE
    
    with patch.object(coin_selector.bybit, 'get_candles', side_effect=side_effect):
        scores = coin_selector.evaluate_coins()
        
        # Только DOGE должен быть в списке
        assert len(scores) == 1
        assert scores[0][0] == "DOGE"