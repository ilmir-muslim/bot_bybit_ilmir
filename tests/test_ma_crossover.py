import pytest
from app.strategies.ma_crossover import MovingAverageStrategy


def test_calculate_atr():
    strategy = MovingAverageStrategy("BTCUSDT")

    candles = [
        {"high": 105, "low": 100, "close": 102},
        {"high": 108, "low": 101, "close": 107},  # TR = max(7, 6, 6) = 7
        {"high": 110, "low": 106, "close": 108},  # TR = max(4, 3, 2) = 4
    ]

    atr = strategy._calculate_atr(candles)
    expected_trs = [7, 4]
    expected_atr = sum(expected_trs) / len(expected_trs)

    assert abs(atr - expected_atr) < 1e-6, f"Expected {expected_atr}, got {atr}"


def test_calculate_ema():
    strategy = MovingAverageStrategy("BTCUSDT")
    closes = [10, 11, 12, 13, 14, 15, 16]
    ema = strategy._calculate_ema(closes, window=3)

    # Проверим, что EMA ближе к последнему значению, чем к среднему
    assert ema > sum(closes[-3:]) / 3
    assert ema <= closes[-1]


def test_should_trade_buy_signal(monkeypatch):
    strategy = MovingAverageStrategy("BTCUSDT", short_window=2, long_window=4)

    # Подменяем get_price
    monkeypatch.setattr(strategy.bybit, "get_price", lambda symbol: 105.0)
    monkeypatch.setattr(strategy, "_get_last_buy_price", lambda last_action=None: None)

    # Сгенерируем свечи так, чтобы short EMA > long EMA
    candles = [
        {"high": 100, "low": 95, "close": 96},
        {"high": 101, "low": 96, "close": 97},
        {"high": 102, "low": 97, "close": 98},
        {"high": 104, "low": 98, "close": 100},
        {"high": 106, "low": 100, "close": 104},  # резкий рост
    ]

    action = strategy.should_trade(candles)
    assert action == "BUY", f"Expected BUY signal, got {action}"


def test_should_trade_insufficient_data():
    strategy = MovingAverageStrategy("BTCUSDT", short_window=5, long_window=10)

    # Меньше long_window — сигналов быть не должно
    candles = [{"high": 100, "low": 95, "close": 97}] * 8
    action = strategy.should_trade(candles)

    assert action is None
