#!/usr/bin/env python3
import logging
import time
import traceback
import os
from app.services.bot_controller import BotController, bot_controller
from app.utils import load_coin_list
from app.services.trading_system import TradingSystem
from app.trading.order_executor import OrderExecutor

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/bot_system.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('main')

def setup_directories():
    """Создает необходимые директории"""
    os.makedirs("models", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    os.makedirs("data", exist_ok=True)

def main():
    logger.info("🚀 Запуск торговой системы...")
    setup_directories()
    
    coin_list = load_coin_list("coins_list.txt")
    logger.info(f"📋 Загружено монет: {len(coin_list)}")
    
    trading_system = TradingSystem(coin_list=coin_list)
    trading_system.start()
    
    # Создаём контроллер с передачей rotator
    bot_controller = BotController(rotator=trading_system.rotator)

    # Проверяем есть ли открытая позиция
    position_coin = trading_system.state.get("position_coin", "")
    if position_coin:
        trading_system.current_coin = position_coin
        trading_system.rotator.set_current_coin(position_coin)
        logger.info(f"⏪ Возвращаемся к открытой позиции: {position_coin}")
    
    
    logger.info(f"🏁 Начальная монета: {trading_system.current_coin}")

    bot_controller.start()
    logger.info("🤖 Торговый бот запущен")
    
    try:
        logger.info("🔄 Вход в основной цикл управления")
        last_health_check = time.time()
        while True:
            # Проверяем состояние бота
            if bot_controller.status() != "running":
                logger.error("⚠️ Бот остановлен! Перезапускаем...")
                bot_controller.start()
            
            # Ротация монет только если нет открытой позиции
            if not trading_system.position_open_time:
                try:
                    current_coin = trading_system.rotator.rotate_coins()
                    if current_coin != trading_system.current_coin:
                        logger.info(f"🔄 Переключаем монету с {trading_system.current_coin} на {current_coin}")
                        
                        # Принудительно очищаем остатки предыдущей монеты
                        prev_symbol = f"{trading_system.current_coin}USDT"
                        executor = OrderExecutor(prev_symbol)
                        executor.clean_residuals(threshold=0.0001)
                        
                        trading_system.switch_coin(current_coin)
                        bot_controller.switch_coin(current_coin)
                except Exception as e:
                    logger.error(f"⚠️ Ошибка при ротации монет: {e}")
            
            # Проверка на принудительное закрытие позиции
            try:
                if trading_system.position_open_time:
                    symbol = f"{trading_system.current_coin}USDT"
                    logger.info(f"⏱️ Проверка принудительного закрытия позиции для {symbol}")
                    
                    # Проверяем есть ли реальная позиция
                    positions = trading_system.bybit.get_open_positions()
                    position_exists = any(
                        pos['coin'] == trading_system.current_coin 
                        for pos in positions
                    )
                    
                    if position_exists:
                        executor = OrderExecutor(symbol)
                        if executor.execute_force_close():
                            trading_system.position_open_time = 0
                            logger.info("✅ Позиция успешно закрыта")
                        else:
                            logger.warning("⚠️ Не удалось закрыть позицию принудительно")
                    else:
                        logger.info("⏩ Нет открытой позиции, сбрасываем флаг")
                        trading_system.position_open_time = 0
            except Exception as e:
                logger.error(f"⚠️ Ошибка при проверке принудительного закрытия: {e}")
            
            # Health check
            if time.time() - last_health_check > 3600:
                logger.info("🩺 Health check:")
                logger.info(f"Bot status: {bot_controller.status()}")
                last_health_check = time.time()
            
            # Ожидание перед следующей проверкой
            time.sleep(60)
            
    except KeyboardInterrupt:
        logger.info("🛑 Получен сигнал KeyboardInterrupt")
    except Exception as e:
        logger.error(f"💥 Критическая ошибка: {e}")
        logger.error(traceback.format_exc())
    finally:
        logger.info("⏹️ Завершение работы системы...")
        bot_controller.stop()
        trading_system.stop()
        logger.info("✅ Система остановлена корректно")

if __name__ == "__main__":
    main()