#!/usr/bin/env python3
import os
import sys

def load_coin_list(file_path: str) -> list:
    """Загружает список монет из файла"""
    try:
        with open(file_path, 'r') as f:
            return [line.strip().upper() for line in f if line.strip()]
    except Exception as e:
        print(f"❌ Ошибка загрузки списка монет: {e}")
        return ["SOL", "ARB", "BTC"]  # Значения по умолчанию

def check_models(coin_list):
    print("🔍 Проверка моделей:")
    missing = []
    
    for coin in coin_list:
        model_path = f"models/{coin}_neural_model.keras"
        scaler_path = f"models/{coin}_neural_model_scaler.npz"
        
        exists = os.path.exists(model_path) and os.path.exists(scaler_path)
        status = "✅" if exists else "❌"
        
        print(f"{status} {coin}:")
        print(f"  • Модель: {model_path}")
        print(f"  • Скалер: {scaler_path}")
        
        if not exists:
            missing.append(coin)
    
    if missing:
        print("\n⚠️ Отсутствуют модели для:")
        for coin in missing:
            print(f"  • {coin}")
        print("\nЗапустите обучение:")
        for coin in missing:
            print(f"  python app/strategies/neural_network/trainer.py --symbol={coin}USDT --model_path=models/{coin}_neural_model")
    else:
        print("\n🎉 Все модели доступны и готовы к работе!")

if __name__ == "__main__":
    # Загружаем список монет из файла
    coin_file = "coins_list.txt"
    coins = load_coin_list(coin_file)
    print(f"📋 Загружено монет: {len(coins)} из {coin_file}")
    
    check_models(coins)