from dataclasses import dataclass
from decimal import Decimal

from src.utils.validation.money import validate_money


@dataclass(frozen=True, slots=True)
class Entity:
    id: int
    cash: Decimal = Decimal("0")
    income: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        validate_money(self.cash, field="cash")
        validate_money(self.income, field="income")


@dataclass(frozen=True, slots=True)
class Region:
    id: int
    name: str

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Region name cannot be empty")


@dataclass(frozen=True, slots=True)
class Household:
    """A single person's housing unit; residence is derived from home occupancy."""

    id: int
    person_id: int


@dataclass(frozen=True, slots=True)
class Home:
    id: int
    region_id: int
    owner_id: int
    market_value: Decimal
    occupant_id: int | None = None
    rent: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        validate_money(self.market_value, field="market_value")
        validate_money(self.rent, field="rent")
        if (self.occupant_id is None or self.occupant_id == self.owner_id) and self.rent != 0:
            raise ValueError("Vacant and owner-occupied homes cannot charge rent")
