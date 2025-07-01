# services/model_trainer.py
import threading
import sys
import os
import time
from app.utils.log_helper import log_maker
import traceback
import logging
import json

# Импорт функции обучения модели
try:
    from app.strategies.neural_network.trainer import main as train_model
except ImportError:
    log_maker("❌ Ошибка импорта функции обучения модели. Проверьте путь к модулю.")
    train_model = None


class ModelTrainer:
    def __init__(self, coin_list, interval="5", epochs=100, max_concurrent=1):
        self.coin_list = coin_list
        self.interval = interval  # Сохраняем текущий интервал
        self.epochs = epochs
        self.max_concurrent = max_concurrent
        self.training_queue = []
        self.current_training = 0
        self.thread = threading.Thread(target=self._training_loop, daemon=True)
        self.thread.start()
        self.logger = logging.getLogger("model_trainer")
        self.logger.setLevel(logging.INFO)
        log_maker(
            f"🎓 Инициализирован тренер моделей. Интервал: {interval} мин. Макс. одновременных обучений: {max_concurrent}"
        )

        # Создаем директорию для моделей
        os.makedirs("models", exist_ok=True)

    def add_to_queue(self, coin, force_retrain=False):
        """Добавляет монету в очередь на обучение"""
        model_path = f"models/{coin}_neural_model"
        model_file = f"{model_path}.keras"
        error_path = f"{model_path}.error"
        config_path = f"{model_path}.config"

        if os.path.exists(model_file) and not force_retrain:
            return False

        # Проверяем конфигурацию существующей модели
        existing_interval = self._get_model_interval(config_path)
        interval_mismatch = (
            existing_interval != self.interval if existing_interval else False
        )

        # Причины для переобучения
        reasons = []
        if force_retrain:
            reasons.append("принудительное переобучение")
        if interval_mismatch:
            reasons.append(
                f"несоответствие интервала ({existing_interval} ≠ {self.interval})"
            )
        if not os.path.exists(model_file):
            reasons.append("модель не существует")
        if os.path.exists(error_path):
            reasons.append("предыдущая ошибка обучения")

        if reasons:
            reason_str = ", ".join(reasons)
            self.logger.info(f"🧠 Требуется обучение {coin}: {reason_str}")

            # Удаляем старые файлы если нужно
            if os.path.exists(model_file):
                try:
                    os.remove(model_file)
                    os.remove(f"{model_path}_scaler.npz")
                    self.logger.info(f"🧹 Удалены старые файлы модели для {coin}")
                except Exception as e:
                    self.logger.info(f"⚠️ Ошибка удаления старых файлов: {e}")

            # Добавляем в очередь, если еще не добавлена
            if coin not in self.training_queue:
                # Новые монеты (без модели) добавляем в начало очереди
                if not os.path.exists(model_file) and not os.path.exists(error_path):
                    self.training_queue.insert(0, coin)
                    self.logger.info(
                        f"🚀 Монета {coin} (новая) добавлена в начало очереди обучения"
                    )
                else:
                    self.training_queue.append(coin)
                    self.logger.info(
                        f"🧠 Монета {coin} добавлена в очередь на обучение"
                    )

            else:
                self.logger.info(f"🧠 Монета {coin} уже в очереди на обучение")
            return True
        else:
            self.logger.info(
                f"🧠 Модель для {coin} актуальна (интервал: {self.interval} мин)"
            )
            return False

    def _get_model_interval(self, config_path):
        """Получает интервал из конфигурации модели"""
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    config = json.load(f)
                    return config.get("interval")
            except:
                return None
        return None

    def _save_model_config(self, config_path, interval):
        """Сохраняет конфигурацию модели"""
        try:
            with open(config_path, "w") as f:
                json.dump({"interval": interval}, f)
        except Exception as e:
            log_maker(f"⚠️ Ошибка сохранения конфигурации модели: {e}")

    def start_periodic_retraining(self, interval_hours=24):
        """Запускает периодическое переобучение каждые N часов"""

        def retrain_loop():
            while True:
                time.sleep(interval_hours * 3600)
                self.logger.info(
                    f"🔄 Запуск периодического переобучения моделей (интервал: {self.interval} мин)"
                )
                for coin in self.coin_list:
                    self.add_to_queue(coin, force_retrain=True)

        threading.Thread(target=retrain_loop, daemon=True).start()

    def _training_loop(self):
        """Основной цикл обработки очереди обучения"""
        while True:
            try:
                # Проверяем возможность запуска нового обучения
                if self.training_queue and self.current_training < self.max_concurrent:

                    coin = self.training_queue.pop(0)
                    self.current_training += 1

                    # Запускаем обучение в отдельном потоке
                    threading.Thread(
                        target=self._train_coin_model, args=(coin,), daemon=True
                    ).start()

                time.sleep(10)  # Проверяем очередь каждые 10 секунд
            except Exception as e:
                log_maker(f"🔥 Ошибка в цикле обучения: {str(e)}")
                traceback.print_exc()
                time.sleep(30)

    def _train_coin_model(self, coin):
        """Обучает модель для конкретной монеты"""
        symbol = f"{coin}USDT"
        model_path = f"models/{coin}_neural_model"
        config_path = f"{model_path}.config"

        try:
            log_maker(f"🧠 Начинаю обучение модели для {symbol} ({self.interval} мин)")

            # Проверяем наличие функции обучения
            if train_model is None:
                raise ImportError("Функция обучения не найдена")

            # Создаем аргументы командной строки для обучения
            original_argv = sys.argv.copy()
            sys.argv = [
                "trainer.py",
                f"--symbol={symbol}",
                f"--interval={self.interval}",  # Используем текущий интервал
                f"--epochs={str(self.epochs)}",
                f"--model_path={model_path}",
            ]

            log_maker(f"🔧 Параметры обучения: {' '.join(sys.argv[1:])}")

            # Вызываем функцию обучения
            train_model()

            # Сохраняем конфигурацию модели
            self._save_model_config(config_path, self.interval)

            log_maker(
                f"✅ Модель для {symbol} ({self.interval} мин) успешно обучена и сохранена"
            )

        except Exception as e:
            error_msg = f"❌ Ошибка обучения модели для {symbol} ({self.interval} мин): {str(e)}"
            log_maker(error_msg)
            traceback.print_exc()

            # Создаем файл ошибки
            try:
                with open(f"{model_path}.error", "w") as f:
                    f.write(error_msg)
            except:
                pass

        finally:
            # Восстанавливаем оригинальные аргументы
            sys.argv = original_argv
            self.current_training -= 1

    def force_retrain_all(self):
        """Принудительное переобучение всех моделей"""
        log_maker("🔄 Запуск принудительного переобучения всех моделей")
        for coin in self.coin_list:
            self.add_to_queue(coin, force_retrain=True)
