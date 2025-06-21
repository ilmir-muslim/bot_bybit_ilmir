import pytest
from decimal import Decimal
from app.trader import round_qty, validate_qty_precision

# Мокаем зависимости вручную, если BybitService недоступен в тесте
class DummyBybitService:
    def get_qty_precision(self, symbol):
        return {"BTCUSDT": 3, "DOGEUSDT": 0}.get(symbol, 2)

# Мокаем оригинальный bybit
import app.trader
app.trader.bybit = DummyBybitService()


def test_round_qty():
    assert round_qty(0.123456, 3) == 0.123
    assert round_qty(57.891, 0) == 57.0
    assert round_qty(1.9999, 2) == 1.99


def test_validate_qty_precision_valid():
    validate_qty_precision("BTCUSDT", 0.123)
    validate_qty_precision("DOGEUSDT", 57)  # заменено с 57.0 на 57
    validate_qty_precision("DOGEUSDT", Decimal("57"))  # допустимо


def test_validate_qty_precision_invalid():
    with pytest.raises(ValueError) as e:
        validate_qty_precision("BTCUSDT", 0.12345)
    assert "qty=0.12345 содержит" in str(e.value)

    with pytest.raises(ValueError) as e2:
        validate_qty_precision("DOGEUSDT", 57.8)
    assert "qty=57.8 содержит" in str(e2.value)
