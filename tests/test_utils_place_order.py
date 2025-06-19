import os
import json
import tempfile
from datetime import datetime, timezone

from app.utils.place_order import log_order_failure


def test_log_order_failure_creates_log_entry():
    # Временный путь к файлу
    with tempfile.TemporaryDirectory() as tmpdir:
        test_log_path = os.path.join(tmpdir, "order_failures.json")
        
        # Мокаем путь к файлу
        from app.utils import place_order
        place_order.LOG_PATH = test_log_path

        context = {
            "symbol": "BTCUSDT",
            "side": "BUY",
            "qty": "0.001",
            "category": "spot",
            "accountType": "SPOT",
            "error": "Test error"
        }

        # Запуск логгера
        log_order_failure(context)

        # Проверка — файл существует
        assert os.path.exists(test_log_path)

        # Читаем первую (и единственную) строку
        with open(test_log_path, "r", encoding="utf-8") as f:
            line = f.readline()
            log_data = json.loads(line)

        # Проверка структуры
        assert "timestamp" in log_data
        assert log_data["symbol"] == "BTCUSDT"
        assert log_data["error"] == "Test error"

        # Проверка корректности формата времени
        ts = datetime.fromisoformat(log_data["timestamp"])
        assert ts.tzinfo is not None  # Должна быть временная зона (UTC)
