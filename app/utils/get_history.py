import requests
import pandas as pd
import json

def fetch_bybit_ohlcv_15m(symbol="SOLUSDT", category="spot"):
    url = "https://api.bybit.com/v5/market/kline"
    params = {
        "category": category,
        "symbol": symbol,
        "interval": "15m",
        "limit": 96
    }

    response = requests.get(url, params=params)
    data = response.json()

    if data["retCode"] != 0:
        raise Exception(f"API error: {data['retMsg']}")

    raw = data["result"]["list"]

    if not raw:
        print("❌ No data returned. Check symbol and category.")
        return pd.DataFrame()

    # Сохраняем в файл (в порядке по убыванию времени)
    with open(f"ohlcv_{symbol}.json", "w") as f:
        json.dump(raw, f, indent=2)

    # Парсинг и сортировка по времени (по возрастанию)
    df = pd.DataFrame(raw, columns=[
        "timestamp", "open", "high", "low", "close", "volume", "_1", "_2"
    ])

    df = df.astype({
        "timestamp": "int64",
        "open": "float",
        "high": "float",
        "low": "float",
        "close": "float",
        "volume": "float"
    })

    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    df = df.sort_values("timestamp").reset_index(drop=True)

    return df

# 🧪 Пример запуска
if __name__ == "__main__":
    df = fetch_bybit_ohlcv_15m("SOLUSDT", "spot")
    if not df.empty:
        print(df.tail())
