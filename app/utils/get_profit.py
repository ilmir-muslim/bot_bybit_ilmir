import time
import hmac
import hashlib
import requests
from datetime import datetime, timedelta
import urllib.parse

class ProfitCalculator:
    def __init__(self, api_key, api_secret):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://api.bybit.com"
        self.recv_window = "5000"

    def _generate_signature(self, params):
        timestamp = str(int(time.time() * 1000))
        encoded_params = urllib.parse.urlencode(params, doseq=True)
        sign_str = timestamp + self.api_key + self.recv_window + encoded_params
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            sign_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return timestamp, signature

    def get_balance_history(self, days=1, coin="USDT", account_type="UNIFIED", limit=50):
        end_time = int(datetime.now().timestamp() * 1000)
        start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
        
        params = {
            "accountType": account_type,
            "startTime": start_time,
            "endTime": end_time,
            "limit": limit,
            "coin": coin
        }
        
        timestamp, signature = self._generate_signature(params)
        
        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-SIGN": signature,
            "X-BAPI-RECV-WINDOW": self.recv_window,
        }
        
        endpoint = "/v5/account/transaction-log"
        url = f"{self.base_url}{endpoint}"
        response = requests.get(url, params=params, headers=headers)
        
        return response.json()

    def calculate_profit(self, history):
        if not history or history.get("retCode") != 0:
            return 0.0, 0.0

        transactions = history.get("result", {}).get("list", [])
        today = datetime.now().date()
        month_start = today.replace(day=1)
        
        profit_today = 0.0
        profit_month = 0.0
        
        for tx in transactions:
            if tx.get("currency") == "USDT" and tx.get("type") == "TRADE":
                tx_time = int(tx.get("transactionTime", 0)) / 1000
                if tx_time == 0:
                    continue
                    
                tx_date = datetime.fromtimestamp(tx_time).date()
                change = float(tx.get("change", 0))
                
                # Учитываем комиссию
                if tx.get("fee") and tx["fee"] != "0":
                    fee = float(tx["fee"])
                    change -= fee
                    
                profit_month += change
                if tx_date == today:
                    profit_today += change
                    
        return profit_today, profit_month