from dataclasses import dataclass
from decimal import Decimal

from utils.validation.money import validate_money


@dataclass(frozen=True, slots=True)
class Entity:
    id: int
    cash: Decimal = Decimal("0")
    income: Decimal = Decimal("0")
    annual_income: Decimal | None = None

    def __post_init__(self) -> None:
        if self.annual_income is not None:
            validate_money(self.annual_income, field="annual_income")
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
    position: tuple[int, int] | None = None
    destroyed: bool = False

    def __post_init__(self) -> None:
        if self.position is not None and (
            len(self.position) != 2 or any(type(v) is not int or v < 0 for v in self.position)
        ):
            raise ValueError("position must contain two nonnegative integer coordinates")
        if self.destroyed and (
            self.market_value != 0 or self.occupant_id is not None or self.rent != 0
        ):
            raise ValueError("Destroyed homes must have zero value and rent and no resident")
        validate_money(self.market_value, field="market_value")
        validate_money(self.rent, field="rent")
        if (self.occupant_id is None or self.occupant_id == self.owner_id) and self.rent != 0:
            raise ValueError("Vacant and owner-occupied homes cannot charge rent")
