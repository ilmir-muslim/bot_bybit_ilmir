import time
import hmac
import hashlib
import requests
from datetime import datetime, timedelta
import urllib.parse
import json  # Добавлен для отладки

from app.config import BYBIT_API_KEY, BYBIT_API_SECRET

class BybitAccount:
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://api.bybit.com"
        self.recv_window = "5000"

    def _generate_signature(self, params):
        timestamp = str(int(time.time() * 1000))
        
        # Кодируем параметры
        encoded_params = urllib.parse.urlencode(params, doseq=True)
        
        # Формируем строку для подписи
        sign_str = timestamp + self.api_key + self.recv_window + encoded_params
        
        # Генерация подписи
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            sign_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return timestamp, signature, sign_str

    def get_balance_history(self, days=7, coin=None, account_type="UNIFIED", sub_uid=None):
        """Получить историю изменений баланса"""
        # Рассчитываем временной диапазон
        end_time = int(datetime.now().timestamp() * 1000)
        start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
        
        # Параметры запроса
        params = {
            "accountType": account_type,
            "startTime": str(start_time),
            "endTime": str(end_time),
            "limit": "50"
        }
        
        if coin:
            params["coin"] = coin.upper()
            
        # Добавляем sub_uid если указан (для субаккаунтов)
        if sub_uid:
            params["subMemberId"] = str(sub_uid)
        
        # Генерируем подпись и временную метку
        timestamp, signature, sign_str = self._generate_signature(params)
        
        # Заголовки запроса
        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-SIGN": signature,
            "X-BAPI-RECV-WINDOW": self.recv_window,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # Формируем URL
        endpoint = "/v5/account/transaction-log"
        if account_type == "CONTRACT":
            endpoint = "/v5/account/contract-transaction-log"
        
        url = self.base_url + endpoint
        
        # Формируем строку запроса
        query_string = urllib.parse.urlencode(params, doseq=True)
        full_url = f"{url}?{query_string}"
        
        # Отправляем запрос
        response = requests.get(full_url, headers=headers)
        
        # Возвращаем как словарь для гибкости
        return response.json()

    def print_balance_history(self, history):
        """Красиво отображаем историю изменений баланса"""
        if not history:
            print("Пустой ответ от сервера")
            return
            
        if history.get("retCode") != 0:
            msg = history.get("retMsg", "Неизвестная ошибка")
            print(f"Ошибка API: {msg} (код {history.get('retCode', 'N/A')}")
            return
        
        # Сохраняем сырой ответ для анализа
        with open("bybit_raw_response.json", "w") as f:
            json.dump(history, f, indent=2)
        print("Сохранен сырой ответ в bybit_raw_response.json")
        
        result = history.get("result", {})
        transactions = result.get("list", [])
        
        if not transactions:
            print("Нет данных за указанный период")
            return
        
        print(f"\nНайдено операций: {len(transactions)}")
        print("-" * 80)
        
        for i, tx in enumerate(transactions):
            # Временное решение для отображения валюты
            coin = "USDT"  # По умолчанию, так как мы фильтровали по USDT
            
            # Пытаемся получить валюту из разных источников
            possible_coin_fields = ["coin", "currency", "feeCoin", "feeCurrency"]
            for field in possible_coin_fields:
                if field in tx:
                    coin = tx[field]
                    break
            
            # Получаем сумму изменения баланса
            amount = float(tx.get("change", tx.get("amount", 0)))
            
            # Получаем комиссию
            fee = 0.0
            if "fee" in tx:
                fee = float(tx["fee"])
            elif "tradeFee" in tx and isinstance(tx["tradeFee"], list):
                # Обработка структуры с комиссиями
                for fee_item in tx["tradeFee"]:
                    fee += float(fee_item.get("fee", 0))
            
            # Определяем тип операции
            tx_type = tx.get("type", "UNKNOWN")
            
            # Получаем время операции
            timestamp = 0
            time_fields = ["time", "execTime", "createdAt", "transactionTime"]
            for field in time_fields:
                if field in tx:
                    timestamp = int(tx[field]) / 1000
                    break
            
            # Форматируем время
            if timestamp > 0:
                time_str = datetime.fromtimestamp(timestamp).strftime('%d.%m.%Y %H:%M')
            else:
                time_str = "N/A"
                
            # Определение типа операции
            operation_types = {
                "Transfer": "Перевод",
                "RealisedPNL": "Реализованный PnL",
                "Commission": "Комиссия",
                "Refund": "Возврат",
                "Prize": "Награда",
                "FundingFee": "Финансирование",
                "Deposit": "Депозит",
                "Withdraw": "Вывод средств",
                "TRADE": "Торговая операция"
            }
            
            op_type = operation_types.get(tx_type, tx_type)
            
            # Форматирование суммы
            amount_str = f"{amount:+,.8f} {coin}"
            if amount >= 0:
                amount_str = f"\033[92m{amount_str}\033[0m"  # Зеленый для положительных
            else:
                amount_str = f"\033[91m{amount_str}\033[0m"  # Красный для отрицательных
            
            print(f"[{time_str}] {op_type}: {amount_str}")
            
            if fee > 0:
                # Пытаемся получить валюту комиссии
                fee_coin = coin
                if "feeCoin" in tx:
                    fee_coin = tx["feeCoin"]
                elif "feeCurrency" in tx:
                    fee_coin = tx["feeCurrency"]
                
                print(f"    Комиссия: {fee:.8f} {fee_coin}")
            
            # Выводим все доступные поля для анализа
            print(f"    Тип: {tx_type}")
            print(f"    ID: {tx.get('id', 'N/A')}")
            print(f"    Статус: {tx.get('status', 'N/A')}")
            
            # Для торговых операций выводим дополнительную информацию
            if tx_type == "TRADE":
                print(f"    Символ: {tx.get('symbol', 'N/A')}")
                print(f"    Размер: {tx.get('qty', 'N/A')}")
                print(f"    Цена: {tx.get('price', 'N/A')}")
            
            print("-" * 80)

# ======== КОНФИГУРАЦИЯ ========
API_KEY = BYBIT_API_KEY
API_SECRET = BYBIT_API_SECRET
ACCOUNT_TYPE = "UNIFIED"         # "UNIFIED" или "CONTRACT"
COIN = "USDT"                    # Валюта для фильтра (None - все валюты)
DAYS = 7                         # Количество дней истории
# ==============================

if __name__ == "__main__":
    print("Инициализация аккаунта Bybit...")
    account = BybitAccount(API_KEY, API_SECRET)
    
    print(f"\nЗапрос истории баланса за {DAYS} дней (аккаунт: {ACCOUNT_TYPE}, валюта: {COIN})...")
    
    # Получаем историю
    try:
        history = account.get_balance_history(
            days=DAYS,
            coin=COIN,
            account_type=ACCOUNT_TYPE
        )
    except Exception as e:
        print(f"Ошибка при выполнении запроса: {str(e)}")
        exit(1)
    
    # Выводим результат
    account.print_balance_history(history)
    print("\nАнализ завершен. Для детального изучения структуры данных")
    print("проверьте файл bybit_raw_response.json")