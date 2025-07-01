import os
import json
import time
import numpy as np
from datetime import datetime, timedelta
import logging
from typing import Dict, List, Tuple, Optional


class CoinRanker:
    def __init__(self, data_path: str = "data/coin_ranking.json", min_trades: int = 5):
        self.data_path = data_path
        self.min_trades = min_trades
        self.logger = logging.getLogger("coin_ranker")
        self.logger.setLevel(logging.INFO)

        # Инициализируем настройки ПЕРЕД загрузкой данных
        self.default_settings = {
            "trial_period": 10,
            "min_success_rate": 0.5,
            "min_avg_profit": 0.005,
            "evaluation_period": 30,
            "initial_boost": 2,
            "decay_factor": 0.95,
            "max_coins": 30,
            "min_trade_density": 0.3,
        }

        # Теперь загружаем данные
        self.data = self.load_data()

        # Обновляем настройки
        if "settings" not in self.data:
            self.data["settings"] = self.default_settings
        else:
            for key, value in self.default_settings.items():
                if key not in self.data["settings"]:
                    self.data["settings"][key] = value

        os.makedirs("logs", exist_ok=True)

    def get_best_coins(self, top_n: int = 5) -> List[str]:
        """Возвращает лучшие монеты по производительности"""
        ranked = self.get_ranked_coins()
        return [coin for coin, _ in ranked[:top_n]]

    def load_data(self) -> Dict:
        """Загружает данные из файла с автоматической коррекцией"""
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)

        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, "r") as f:
                    data = json.load(f)
                    # Добавляем автоматическую миграцию старых данных
                    self._migrate_old_data(data)
                    # Применяем коррекцию статистики
                    self.fix_statistics(data)
                    return data
            except Exception as e:
                self.logger.error(f"Ошибка загрузки данных: {e}")
                return self._create_initial_data()
        return self._create_initial_data()

    def _migrate_old_data(self, data: dict):
        """Конвертирует старые форматы данных в новый формат"""
        # Миграция для active_coins
        for coin, coin_data in data.get("active_coins", {}).items():
            # Конвертация timestamp в ISO строку
            if "first_selected" in coin_data and isinstance(
                coin_data["first_selected"], (int, float)
            ):
                coin_data["first_selected"] = datetime.fromtimestamp(
                    coin_data["first_selected"]
                ).isoformat()

            if "last_selected" in coin_data and isinstance(
                coin_data["last_selected"], (int, float)
            ):
                coin_data["last_selected"] = datetime.fromtimestamp(
                    coin_data["last_selected"]
                ).isoformat()

        # Миграция для статистики
        stats = data.get("statistics", {})
        if "last_rotation" in stats and isinstance(
            stats["last_rotation"], (int, float)
        ):
            stats["last_rotation"] = datetime.fromtimestamp(
                stats["last_rotation"]
            ).isoformat()

        if "created_at" in stats and isinstance(stats["created_at"], (int, float)):
            stats["created_at"] = datetime.fromtimestamp(
                stats["created_at"]
            ).isoformat()

    def fix_statistics(self, data: dict):
        """Корректирует искаженную статистику selections"""
        for coin, coin_data in data.get("active_coins", {}).items():
            try:
                # Проверяем тип данных для first_selected
                first_selected = coin_data["first_selected"]
                if not isinstance(first_selected, str):
                    # Если это timestamp, конвертируем в строку
                    if isinstance(first_selected, (int, float)):
                        coin_data["first_selected"] = datetime.fromtimestamp(
                            first_selected
                        ).isoformat()
                    else:
                        # Устанавливаем текущую дату как fallback
                        coin_data["first_selected"] = datetime.now().isoformat()
                        self.logger.warning(f"🛠️ Исправлено first_selected для {coin}")

                # Проверяем тип данных для last_selected
                last_selected = coin_data["last_selected"]
                if not isinstance(last_selected, str):
                    # Если это timestamp, конвертируем в строку
                    if isinstance(last_selected, (int, float)):
                        coin_data["last_selected"] = datetime.fromtimestamp(
                            last_selected
                        ).isoformat()
                    else:
                        # Устанавливаем текущую дату как fallback
                        coin_data["last_selected"] = datetime.now().isoformat()
                        self.logger.warning(f"🛠️ Исправлено last_selected для {coin}")

                # Теперь преобразуем строки в datetime объекты
                first = datetime.fromisoformat(coin_data["first_selected"])
                last = datetime.fromisoformat(coin_data["last_selected"])
                days_active = (last - first).days + 1

                # Ограничиваем selections количеством дней активности
                if coin_data["selections"] > days_active:
                    self.logger.info(
                        f"🛠️ Корректируем selections для {coin}: {coin_data['selections']} -> {days_active}"
                    )
                    coin_data["selections"] = days_active

                    # Корректируем trial_used
                    trial_period = data["settings"]["trial_period"]
                    coin_data["trial_used"] = min(coin_data["trial_used"], trial_period)
            except Exception as e:
                self.logger.error(f"Ошибка коррекции статистики для {coin}: {e}")
                # Устанавливаем значения по умолчанию при неудачной коррекции
                coin_data["first_selected"] = datetime.now().isoformat()
                coin_data["last_selected"] = datetime.now().isoformat()
                coin_data["selections"] = 1
                coin_data["trial_used"] = 0

    def _create_initial_data(self) -> Dict:
        return {
            "active_coins": {},
            "archived_coins": {},
            "statistics": {
                "total_rotations": 0,
                "last_rotation": None,
                "created_at": datetime.now().isoformat(),
            },
            "settings": self.default_settings,  # используем self.default_settings
        }

    def save_data(self):
        """Сохраняет данные в файл"""
        try:
            with open(self.data_path, "w") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            self.logger.error(f"Ошибка сохранения данных: {e}")

    def add_new_coin(self, coin: str):
        """Добавляет новую монету в систему отслеживания"""
        if coin in self.data["active_coins"] or coin in self.data["archived_coins"]:
            return

        if len(self.data["active_coins"]) >= self.data["settings"]["max_coins"]:
            self._remove_lowest_performer()

        self.data["active_coins"][coin] = {
            "selections": 0,  # Количество выборов (итераций)
            "trades": 0,  # Количество сделок
            "profitable_trades": 0,
            "total_profit": 0.0,
            "last_selected": None,
            "first_selected": datetime.now().isoformat(),
            "last_trade": None,
            "trial_used": 0,
            "performance_score": 0.0,
            "priority": 1.0,  # Начальный приоритет
        }
        self.logger.info(f"Добавлена новая монета: {coin}")
        self.save_data()

    def add_new_coins(self, new_coins: List[str]):
        """Добавляет несколько новых монет"""
        for coin in new_coins:
            self.add_new_coin(coin)

    def record_selection(self, coin: str, is_real_rotation: bool = False):
        """Фиксирует выбор монеты (итерацию)"""
        if coin in self.data["active_coins"]:
            coin_data = self.data["active_coins"][coin]
            # Увеличиваем selections ВСЕГДА при вызове (независимо от реальной ротации)
            coin_data["selections"] += 1

            # Уменьшаем "буст" только при реальной ротации
            if (
                is_real_rotation
                and coin_data["trial_used"] < self.data["settings"]["trial_period"]
            ):
                coin_data["trial_used"] += 1
                # Плавное уменьшение приоритета вместо резкого
                decay = 1.0 - (0.5 / self.data["settings"]["trial_period"])
                coin_data["priority"] *= decay
                self.logger.info(
                    f"🔧 {coin}: уменьшен приоритет (trial {coin_data['trial_used']}/{self.data['settings']['trial_period']})"
                )
            coin_data["last_selected"] = datetime.now().isoformat()
            self.data["statistics"]["total_rotations"] += 1
            self.data["statistics"]["last_rotation"] = datetime.now().isoformat()
            self.save_data()

    def record_trade_result(self, coin: str, profit: float):
        """Записывает результат сделки"""
        if coin in self.data["active_coins"]:
            coin_data = self.data["active_coins"][coin]
            coin_data["trades"] += 1
            coin_data["last_trade"] = datetime.now().isoformat()

            if profit > 0:
                coin_data["profitable_trades"] += 1

            coin_data["total_profit"] += profit
            self.save_data()

            # Пересчитываем оценку производительности
            self._update_performance_score(coin)

            self.logger.info(f"Записана сделка для {coin}: прибыль={profit:.2f} USDT")

    def _update_performance_score(self, coin: str):
        """Обновляет оценку производительности монеты с гарантией для новых"""
        coin_data = self.data["active_coins"][coin]
        trades = coin_data["trades"]
        selections = coin_data["selections"]

        # Базовый расчет для монет с историей
        if trades > 0:
            success_rate = coin_data["profitable_trades"] / trades
            avg_profit = coin_data["total_profit"] / trades
            score = success_rate * avg_profit * 100
        # Новые монеты без истории сделок
        else:
            # Минимальный стартовый балл вместо 0
            score = 0.5

            # Дополнительный буст для совершенно новых монет
            if coin_data["selections"] == 0:
                score += 1.0

        # Применяем буст для новых монет
        trial_period = self.data["settings"]["trial_period"]
        if coin_data["trial_used"] < trial_period:
            # Сохраняем более сильный буст на весь испытательный период
            boost = self.data["settings"]["initial_boost"]
            score *= boost

            # Дополнительный буст для первых 3 выборов
            if coin_data["selections"] < 3:
                score *= 1.5

        coin_data["performance_score"] = max(0.1, score)  # Никогда не опускаем ниже 0.1
        self.save_data()

    def get_coin_performance(self, coin: str) -> Dict:
        """Возвращает производительность монеты"""
        if coin not in self.data["active_coins"]:
            return {"status": "unknown", "score": 0, "priority": 0}

        coin_data = self.data["active_coins"][coin]
        return {
            "status": self._get_performance_status(coin_data),
            "score": coin_data["performance_score"],
            "priority": coin_data["priority"],
            "trades": coin_data["trades"],
            "selections": coin_data["selections"],
            "trade_density": (
                coin_data["trades"] / coin_data["selections"]
                if coin_data["selections"] > 0
                else 0
            ),
            "success_rate": (
                coin_data["profitable_trades"] / coin_data["trades"]
                if coin_data["trades"] > 0
                else 0
            ),
            "avg_profit": (
                coin_data["total_profit"] / coin_data["trades"]
                if coin_data["trades"] > 0
                else 0
            ),
        }

    def _get_performance_status(self, coin_data: Dict) -> str:
        """Определяет статус производительности"""
        trades = coin_data["trades"]

        if trades == 0:
            return "untested"

        if coin_data["trial_used"] < self.data["settings"]["trial_period"]:
            return "trial"

        success_rate = coin_data["profitable_trades"] / trades
        avg_profit = coin_data["total_profit"] / trades

        if (
            success_rate >= 0.7
            and avg_profit >= self.data["settings"]["min_avg_profit"]
        ):
            return "excellent"
        elif (
            success_rate >= 0.6
            and avg_profit >= self.data["settings"]["min_avg_profit"] * 0.8
        ):
            return "good"
        elif success_rate >= 0.5:
            return "neutral"
        else:
            return "poor"

    def get_ranked_coins(self) -> List[Tuple[str, float]]:
        """Возвращает отсортированный список монет по приоритету"""
        ranked = []
        for coin, data in self.data["active_coins"].items():
            # Комбинированный рейтинг = производительность * приоритет
            score = data["performance_score"] * data["priority"]
            ranked.append((coin, score))

        # Сортируем по убыванию рейтинга
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked

    def should_keep_coin(self, coin: str) -> bool:
        """Определяет, стоит ли сохранять монету"""
        perf = self.get_coin_performance(coin)
        return perf["status"] in ["excellent", "good", "trial"]

    def evaluate_and_cleanup(self):
        """Оценивает и очищает список монет, удаляя неэффективные"""
        coins_to_remove = []

        for coin, data in list(self.data["active_coins"].items()):
            # Удаляем монеты с плохой производительностью после испытательного срока
            if data["trial_used"] >= self.data["settings"]["trial_period"]:
                perf_status = self._get_performance_status(data)
                if perf_status == "poor":
                    coins_to_remove.append(coin)

            # Удаляем монеты, которые не выбирались долгое время
            if data["last_selected"]:
                last_selected = datetime.fromisoformat(data["last_selected"])
                if (datetime.now() - last_selected) > timedelta(days=30):
                    coins_to_remove.append(coin)

        for coin in coins_to_remove:
            self.logger.info(
                f"Удаление монеты {coin} из-за плохой производительности или неактивности"
            )
            self.data["archived_coins"][coin] = self.data["active_coins"].pop(coin)

        if coins_to_remove:
            self.save_data()

    def get_next_coin(self, current_coin: str) -> str:
        """Возвращает следующую монету для торговли"""
        ranked_coins = self.get_ranked_coins()

        # Если текущая монета в топе, сохраняем ее
        if ranked_coins and current_coin == ranked_coins[0][0]:
            return current_coin

        # Ищем следующую подходящую монету
        for coin, score in ranked_coins:
            if coin == current_coin:
                continue

            perf = self.get_coin_performance(coin)
            if perf["status"] not in ["poor", "unknown"]:
                return coin

        # Если ничего не найдено, возвращаем текущую монету
        return current_coin

    def _remove_lowest_performer(self):
        """Удаляет монету с самой низкой производительностью"""
        ranked = self.get_ranked_coins()
        if not ranked:
            return

        lowest_coin = ranked[-1][0]
        self.logger.info(
            f"Удаление самой слабой монеты {lowest_coin} для освобождения места"
        )
        self.data["archived_coins"][lowest_coin] = self.data["active_coins"].pop(
            lowest_coin
        )
        self.save_data()

    def generate_report(self) -> str:
        """Генерирует отчет о состоянии системы"""
        report = [
            "📊 Coin Ranking System Report",
            f"• Всего ротаций: {self.data['statistics']['total_rotations']}",
            f"• Активных монет: {len(self.data['active_coins'])}",
            f"• В архиве: {len(self.data['archived_coins'])}",
            f"• Система создана: {self.data['statistics']['created_at']}",
            f"• Последняя ротация: {self.data['statistics']['last_rotation'] or 'N/A'}",
            "",
            "⚙️ Настройки системы:",
        ]

        for key, value in self.data["settings"].items():
            report.append(f"  • {key}: {value}")

        report.append("\n🏆 Топ-5 монет:")
        ranked = self.get_ranked_coins()[:5]

        for i, (coin, score) in enumerate(ranked, 1):
            perf = self.get_coin_performance(coin)
            report.append(
                f"{i}. {coin}: "
                f"score={score:.2f}, "
                f"status={perf['status']}, "
                f"priority={perf['priority']:.2f}, "
                f"trades={perf['trades']}, "
                f"success={perf['success_rate']:.1%}"
            )

        return "\n".join(report)
