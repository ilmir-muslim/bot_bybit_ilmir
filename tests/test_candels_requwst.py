def test_candle_parsing():
    from app.services.bybit_service import BybitService
    sample_data = {
        "retCode": 0,
        "result": {
            "list": [
                ["1751256300000", "151.89", "151.94", "151.89", "151.93", "140.796", "21388.29436"]
            ]
        }
    }
    
    bybit = BybitService()
    # Метод для тестирования (сделайте parse_candles публичным для тестов)
    candles = bybit.get_candles("SOLUSDT", 5, 1)  
    
    assert len(candles) == 1
    assert candles[0]["volume"] == 140.796