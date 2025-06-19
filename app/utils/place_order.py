import json
import os
from datetime import datetime, timezone
from pybit.unified_trading import HTTP


LOG_PATH = "logs/order_failures.json"


def log_order_failure(context: dict):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **context
    }
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")


def safe_place_order(
    client: HTTP,
    symbol: str,
    side: str,
    qty: str,
    order_type: str = "Market",
    category: str = "spot"
) -> dict | None:
    payload = {
        "category": category,
        "symbol": symbol,
        "side": side.upper(),
        "order_type": order_type,
        "qty": qty,
    }

    # Попытка №1 — с accountType="SPOT"
    try:
        print("[TRY] Ордер с accountType='SPOT'")
        response = client.place_order(**payload, accountType="SPOT")
        if response["retCode"] == 0:
            print("[SUCCESS] Ордер прошёл с accountType='SPOT'")
            return response
        print(f"[FAILURE] retCode: {response['retCode']} — {response['retMsg']}")
    except Exception as e:
        print(f"[ERROR] ИСКЛЮЧЕНИЕ с accountType='SPOT': {e}")
        log_order_failure({
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "category": category,
            "accountType": "SPOT",
            "error": str(e)
        })

    # Попытка №2 — без accountType
    try:
        print("[TRY] Ордер без accountType")
        response = client.place_order(**payload)
        if response["retCode"] == 0:
            print("[SUCCESS] Ордер прошёл без accountType")
            return response
        print(f"[FAILURE] retCode: {response['retCode']} — {response['retMsg']}")
    except Exception as e:
        print(f"[ERROR] ИСКЛЮЧЕНИЕ без accountType: {e}")
        log_order_failure({
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "category": category,
            "accountType": "UNSPECIFIED",
            "error": str(e)
        })

    return None
