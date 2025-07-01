import pytest
from app.services.coin_selector import CoinSelector
import time
import logging

# Настройка логгера
logger = logging.getLogger(__name__)

# Список монет для тестирования
REAL_COINS = ["BTC", "ETH", "SOL", "ADA", "DOGE"]

@pytest.fixture(scope="module")
def coin_selector():
    return CoinSelector(REAL_COINS)

def test_real_data_loading(coin_selector):
    """Тест загрузки реальных данных с биржи"""
    logger.info("🔄 Тестирование с реальными данными с биржи Bybit...")
    
    # Для каждой монеты получаем метрики
    for coin in REAL_COINS:
        symbol = f"{coin}USDT"
        start_time = time.time()
        metrics = coin_selector.calculate_metrics(symbol)
        duration = time.time() - start_time
        
        assert metrics is not None, f"Не удалось получить данные для {symbol}"
        logger.info(f"✅ {symbol} данные получены за {duration:.2f} сек")
        
        # Проверяем основные метрики
        assert metrics['volatility'] > 0, f"Волатильность должна быть > 0 для {symbol}"
        assert metrics['trend_strength'] != 0, f"Тренд не должен быть нулевым для {symbol}"
        assert metrics['volume_ratio'] > 0, f"Объем не должен быть нулевым для {symbol}"
        
        logger.info(f"  Волатильность: {metrics['volatility']:.2f}%")
        logger.info(f"  Сила тренда: {metrics['trend_strength']:.2f}%")
        logger.info(f"  Отношение объема: {metrics['volume_ratio']:.2f}x")
        logger.info(f"  Риск/прибыль: {metrics['risk_reward']:.2f}%")

def test_real_coin_evaluation(coin_selector):
    """Тест оценки монет на реальных данных"""
    logger.info("📊 Оценка монет на реальных данных...")
    start_time = time.time()
    scores = coin_selector.evaluate_coins()
    duration = time.time() - start_time
    
    assert len(scores) > 0, "Не удалось оценить ни одну монету"
    logger.info(f"✅ Оценка выполнена за {duration:.2f} сек")
    
    # Выводим результаты
    logger.info("\nРейтинг монет:")
    for i, (coin, score) in enumerate(scores):
        report = coin_selector.get_coin_report(coin)
        logger.info(f"{i+1}. {coin}: {score:.4f}")
        logger.info(f"   Волатильность: {report['metrics']['volatility']:.2f}%")
        logger.info(f"   Сила тренда: {report['metrics']['trend_strength']:.2f}%")
        logger.info(f"   Отношение объема: {report['metrics']['volume_ratio']:.2f}x")
        logger.info(f"   Риск/прибыль: {report['metrics']['risk_reward']:.2f}%")
    
    # Проверяем что все монеты присутствуют в оценке
    evaluated_coins = [c[0] for c in scores]
    for coin in REAL_COINS:
        assert coin in evaluated_coins, f"Монета {coin} отсутствует в оценке"
    
    logger.info("Тест с реальными данными завершен успешно!")