import time
import numpy as np
from typing import List, Dict, Optional
from app.indicators.market_grades import grade_atr, grade_ema_diff, grade_slope, grade_volatility
from app.utils.get_profit import ProfitCalculator
from app.utils.log_helper import log_maker
from app.services.bybit_service import BybitService

class MovingAverageStrategy:
    def __init__(
        self,
        symbol: str,
        interval: str = "3",
        short_window: int = 8,
        medium_window: int = 21,
        long_window: int = 50,
        initial_data_limit: int = 500,
        rotator=None,  # Для ротатора монет
        trading_system=None  # Для управления позициями
    ):
        self.symbol = symbol
        self.interval = interval
        self.short_window = short_window
        self.medium_window = medium_window
        self.long_window = long_window
        self.initial_data_limit = initial_data_limit
        self.bybit = BybitService()
        self.rotator = rotator  # Сохраняем ротатор
        self.trading_system = trading_system  # Сохраняем ссылку на торговую систему

        # Состояние позиции
        self.position_qty = 0.0
        self.avg_buy_price = 0.0
        self.last_action = "NONE"
        self.max_price_since_buy = None
        self.last_trade_time = time.time()

        # Статистика эффективности
        self.trade_opportunities = 0
        self.executed_trades = 0

        # Инициализация состояния через API
        self._init_state_from_api()

        # ===== ОПТИМИЗИРОВАННЫЕ ПАРАМЕТРЫ ДЛЯ МЕНЕЕ АГРЕССИВНОЙ СТРАТЕГИИ =====
        # Адаптивные параметры
        self.adaptive_params = True
        self.base_min_cross = 0.0005  # Увеличен с 0.0002
        self.base_min_slope = 0.00001  # Увеличен с 0.000005

        # Риск-менеджмент
        self.base_min_profit = 0.0080  # Увеличен с 0.0050
        self.max_loss = 0.0075         # Уменьшен с 0.01
        self.emergency_stop = -0.006   # Экстренный стоп при -0.6%

        # Фильтры входа
        self.min_volume_ratio = 0.8    # Увеличен с 0.4
        self.adaptive_volume_ratio = 0.05  # Увеличен с 0.02
        self.volume_lookback = 20      # Увеличен с 15

        # Выход из позиции
        self.trailing_stop_activation = 0.020  # Увеличен с 0.015
        self.trailing_stop_distance = 0.005    # Уменьшен с 0.006

        # Частичное взятие прибыли (менее агрессивное)
        self.partial_profit_levels = [0.004, 0.008, 0.012]  # Увеличены
        self.partial_profit_pcts = [0.2, 0.3, 0.5]          # Уменьшены
        self.partial_taken = [False, False, False]
        
        # Частичный выход при убытках
        self.partial_exit_level = -0.0025  # Увеличен с -0.003
        self.partial_exit_pct = 0.3        # Уменьшен с 0.5
        self.partial_exit_taken = False

        # Защита от преждевременного выхода
        self.min_hold_time = 30 * 60  # Увеличен с 15 до 30 минут

        # Выход по флэту
        self.flat_volatility_threshold = 0.0008  # Увеличен с 0.0006
        self.flat_max_duration = 180
        self.flat_counter = 0
        self.flat_max_no_growth = 25  # Увеличено с 15 до 25
        self.flat_exit_profit = 0.0
        self.min_hold_time_for_flat = 3600  # Увеличен с 30 до 60 минут
        
        # Фильтры по RSI и тренду
        self.rsi_overbought_threshold = 65  # Уменьшен с 68
        self.min_risk_reward_ratio = 2.5    # Увеличен с 1.8

        self.min_avg_price = 0.01  # Минимальная допустимая цена покупки

        # Дополнительные фильтры
        self.require_confirmation = True    # Требовать подтверждение сигнала
        self.confirmation_period = 3        # Количество свечей для подтверждения
        self.required_trend_strength = 4    # Минимальная сила тренда для входа

        # ===== КОНЕЦ ПАРАМЕТРОВ =====

        # Технические переменные
        self.prev_short_ema = None
        self.prev_medium_ema = None
        self.prev_long_ema = None
        self.ma_crossed_down = False
        self.ema_history = []
        self.last_trade_price = 0.0
        self.current_atr = 0.0
        self.current_short_ema = 0.0
        self.current_medium_ema = 0.0
        self.last_candle_time = None
        self.pending_signal = None
        self.signal_confirmation_count = 0

        # Загрузка исторических данных
        self._load_initial_data()

    def _load_initial_data(self):
        log_maker(
            f"⏳ Загрузка исторических данных ({self.initial_data_limit} свечей)..."
        )
        try:
            historical_candles = self.bybit.get_candles(
                self.symbol, interval=self.interval, limit=self.initial_data_limit
            )

            if historical_candles and len(historical_candles) > 50:
                closes = [c["close"] for c in historical_candles]
                self.prev_short_ema = self._calc_ema(closes, self.short_window)
                self.prev_medium_ema = self._calc_ema(closes, self.medium_window)
                self.prev_long_ema = self._calc_ema(closes, self.long_window)

                log_maker(
                    f"📊 Исторические EMA инициализированы:\n"
                    f"  Short ({self.short_window}): {self.prev_short_ema:.6f}\n"
                    f"  Medium ({self.medium_window}): {self.prev_medium_ema:.6f}\n"
                    f"  Long ({self.long_window}): {self.prev_long_ema:.6f}"
                )
            else:
                log_maker(
                    "⚠️ Не удалось загрузить исторические данные для инициализации EMA"
                )
        except Exception as e:
            log_maker(f"❌ Ошибка загрузки исторических данных: {e}")

    def _init_state_from_api(self):
        log_maker("\n\n⚙️ Инициализация состояния через API...")
        try:
            coin = self.symbol.replace("USDT", "")
            actual_balance = self.bybit.get_balance(coin)
            self.position_qty = actual_balance

            # Получаем последние ордера из API
            orders = self.bybit.get_filled_orders(self.symbol, limit=20)
            
            # Если есть ордера, ищем последний BUY
            last_buy_price = None
            if orders:
                for order in orders:
                    if order["side"].upper() == "BUY":
                        last_buy_price = float(order.get("avgPrice", 0.0))
                        break
            
            # Если нашли цену покупки
            if last_buy_price:
                self.avg_buy_price = last_buy_price
                log_maker(f"⚙️ Цена покупки установлена: {self.avg_buy_price:.6f}")
            else:
                # Если позиция есть, но нет истории покупок
                if actual_balance > 0:
                    current_price = self.bybit.get_reliable_price(self.symbol)
                    self.avg_buy_price = current_price
                    log_maker(f"⚙️ Установлена текущая цена как цена покупки: {current_price:.6f}")
                else:
                    self.avg_buy_price = 0.0
                    
        except Exception as e:
            log_maker(f"❌ Критическая ошибка инициализации из API: {e}")
            self.position_qty = 0
            self.avg_buy_price = 0.0
            
    def _record_trade(self, side: str):
        try:
            order = self.bybit.get_last_filled_order(self.symbol)
            if not order:
                log_maker("❌ Не удалось получить данные ордера из API")
                return

            actual_price = float(order["avg_price"])
            self.last_trade_price = actual_price
            actual_qty = float(order["qty"])
            usdt_qty = float(order["cumExecValue"])
            coin_qty = float(order["cumExecQty"])
            actual_side = order["side"].upper()

            # Для покупки
            if actual_side == "BUY":
                if self.position_qty > 0:
                    total_cost = (self.avg_buy_price * self.position_qty) + (
                        actual_price * actual_qty
                    )
                    self.position_qty += actual_qty
                    self.avg_buy_price = total_cost / self.position_qty
                else:
                    self.position_qty = actual_qty
                    self.avg_buy_price = actual_price
                
                # Сброс флагов при новой покупке
                self.partial_exit_taken = False
                self.max_price_since_buy = actual_price

            # Для продажи
            elif actual_side == "SELL":
                if self.position_qty > 0:
                    sell_qty = min(actual_qty, self.position_qty)
                    self.position_qty -= sell_qty
                    if self.position_qty <= 0:
                        self.avg_buy_price = 0.0
                        self.max_price_since_buy = None
                        # Сброс флагов при полной продаже
                        self.partial_exit_taken = False
            
            # Для частичной продажи
            elif actual_side == "SELL_PARTIAL":
                if self.position_qty > 0:
                    sell_qty = min(actual_qty, self.position_qty)
                    self.position_qty -= sell_qty
                    # Не сбрасываем avg_buy_price при частичной продаже
                    if self.position_qty <= 0:
                        self.avg_buy_price = 0.0
                        self.max_price_since_buy = None
            
            coin = self.symbol.replace("USDT", "")
            amount = coin_qty
            log_maker(
                f"📝 Сделка записана: {actual_side} {amount} {coin} по цене {actual_price:.6f}. "
                f"Текущее количество: {self.position_qty:.6f}"
            )
        except Exception as e:
            log_maker(f"❌ Ошибка при записи сделки: {e}")
            self._init_state_from_api()

    def _calculate_atr(self, candles: List[Dict], window: int = 14) -> float:
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
        if not prices or len(prices) < window:
            return 0.0
            
        k = 2 / (window + 1)
        ema = prices[0]
        
        for price in prices[1:]:
            ema = price * k + ema * (1 - k)
            
        return ema

    def _get_profit_stats(self) -> dict:
        try:
            calculator = ProfitCalculator(
                symbol=self.symbol, bybit=self.bybit, last_action=self.last_action
            )
            return calculator.get_profit_stats()
        except Exception as e:
            log_maker(f"Ошибка получения статистики прибыли: {e}")
            return {"today": 0.0, "7_days": 0.0, "30_days": 0.0}
            
    def _check_hourly_trend(self) -> int:
        try:
            hourly_candles = self.bybit.get_candles(
                self.symbol, interval="30", limit=8
            )
            
            if len(hourly_candles) < 5:
                return 0
                
            closes = [c["close"] for c in hourly_candles]
            short_ema = self._calc_ema(closes, 5)
            medium_ema = self._calc_ema(closes, 10)
            
            if short_ema > medium_ema:
                return 1
            elif short_ema < medium_ema:
                return -1
            return 0
        except Exception as e:
            log_maker(f"⚠️ Ошибка проверки часового тренда: {e}")
            return 0

    def _calculate_rsi(self, closes: List[float], period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0

        relevant_closes = closes[-(period+1):]
        deltas = np.diff(relevant_closes)
        
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])
        
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period-1) + gains[i]) / period
            avg_loss = (avg_loss * (period-1) + losses[i]) / period
        
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
            
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return min(max(rsi, 0), 100)

    def should_trade(self, candles: List[Dict]) -> Optional[str]:
        if not candles:
            return None
            
        current_candle = candles[-1]
        current_candle_time = current_candle.get('timestamp')
        
        if not current_candle_time:
            current_candle_time = time.time()
        
        if self.last_candle_time == current_candle_time:
            return None
            
        self.last_candle_time = current_candle_time

        self._init_state_from_api()
        if not candles:
            return None

        self.trade_opportunities += 1

        if len(candles) < 50:
            log_maker(
                "📊📭 Недостаточно данных для анализа (требуется минимум 50 свечей)"
            )
            return None

        current_price = self.bybit.get_price(self.symbol)
        if not self.bybit.validate_price(current_price, self.symbol):
            log_maker("🚨 Цена не прошла валидацию! Запрос надежной цены...")
            current_price = self.bybit.get_reliable_price(self.symbol)

        if current_price is None or not self.bybit.validate_price(
            current_price, self.symbol
        ):
            log_maker("💸❌ Нет достоверной цены, пропускаем итерацию.")
            return None
        
        if (self.position_qty > 0 
            and self.avg_buy_price < self.min_avg_price
            and self.last_action == "BUY"):
            log_maker("⚠️ Критическая ошибка: цена покупки неизвестна! Используем текущую цену.")
            self.avg_buy_price = current_price
            self.last_trade_time = time.time()

        candle_low = current_candle['low']
        price_diff = (current_price - candle_low) / candle_low
        if not self.position_qty and price_diff > 0.005:
            log_maker(f"⏩ Пропуск BUY: цена ({current_price}) далеко от минимума свечи ({candle_low})")
            return None

        closes = [c["close"] for c in candles]
        volumes = [c.get("volume", 0) for c in candles]
        if max(volumes[-self.volume_lookback:]) == 0:
            log_maker("⚠️ Обнаружен нулевой объем, пропускаем итерацию")
            return None

        range_window = 20
        upper_level = max(closes[-range_window:])
        lower_level = min(closes[-range_window:])
        level_delta = (upper_level - lower_level) * 0.02

        short_ema = self._calc_ema(closes, self.short_window)
        medium_ema = self._calc_ema(closes, self.medium_window)
        long_ema = self._calc_ema(closes, self.long_window)

        self.current_short_ema = short_ema
        self.current_medium_ema = medium_ema

        self.ema_history.append(short_ema)
        if len(self.ema_history) > 10:
            self.ema_history.pop(0)

        if len(self.ema_history) >= 3:
            slopes = []
            for i in range(1, 3):
                if self.ema_history[-i - 1] > 0:
                    slope = (
                        (self.ema_history[-i] - self.ema_history[-i - 1])
                        / self.ema_history[-i - 1]
                    ) * 100
                    slopes.append(slope)
            short_ema_slope = np.mean(slopes) if slopes else 0
        else:
            short_ema_slope = (
                ((short_ema - self.prev_short_ema) / self.prev_short_ema) * 100
                if self.prev_short_ema > 0
                else 0
            )

        returns = [np.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
        volatility = np.std(returns[-self.long_window :]) if returns else 0.0
        volatility_percent = volatility * 100

        volatility_factor = min(5.0, volatility_percent / 0.05) if volatility_percent > 0 else 1.0

        taker_fee = 0.0018
        min_profit_dynamic = max(
            self.base_min_profit,
            taker_fee * 2 + 0.0003,
            volatility * 1.5,
        )

        atr = self._calculate_atr(candles, window=14)
        self.current_atr = atr

        rsi = self._calculate_rsi(closes)
        if not self.position_qty and rsi > self.rsi_overbought_threshold:
            log_maker(f"⏩ Пропуск BUY: RSI {rsi:.2f} > {self.rsi_overbought_threshold} (перекупленность)")
            return None

        if self.adaptive_params:
            adaptive_cross_diff = max(
                self.base_min_cross, min(0.01, volatility_factor * self.base_min_cross)
            )
            adaptive_ema_slope = max(
                self.base_min_slope, min(0.005, volatility_factor * self.base_min_slope)
            )
            adaptive_volume_ratio = max(
                0.01,
                min(1.0, 0.5 / volatility_factor),
            )
            
            if volatility_factor < 0.8:
                adaptive_cross_diff *= 0.7
                adaptive_ema_slope *= 0.6
                adaptive_volume_ratio *= 0.5
            elif volatility_factor > 1.5:
                adaptive_cross_diff *= 1.3
                adaptive_ema_slope *= 1.4
                adaptive_volume_ratio *= 1.2
        else:
            adaptive_cross_diff = self.base_min_cross
            adaptive_ema_slope = self.base_min_slope
            adaptive_volume_ratio = 0.3

        qty_precision = self.bybit.get_qty_precision(self.symbol)
        coin = self.symbol.replace("USDT", "")
        balance_usdt = self.bybit.get_balance("USDT")
        quantity_usdt = round(balance_usdt, qty_precision) if balance_usdt else 0
        time_since_last_trade = (
            time.time() - self.last_trade_time if self.last_trade_time else 0
        )
        hours, remainder = divmod(time_since_last_trade, 3600)
        minutes, seconds = divmod(remainder, 60)
        time_display = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"

        unrealized_pnl = 0.0
        unrealized_pnl_pct = 0.0
        position_status = "⚠️ Нет открытой позиции"
        if self.position_qty > 0:
            if self.avg_buy_price > 0:
                api_price = self.bybit.get_reliable_price(self.symbol)
                unrealized_pnl = (api_price - self.avg_buy_price) * self.position_qty
                net_profit = unrealized_pnl - api_price * self.position_qty * taker_fee
                unrealized_pnl_pct = (
                    net_profit / (self.avg_buy_price * self.position_qty)
                ) * 100

                if net_profit >= 0:
                    position_status = (
                        f"💰 Прибыль: +{net_profit:.6f} USDT (+{unrealized_pnl_pct:.4f}%)"
                    )
                else:
                    position_status = (
                        f"📉 Убыток: {net_profit:.6f} USDT ({unrealized_pnl_pct:.4f}%)"
                    )
            else:
                position_status = "⚠️ Позиция есть, но цена покупки неизвестна"

        vol_tag, vol_desc = grade_volatility(volatility_percent)
        atr_tag, atr_desc = grade_atr(atr, current_price)
        
        # Динамический стоп-лосс на основе ATR
        dynamic_stop_loss = self.max_loss
        if self.position_qty > 0 and self.avg_buy_price > 0:
            atr_contribution = atr * 2.5 / (self.avg_buy_price * self.position_qty)
            dynamic_stop_loss = max(self.max_loss, atr_contribution)

        # Принудительный выход по времени
        if self.last_action == "BUY" and self.position_qty > 0:
            # Условие 1: если удерживаем больше 1 часа и в убытке
            if time_since_last_trade > 3600 and unrealized_pnl_pct < 0:
                log_maker(f"⏱️ [TIME EXIT] Позиция удерживается >1 часа с убытком {unrealized_pnl_pct:.2f}%")
                return "SELL"

            # Условие 2: если удерживаем больше 30 минут и убыток больше 0.5%
            if time_since_last_trade > 1800 and unrealized_pnl_pct < -0.5:
                log_maker(f"🆘 [EMERGENCY EXIT] Позиция удерживается >30 мин с убытком {unrealized_pnl_pct:.2f}%")
                return "SELL"

            # Экстренный выход при значительном убытке
            if unrealized_pnl_pct < self.emergency_stop * 100:
                log_maker(f"🚨 [EMERGENCY STOP] Убыток превысил {self.emergency_stop*100:.2f}%")
                return "SELL"

        stats_message = (
            f"📊 short EMA: {short_ema:.6f}\n📊 medium EMA:{medium_ema:.6f}\n📊 long EMA:{long_ema:.6f}\n"
            f"💰 Текущая цена: {current_price:.6f}\n"
            f"📦 Баланс {coin}: {self.position_qty:.6f}\n"
            f"💵 Баланс USDT: {quantity_usdt:.6f}\n"
            f"{position_status}\n"
            f"🌪️ Волатильность: {volatility_percent:.4f}% → {vol_tag} ({vol_desc})\n"
            f"📏 ATR: {atr:.6f} → {atr_tag} ({atr_desc})\n"
            f"🟢 Min profit: {min_profit_dynamic*100:.4f}% (base: {self.base_min_profit*100:.2f}%) | \n"
            f"🔴 Max loss: {dynamic_stop_loss*100:.4f}%\n"
            f"🧭 Последняя операция: {self.last_action} по цене {self.last_trade_price:.6f} USDT\n"
            f"⏳ Время удержания: {time_display}\n"
        )

        failed_conditions = []

        # Обновление максимальной цены
        if self.last_action == "BUY" and self.position_qty > 0:
            if self.max_price_since_buy is None:
                self.max_price_since_buy = current_price
            else:
                self.max_price_since_buy = max(self.max_price_since_buy, current_price)
                
            if current_price > self.max_price_since_buy:
                self.max_price_since_buy = current_price
                self.flat_counter = 0
            else:
                self.flat_counter += 1

            # Увеличено время для флэт-выхода
            if (
                self.flat_counter >= self.flat_max_no_growth
                and unrealized_pnl_pct > self.flat_exit_profit
                and time_since_last_trade > self.min_hold_time_for_flat
            ):
                log_maker(
                    f"⏹️ [FLAT EXIT] Цена не растёт {self.flat_counter} свечей, выходим по неубытку ({unrealized_pnl_pct:.2f}%)"
                )
                self.flat_counter = 0
                self.max_price_since_buy = None
                return "SELL"

        # Выход при флэте с минимальным убытком (с добавлением времени удержания)
        flat_condition = (
            self.last_action == "BUY"
            and volatility < self.flat_volatility_threshold
            and unrealized_pnl_pct >= -0.1
            and time_since_last_trade > self.min_hold_time_for_flat
        )
        if flat_condition:
            log_maker(f"📈 Закрываем позицию с прибылью {unrealized_pnl_pct:.4f}%")
            return "SELL"
        elif self.last_action == "BUY":
            if not (volatility < self.flat_volatility_threshold):
                failed_conditions.append("Волатильность выше порога флэта")
            if not (unrealized_pnl_pct < 0):
                failed_conditions.append(
                    f"Позиция в прибыли ({unrealized_pnl_pct:.4f}%)"
                )

        if self.last_action == "BUY" and self.position_qty > 0:
            if self.max_price_since_buy is None:
                self.max_price_since_buy = current_price
            elif current_price > self.max_price_since_buy:
                self.max_price_since_buy = current_price

            if current_price >= self.avg_buy_price * (1 + min_profit_dynamic):
                trailing_stop_price = self.max_price_since_buy * (
                    1 - self.trailing_stop_distance
                )
                if current_price <= trailing_stop_price:
                    log_maker(
                        f"🔐 [TRAILING STOP] Активирован: пик {self.max_price_since_buy:.6f}, текущая {current_price:.6f}"
                    )
                    return "SELL"
                else:
                    failed_conditions.append(
                        f"Трейлинг-стоп: цена ({current_price:.6f}) > стопа ({trailing_stop_price:.6f})"
                    )
            else:
                failed_conditions.append(
                    f"Трейлинг-стоп: не активирован (прибыль < {min_profit_dynamic*100:.4f}%)"
                )

        stop_loss_condition = (
            self.last_action == "BUY"
            and self.position_qty > 0
            and unrealized_pnl_pct <= -dynamic_stop_loss * 100
            and time_since_last_trade > 10 * 60
        )
        if stop_loss_condition:
            log_maker(
                f"🛑 [STOP LOSS] Убыток {unrealized_pnl_pct:.4f}% достиг максимума {-dynamic_stop_loss*100:.4f}%"
            )
            return "SELL"
        elif self.last_action == "BUY" and self.position_qty > 0:
            failed_conditions.append(
                f"Стоп-лосс: убыток {unrealized_pnl_pct:.4f}% > порога {-dynamic_stop_loss*100:.4f}%"
            )

        # Частичный выход при убытках
        partial_exit_condition = (
            self.last_action == "BUY"
            and self.position_qty > 0
            and unrealized_pnl_pct < self.partial_exit_level * 100
            and not self.partial_exit_taken
        )

        if partial_exit_condition:
            log_maker(f"🟡 [PARTIAL EXIT] Убыток достиг {self.partial_exit_level*100:.2f}%, продаем {self.partial_exit_pct*100:.0f}% позиции")
            self.partial_exit_taken = True
            return "SELL_PARTIAL"

        # Проверка подтверждения сигнала
        if self.pending_signal and self.require_confirmation:
            self.signal_confirmation_count += 1
            
            # Если сигнал подтвержден достаточным количеством свечей
            if self.signal_confirmation_count >= self.confirmation_period:
                confirmed_signal = self.pending_signal
                self.pending_signal = None
                self.signal_confirmation_count = 0
                return confirmed_signal
            else:
                log_maker(f"⏳ Ожидание подтверждения сигнала ({self.signal_confirmation_count}/{self.confirmation_period})")
                return None

        if self.prev_short_ema is not None and self.prev_medium_ema is not None:
            short_medium_diff = (
                ((short_ema - medium_ema) / medium_ema) * 100 if medium_ema > 0 else 0
            )

            avg_volume = (
                np.mean(volumes[-self.volume_lookback :])
                if len(volumes) >= self.volume_lookback
                else 0
            )
            current_volume = volumes[-1] if volumes else 0
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

            slope_desc = grade_slope(short_ema_slope)
            ema_diff_desc = grade_ema_diff(short_medium_diff)

            log_maker(
                f"📉 EMA Diff: S/M: {short_medium_diff:.4f}% (min: {adaptive_cross_diff:.4f}%) → {ema_diff_desc}\n"
                f"📐 Наклон short: {short_ema_slope:.4f}% (min: {adaptive_ema_slope:.4f}%) → {slope_desc}\n"
                f"📊 Объем: {volume_ratio:.2f}x (min: {adaptive_volume_ratio:.2f}x)\n"
            )

            trend_strength = 0
            if len(self.ema_history) >= 5:
                for i in range(1, min(6, len(self.ema_history))):
                    if (
                        i < len(self.ema_history)
                        and self.ema_history[-i] > self.prev_medium_ema
                    ):
                        trend_strength += 1

            entry_condition = False
            entry_type = ""
            if not entry_condition:
                if short_ema <= medium_ema:
                    failed_conditions.append("Short EMA ≤ Medium EMA")
                elif short_ema_slope <= 0:
                    failed_conditions.append("Наклон short EMA ≤ 0")
                elif current_price <= max(c["close"] for c in candles[-6:-1]):
                    failed_conditions.append("Цена не обновила локальный максимум")
            if self.prev_short_ema <= self.prev_medium_ema and short_ema > medium_ema:
                entry_condition = True
                entry_type = "🆕 Новый восходящий кросс"
            elif (
                trend_strength >= self.required_trend_strength
                and short_ema > medium_ema
                and short_ema_slope > 0
                and current_price > max(c["close"] for c in candles[-6:-1])
            ):
                entry_condition = True
                entry_type = "📈 Продолжение сильного тренда"

            if entry_condition:
                # Дополнительные фильтры входа
                if short_ema_slope < 0.00015:  # Более строгий фильтр наклона
                    log_maker("⏩ Пропуск BUY: слабый тренд (наклон EMA < 0.00015)")
                    return None

                # Проверка объема относительно ATR
                volume_threshold = atr * 1500  # Увеличен порог
                if current_volume < volume_threshold:
                    log_maker(f"⏩ Пропуск BUY: объем {current_volume} < ATR-порога {volume_threshold:.2f}")
                    return None

                # Проверка силы тренда
                if trend_strength < self.required_trend_strength:
                    log_maker(f"⏩ Пропуск BUY: сила тренда {trend_strength} < требуемой {self.required_trend_strength}")
                    return None

                if self.last_action == "BUY":
                    volatility_adjustment = max(0.5, min(2.0, volatility_factor))
                    min_time_since_last_buy = int(self.min_hold_time / volatility_adjustment)
                    if time_since_last_trade < min_time_since_last_buy:
                        log_maker(
                            f"⏱️ Защита: последняя покупка была {time_display} назад, минимальный интервал: {min_time_since_last_buy//60} мин"
                        )
                        failed_conditions.append("Защита от частых входов")
                        entry_condition = False

                condition_cross = short_medium_diff >= adaptive_cross_diff
                condition_slope = short_ema_slope >= adaptive_ema_slope
                condition_volume = volume_ratio >= adaptive_volume_ratio
                conditions_met = sum([condition_cross, condition_slope, condition_volume])

                strong_slope_condition = (
                    short_ema_slope >= 0.018
                    and (condition_cross or condition_volume) and
                    volume_ratio >= 0.08
                )

                buy_condition = (
                    balance_usdt >= 5 and
                    (conditions_met >= 2 or strong_slope_condition)
                )

                strong_trend = short_ema_slope > 0.015 or volume_ratio > 1.5
                if buy_condition and current_price > upper_level - level_delta and not strong_trend:
                    log_maker(
                        f"⛔ [LEVEL FILTER] Цена {current_price:.2f} близко к верхней границе диапазона ({upper_level:.2f})"
                    )
                    failed_conditions.append("Цена близко к верхней границе диапазона")
                    buy_condition = False

                if buy_condition:
                    risk = atr * 2
                    reward = atr * 4
                    risk_reward_ratio = reward / risk if risk > 0 else 0
                    
                    if risk_reward_ratio < self.min_risk_reward_ratio:
                        log_maker(f"⏩ Пропуск BUY: соотношение риск/прибыль {risk_reward_ratio:.1f} < {self.min_risk_reward_ratio:.1f}")
                        buy_condition = False
                        failed_conditions.append(f"Соотношение R/R {risk_reward_ratio:.1f} < {self.min_risk_reward_ratio:.1f}")

                if buy_condition:
                    hourly_trend = self._check_hourly_trend()
                    if hourly_trend == -1:
                        log_maker("⏩ Пропуск BUY: нисходящий тренд на часовом графике")
                        buy_condition = False
                        failed_conditions.append("Нисходящий тренд на 1H")

                if buy_condition:
                    reason = ""
                    if strong_slope_condition:
                        reason = "📈 СИЛЬНЫЙ НАКЛОН + дополнительное условие"
                    elif conditions_met >= 2:
                        reason = f"✅ {conditions_met} из 3 условий выполнено"
                    log_maker(f"📥 [BUY SIGNAL] {entry_type} | Причина: {reason}\n"
                            f"  • Разница EMA: {short_medium_diff:.4f}% {'✅' if condition_cross else '❌'} (порог: {adaptive_cross_diff:.4f}%)\n"
                            f"  • Наклон EMA: {short_ema_slope:.4f}% {'✅' if condition_slope else '❌'} (порог: {adaptive_ema_slope:.4f}%)\n"
                            f"  • Объем: {volume_ratio:.2f}x {'✅' if condition_volume else '❌'} (порог: {adaptive_volume_ratio:.2f}x)")
                    
                    # Вместо немедленного входа, ставим сигнал на подтверждение
                    if self.require_confirmation:
                        self.pending_signal = "BUY"
                        self.signal_confirmation_count = 1
                        log_maker(f"🟡 Предварительный сигнал BUY. Ожидаю подтверждения.")
                        return None
                    else:
                        self.max_price_since_buy = current_price
                        self.ma_crossed_down = False
                        return "BUY"
                else:
                    buy_failed = []
                    if not (short_medium_diff >= adaptive_cross_diff):
                        buy_failed.append(
                            f"Разница EMA S/M ({short_medium_diff:.4f}% < {adaptive_cross_diff:.4f}%)"
                        )
                    if not (short_ema_slope >= adaptive_ema_slope):
                        buy_failed.append(
                            f"Наклон short EMA ({short_ema_slope:.4f}% < {adaptive_ema_slope:.4f}%)"
                        )
                    if not (volume_ratio >= adaptive_volume_ratio):
                        buy_failed.append(
                            f"Объем ({volume_ratio:.2f}x < {adaptive_volume_ratio:.2f}x)"
                        )
                    if buy_failed:
                        failed_conditions.append(
                            f"Условия покупки: " + ", ".join(buy_failed)
                        )

            if self.prev_short_ema <= self.prev_medium_ema and short_ema > medium_ema:
                if self.ma_crossed_down:
                    log_maker("🟢 Сброс флага выхода (MA кросс вверх)")
                    self.ma_crossed_down = False

            if (
                self.ma_crossed_down
                and self.last_action == "BUY"
                and self.position_qty > 0
            ):
                time_in_trade = time.time() - self.last_trade_time
                if time_in_trade < self.min_hold_time:
                    log_maker(
                        f"⏱️ Удерживаем позицию ({time_in_trade/60:.1f} мин < {self.min_hold_time/60} мин)"
                    )
                    failed_conditions.append(
                        f"Защита: позиция удерживается менее {self.min_hold_time/60} мин"
                    )
                elif current_price and self.avg_buy_price:
                    min_net_profit = min_profit_dynamic * 100 + 0.1
                    if unrealized_pnl_pct >= min_net_profit:
                        log_maker(
                            f"💰 [SELL SIGNAL] Net Profit: {unrealized_pnl_pct:.4f}% ≥ {min_net_profit:.4f}%"
                        )
                        return "SELL"
                    elif short_ema > medium_ema:
                        log_maker("⚠️ Отменяем выход - MA кросс вниз был ложным")
                        self.ma_crossed_down = False
                    else:
                        failed_conditions.append(
                            f"Выход по флагу: прибыль {unrealized_pnl_pct:.4f}% < мин. {min_net_profit:.4f}%"
                        )
                else:
                    failed_conditions.append("Выход по флагу: нет данных о цене")

            if self.prev_short_ema >= self.prev_medium_ema and short_ema < medium_ema:
                if self.last_action == "BUY" and self.position_qty > 0:
                    self.ma_crossed_down = True
                    log_maker("⚠️ MA cross down - exit flag set")
                else:
                    log_maker("⚠️ MA cross down (no position)")

        if (
            self.position_qty == 0
            and len(closes) > 8
            and all(closes[-i] < closes[-i-1] for i in range(7,2,-1))
            and closes[-2] < closes[-1]
            and current_price < short_ema * 1.01
            and current_price < upper_level - level_delta
            and balance_usdt >= 5
        ):
            risk = atr * 2
            reward = atr * 4
            risk_reward_ratio = reward / risk if risk > 0 else 0
            
            if risk_reward_ratio >= self.min_risk_reward_ratio:
                # Вход по отскоку также требует подтверждения
                if self.require_confirmation:
                    self.pending_signal = "BUY"
                    self.signal_confirmation_count = 1
                    log_maker(f"🟡 Предварительный сигнал BOUNCE BUY. Ожидаю подтверждения.")
                    return None
                else:
                    log_maker("📈 [BOUNCE ENTRY] Вход по отскоку после падения")
                    self.max_price_since_buy = current_price
                    self.ma_crossed_down = False
                    return "BUY"
            else:
                log_maker(f"⏩ Пропуск BOUNCE: соотношение риск/прибыль {risk_reward_ratio:.1f} < {self.min_risk_reward_ratio:.1f}")

        self.prev_short_ema = short_ema
        self.prev_medium_ema = medium_ema
        self.prev_long_ema = long_ema

        log_maker(stats_message)

        if self.trade_opportunities % 50 == 0 and self.trade_opportunities > 0:
            ratio = self.executed_trades / self.trade_opportunities
            log_maker(f"📊 Эффективность: {self.executed_trades}/{self.trade_opportunities} ({ratio:.1%}) сигналов исполнено")
            
            if ratio < 0.1:
                self.base_min_cross *= 0.9
                self.base_min_slope *= 0.85
                log_maker(f"🔧 Корректировка параметров: min_cross={self.base_min_cross:.6f}, min_slope={self.base_min_slope:.6f}")
            
            elif ratio > 0.3:
                self.base_min_cross *= 1.1
                self.base_min_slope *= 1.15
                log_maker(f"🔧 Корректировка параметров: min_cross={self.base_min_cross:.6f}, min_slope={self.base_min_slope:.6f}")

        if failed_conditions:
            log_maker("🔍 Не выполнены условия:")
            for condition in failed_conditions:
                log_maker(f"   - {condition}")
        else:
            log_maker("⏸️ Ни одно торговое условие не выполнено")

        return None

    def execute_trade(self, action: str, executor):
        """Исполнение торгового сигнала с обновлением состояния"""
        if action == "BUY":
            # Передаем trading_system в execute_buy
            if executor.execute_buy(trading_system=self.trading_system):
                self._init_state_from_api()
        elif action == "SELL":
            if executor.execute_sell(strategy=self):
                self._init_state_from_api()

    