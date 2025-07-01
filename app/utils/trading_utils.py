from decimal import ROUND_DOWN, Decimal

def round_qty(qty: float, precision: int) -> float:
    quantize_str = "1" if precision == 0 else "1." + "0" * precision
    return float(Decimal(str(qty)).quantize(Decimal(quantize_str), rounding=ROUND_DOWN))