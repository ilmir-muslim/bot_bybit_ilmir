import time
from app.utils.format_data import format_profit
import numpy as np
from sqlalchemy import func
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from app.database.engine import SessionLocal
from app.database.models import TradeLog
from app.database.orm_query import orm_add_data_to_tables
from app.utils.log_helper import log_maker
from app.services.bybit_service import BybitService


class MovingAverageStrategy:
    def __init__(self, symbol: str, short_window: int = 7, long_window: int = 25):
        self.symbol = symbol
        self.short_window = short_window
        self.long_window = long_window
        self.bybit = BybitService()

        # Состояние позиции
        self.position_qty = 0.0
        self.avg_buy_price = 0.0
        self.last_action = None  # None, 'BUY', 'SELL'
        self.max_price_since_buy = None
        self.last_trade_time = time.time()

        # Инициализация состояния из БД
        self._init_state()

        # Параметры риска
        self.min_profit_margin = 0.002
        self.max_loss = 0.02
        self.trailing_stop_activation = 1.8
        self.trailing_stop_distance = 1.2

        # Параметры импульса
        self.min_momentum = 0.006
        self.breakout_window = 3
        self.max_reentry_volatility = 1.8
        self.min_volume_ratio = 1.5

        # Фильтры входа
        self.min_cross_diff_percent = 0.15
        self.min_ema_slope = 0.05
        self.volume_lookback = 5

        # Технические переменные
        self.prev_short_ema = None
        self.prev_long_ema = None
        self.ma_crossed_down = False
        self.flat_volatility_threshold = 0.0006
        self.flat_max_duration = 180
        self.last_exit_price = None

        

    def _init_state(self):
        """Инициализирует состояние стратегии из базы данных или API"""
        db = SessionLocal()
        try:
            # Пытаемся получить данные из базы
            last_trade = (
                db.query(TradeLog)
                .filter(TradeLog.symbol == self.symbol)
                .order_by(TradeLog.timestamp.desc())
                .first()
            )

            # Если в базе есть записи
            if last_trade:
                self.last_action = last_trade.side
                self.last_trade_time = last_trade.timestamp.timestamp()

                # Загрузка позиции для BUY-сделок
                if last_trade.side == "BUY":
                    buy_positions = (
                        db.query(
                            func.sum(TradeLog.qty).label("total_qty"),
                            func.sum(TradeLog.qty * TradeLog.entry_price).label(
                                "total_cost"
                            ),
                        )
                        .filter(
                            TradeLog.symbol == self.symbol,
                            TradeLog.side == "BUY",
                            TradeLog.exit_price.is_(None),
                        )
                        .first()
                    )

                    if buy_positions and buy_positions.total_qty:
                        self.position_qty = buy_positions.total_qty
                        self.avg_buy_price = (
                            buy_positions.total_cost / buy_positions.total_qty
                        )
                        self.max_price_since_buy = self.bybit.get_price(self.symbol)

                log_maker(
                    f"⚙️ Состояние загружено из БД: "
                    f"Действие={self.last_action}, "
                    f"Кол-во={self.position_qty}, "
                    f"Цена={self.avg_buy_price}"
                )
            else:
                # Если в базе нет записей - загружаем через API
                log_maker("⚙️ В БД нет записей, загружаем состояние через API...")
                self._init_state_from_api()

        except Exception as e:
            log_maker(f"❌ Ошибка инициализации из БД: {e}")
            # При ошибке БД тоже пробуем API
            self._init_state_from_api()
        finally:
            db.close()

    def _init_state_from_api(self):
        """Инициализирует состояние через Bybit API"""
        try:
            # Получаем последний заполненный ордер через API
            last_order = self.bybit.get_last_filled_order(self.symbol)

            if last_order:
                # Обязательно устанавливаем last_action
                self.last_action = last_order["side"]
                self.last_trade_time = (
                    last_order["timestamp"] / 1000
                )  # Переводим мс в секунды

                # Если последняя сделка была покупкой
                if self.last_action == "BUY":
                    # Получаем баланс и цену
                    coin = self.symbol.replace("USDT", "")
                    self.position_qty = self.bybit.get_balance(coin)
                    self.avg_buy_price = last_order["avg_price"]
                    self.max_price_since_buy = self.bybit.get_price(self.symbol)
                    log_maker(
                        f"⚙️ Состояние загружено из API: "
                        f"Действие={self.last_action}, "
                        f"Кол-во={self.position_qty}, "
                        f"Цена={self.avg_buy_price}"
                    )
                else:
                    # Для SELL просто устанавливаем действие
                    log_maker(f"⚙️ Последняя сделка из API: SELL")
                    self.position_qty = 0
                    self.avg_buy_price = 0
                    self.max_price_since_buy = None
            else:
                log_maker("⚙️ Нет истории сделок в API")
                # Устанавливаем значения по умолчанию
                self.position_qty = 0
                self.avg_buy_price = 0
                self.last_action = "NONE"  # Важно: не None!
                self.max_price_since_buy = None

        except Exception as e:
            log_maker(f"❌ Критическая ошибка инициализации из API: {e}")
            # Устанавливаем безопасные значения
            self.position_qty = 0
            self.avg_buy_price = 0
            self.last_action = None
            self.max_price_since_buy = None

    def _record_trade(self, side: str, price: float, quantity: float):
        """Записывает сделку в базу данных и обновляет состояние"""
        db = SessionLocal()
        try:
            # Подготовка данных для TradeLog
            trade_data = {
                "symbol": self.symbol,
                "side": side,
                "qty": quantity,
                "avg_price": price,
                "status": "Filled",
            }

            # Подготовка данных для UserTradeStats
            stats_data = {
                "symbol": self.symbol,
                "side": side,
                "qty": quantity,
                "price": price,
            }

            # Для покупки
            if side == "BUY":
                trade_data["entry_price"] = price
                # Обновляем состояние позиции
                total_cost = self.avg_buy_price * self.position_qty + price * quantity
                self.position_qty += quantity
                self.avg_buy_price = total_cost / self.position_qty
                self.max_price_since_buy = price

            # Для продажи
            elif side == "SELL":
                if self.position_qty > 0:
                    # Продаем только имеющееся количество
                    sell_qty = min(quantity, self.position_qty)
                    profit = (price - self.avg_buy_price) * sell_qty
                    profit_pct = (price / self.avg_buy_price - 1) * 100

                    # Обновляем данные
                    trade_data["qty"] = sell_qty
                    trade_data["exit_price"] = price
                    trade_data["profit"] = profit
                    trade_data["profit_pct"] = profit_pct
                    trade_data["is_profitable"] = profit > 0
                    trade_data["entry_price"] = self.avg_buy_price

                    stats_data["qty"] = sell_qty
                    stats_data["profit"] = profit
                    stats_data["profit_pct"] = profit_pct

                    # Обновляем состояние
                    self.position_qty -= sell_qty
                    if self.position_qty <= 0:
                        self.avg_buy_price = 0.0
                        self.max_price_since_buy = None

            # Записываем в базу
            orm_add_data_to_tables(
                session=db, data_trade_log=trade_data, data_user_trade_stats=stats_data
            )

            # Обновляем общее состояние
            self.last_action = side
            self.last_trade_time = time.time()

            log_maker(
                f"📝 Сделка записана: {side} {trade_data['qty']} по цене {price}. "
                f"Текущее количество: {self.position_qty}"
            )
        except Exception as e:
            log_maker(f"❌ Ошибка при записи сделки: {e}")
        finally:
            db.close()

    def _calculate_atr(self, candles: List[Dict], window: int = 14) -> float:
        """Расчет Average True Range с фиксированным окном."""
        if len(candles) < 2:
            return 0.0

        trs = []
        start_idx = max(1, len(candles) - window)

        for i in range(start_idx, len(candles)):
            high = candles[i]["high"]
            low = candles[i]["low"]
            prev_close = candles[i - 1]["close"]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            trs.append(tr)

        return np.mean(trs[-window:]) if trs else 0.0

    def _calc_ema(self, prices: List[float], window: int) -> float:
        """Расчет экспоненциального скользящего среднего."""
        if len(prices) < window:
            return np.mean(prices) if prices else 0.0

        alpha = 2 / (window + 1)
        ema = np.mean(prices[:window])

        for price in prices[window:]:
            ema = alpha * price + (1 - alpha) * ema

        return ema

    def _get_profit_stats(self) -> dict:
        """Возвращает статистику прибыли за разные периоды"""
        db = SessionLocal()
        try:
            now = datetime.now()

            # Сегодня (с 00:00)
            today_start = datetime(now.year, now.month, now.day)

            # Начало недели (понедельник)
            week_start = today_start - timedelta(days=now.weekday())

            # Начало месяца
            month_start = datetime(now.year, now.month, 1)

            # Запросы к БД
            today_profit = (
                db.query(func.sum(TradeLog.profit))
                .filter(
                    TradeLog.symbol == self.symbol, TradeLog.timestamp >= today_start
                )
                .scalar()
                or 0.0
            )

            week_profit = (
                db.query(func.sum(TradeLog.profit))
                .filter(
                    TradeLog.symbol == self.symbol, TradeLog.timestamp >= week_start
                )
                .scalar()
                or 0.0
            )

            month_profit = (
                db.query(func.sum(TradeLog.profit))
                .filter(
                    TradeLog.symbol == self.symbol, TradeLog.timestamp >= month_start
                )
                .scalar()
                or 0.0
            )

            return {"today": today_profit, "week": week_profit, "month": month_profit}
        except Exception as e:
            log_maker(f"Ошибка получения статистики: {e}")
            return {"today": 0.0, "week": 0.0, "month": 0.0}
        finally:
            db.close()

    def should_trade(self, candles: List[Dict]) -> Optional[str]:
        if len(candles) < self.long_window:
            log_maker("📊📭 Недостаточно данных для анализа")
            return None

        closes = [c["close"] for c in candles]
        volumes = [c.get("volume", 0) for c in candles]

        # Расчет EMA
        short_ema = self._calc_ema(closes, self.short_window)
        long_ema = self._calc_ema(closes, self.long_window)

        # Расчет волатильности
        returns = []
        for i in range(1, len(closes)):
            ret = np.log(closes[i] / closes[i - 1])
            returns.append(ret)

        volatility = np.std(returns[-self.long_window :]) if returns else 0.0
        volatility_percent = volatility * 100

        # Динамическое обновление параметров
        self.max_loss = min(0.06, max(0.02, volatility_percent * 3 / 100))
        self.min_profit_margin = max(0.002, volatility_percent * 2 / 100)

        # Расчет ATR
        atr = self._calculate_atr(candles, window=14)

        current_price = self.bybit.get_price(self.symbol)
        if current_price is None:
            log_maker("💸❌ Нет текущей цены, пропускаем итерацию.")
            return None

        # Получение данных для расчета позиции
        qty_precision = self.bybit.get_qty_precision(self.symbol)
        coin = self.symbol.replace("USDT", "")
        balance_usdt = self.bybit.get_balance("USDT")
        quantity_usdt = round(balance_usdt, qty_precision) if balance_usdt else 0

        time_since_buy = time.time() - self.last_trade_time

        # Расчет PnL текущей позиции
        unrealized_pnl = 0.0
        unrealized_pnl_pct = 0.0
        if self.last_action == "BUY" and self.position_qty > 0:
            # Учитываем комиссию taker (0.18%) при продаже
            taker_fee = 0.0018
            unrealized_pnl = (current_price - self.avg_buy_price) * self.position_qty
            # Чистая прибыль с учетом комиссии при продаже
            net_profit = unrealized_pnl - current_price * self.position_qty * taker_fee
            unrealized_pnl_pct = (
                net_profit / (self.avg_buy_price * self.position_qty)
            ) * 100

            if net_profit >= 0:
                pnl_display = (
                    f"💰 Прибыль: +{net_profit:.6f} USDT (+{unrealized_pnl_pct:.4f}%)"
                )
            else:
                pnl_display = (
                    f"📉 Убыток: {net_profit:.6f} USDT ({unrealized_pnl_pct:.4f}%)"
                )
        else:
            pnl_display = "⚠️ Нет открытой позиции"
        profit_stats = self._get_profit_stats()
        today_display = format_profit(profit_stats["today"])
        week_display = format_profit(profit_stats["week"])
        month_display = format_profit(profit_stats["month"])

        # Форматирование сообщения
        stats_message = (
            f"📊 short EMA: {short_ema:.6f}, long EMA: {long_ema:.6f}\n"
            f"💰 Цена: {current_price:.6f}\n"
            f"📦 Баланс {coin}: {self.position_qty:.6f}\n"
            f"💵 Баланс USDT: {quantity_usdt:.6f}\n"
            f"{pnl_display}\n"
            f"🌪️ Волатильность: {volatility_percent:.4f}%\n"
            f"📏 ATR: {atr:.6f}\n"
            f"🟢 Min profit: {self.min_profit_margin*100:.4f}% | \n"
            f"🔴 Max loss: {self.max_loss*100:.4f}%\n"
            f"🧭 Последняя операция: {self.last_action}\n"
            f"⏳ Время удержания: {time.strftime('%H:%M:%S', time.gmtime(time_since_buy))}\n"
            f"📈 Прибыль:\n"
            f"  Сегодня: {today_display} USDT\n"
            f"  Неделя: {week_display} USDT\n"
            f"  Месяц: {month_display} USDT"
        )
        log_maker(stats_message)

        # 1. Проверка выхода по флэту
        if (
            self.last_action == "BUY"
            and volatility < self.flat_volatility_threshold
            and time_since_buy > self.flat_max_duration
            and unrealized_pnl_pct >= 0  # Прибыль с учетом комиссии
        ):
            log_maker(f"📈 Закрываем позицию с прибылью {unrealized_pnl_pct:.4f}%")
            return "SELL"

        # 2. Трейлинг-стоп
        if self.last_action == "BUY" and self.position_qty > 0:
            if self.max_price_since_buy is None:
                self.max_price_since_buy = current_price
            elif current_price > self.max_price_since_buy:
                self.max_price_since_buy = current_price

            # Активация только после достижения порога прибыли
            if current_price >= self.avg_buy_price * (
                1 + self.trailing_stop_activation * atr / self.avg_buy_price
            ):
                trailing_stop_price = self.max_price_since_buy * (
                    1 - self.trailing_stop_distance * atr / self.max_price_since_buy
                )
                if current_price <= trailing_stop_price:
                    log_maker(
                        f"🔐 [TRAILING STOP] Активирован: пик {self.max_price_since_buy:.6f}, "
                        f"текущая цена {current_price:.6f}, стоп {trailing_stop_price:.6f}"
                    )
                    return "SELL"

        # 3. Стоп-лосс
        if self.last_action == "BUY" and self.position_qty > 0:
            if unrealized_pnl_pct <= -self.max_loss * 100:
                log_maker(
                    f"🛑 [STOP LOSS] Убыток {unrealized_pnl_pct:.4f}% достиг максимума {-self.max_loss*100:.4f}%"
                )
                return "SELL"

        # 4. Логика MA-кроссов
        if self.prev_short_ema is not None and self.prev_long_ema is not None:
            # Расчет наклона EMA
            short_ema_slope = 0
            if self.prev_short_ema > 0:
                short_ema_slope = (
                    (short_ema - self.prev_short_ema) / self.prev_short_ema
                ) * 100

            # Расчет разницы между EMA в процентах
            ema_diff_percent = 0
            if long_ema > 0:
                ema_diff_percent = ((short_ema - long_ema) / long_ema) * 100

            # Фильтр объема
            avg_volume = (
                np.mean(volumes[-self.volume_lookback :])
                if len(volumes) >= self.volume_lookback
                else 0
            )
            current_volume = volumes[-1] if volumes else 0
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

            log_maker(
                f"📉 [EMA DIFF] Разница: {ema_diff_percent:.4f}% | "
                f"📐 Наклон short: {short_ema_slope:.4f}% | "
                f"📊 Объем: {volume_ratio:.2f}x"
            )

            # Кросс вверх (покупка) только с фильтрами
            if (
                self.prev_short_ema <= self.prev_long_ema
                and short_ema > long_ema
                and self.last_action != "BUY"
                and ema_diff_percent >= self.min_cross_diff_percent
                and short_ema_slope >= self.min_ema_slope
                and volume_ratio >= self.min_volume_ratio
            ):
                log_maker(
                    f"📥 [ENTRY SIGNAL] MA-кросс: short EMA {short_ema:.6f} > long EMA {long_ema:.6f} | "
                    f"Разница: {ema_diff_percent:.4f}% | Объём: {volume_ratio:.2f}x"
                )
                return "BUY"

            # Выход по кроссу вниз при условии прибыли
            elif (
                self.ma_crossed_down
                and self.last_action == "BUY"
                and self.position_qty > 0
            ):
                if unrealized_pnl_pct >= self.min_profit_margin * 100:
                    log_maker(
                        f"💰 [PROFIT EXIT] Прибыль: {unrealized_pnl_pct:.4f}% достигла минимума {self.min_profit_margin*100:.4f}%"
                    )
                    return "SELL"

            # Обнаружение кросса вниз (установка флага)
            if self.prev_short_ema >= self.prev_long_ema and short_ema < long_ema:
                self.ma_crossed_down = True
                log_maker("⚠️ MA кросс вниз — установлен флаг для возможного выхода")

        # Обновление предыдущих значений EMA
        self.prev_short_ema = short_ema
        self.prev_long_ema = long_ema

        log_maker("⏸️ Ни одно торговое условие не выполнено")
        return None
