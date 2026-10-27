from decimal import Decimal


def validate_money(value: Decimal, *, field: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field} must be a Decimal")
    if not value.is_finite() or value < 0:
        raise ValueError(f"{field} must be finite and nonnegative")
