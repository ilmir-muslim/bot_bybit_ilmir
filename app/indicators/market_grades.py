# app/indicators/market_grades.py

def grade_volatility(value: float) -> tuple[str, str]:
    if value < 0.15:
        return "🔵 Очень низкая", "Флэт, движение отсутствует"
    elif value < 0.3:
        return "🟢 Умеренная", "Лёгкое колебание, слабая активность"
    elif value < 0.6:
        return "🟡 Средняя", "Умеренная волатильность"
    else:
        return "🟠 Высокая", "Сильные колебания, возможны резкие движения цены"


def grade_atr(atr: float, current_price: float) -> tuple[str, str]:
    percent = (atr / current_price) * 100
    if percent < 0.3:
        return "🔵 Очень низкий", "Флэт, движение отсутствует"
    elif percent < 0.7:
        return "🟡 Средний", "Нормальная активность"
    else:
        return "🟠 Высокий", "Рынок дышит широко, высокая амплитуда движения"


def grade_slope(value: float) -> str:
    if value < 0.02:
        return 'Флэт / стагнация'
    elif value < 0.08:
        return 'Слабое движение'
    elif value < 0.2:
        return 'Средняя активность'
    else:
        return 'Сильное движение'


def grade_ema_diff(value: float) -> str:
    if value < 0.1:
        return 'Очень слабый тренд'
    elif value < 0.3:
        return 'Слабый тренд'
    elif value < 0.7:
        return 'Умеренный тренд'
    else:
        return 'Сильный тренд'
