# ===== ./app/trader/data_provider.py =====
from app.services.bybit_service import BybitService
from app.utils.log_helper import log_maker

class DataProvider:
    def __init__(self, symbol: str, interval: str):
        self.symbol = symbol
        self.interval = interval
        self.bybit = BybitService()
        self.controller = None
    
    def get_candles(self, limit: int = 200):
        # Используем предзагруженные данные если доступны
        if self.controller and hasattr(self.controller, 'preloaded_data'):
            coin = self.symbol.replace('USDT', '')
            if coin in self.controller.preloaded_data:
                preloaded = self.controller.preloaded_data[coin]
                if len(preloaded) >= limit:
                    return preloaded[-limit:]
        
        # Если нет предзагруженных данных, загружаем из API
        try:
            candles = self.bybit.get_candles(
                self.symbol, 
                interval=self.interval, 
                limit=limit
            )
            
            if len(candles) < limit // 2:
                log_maker(f"⚠️ Получено недостаточно свечей: {len(candles)} из {limit}")
                
            return candles
        except Exception as e:
            log_maker(f"🔥 Ошибка получения данных: {e}")
            return []