"""Seeded toy-model population with one initial resident per grid cell."""

from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from math import isfinite
from typing import Literal

from domain.models import Entity, Home, Household, Region
from environment import Scenario
from utils.distributions import (
    PowerLorenz,
    allocate_counts,
    allocate_money,
    lorenz_shares,
    match_residences,
    monetary_array,
    numpy_stream,
    price_field,
    validate_shape,
)
from utils.validation.money import validate_money


@dataclass(frozen=True, slots=True)
class GridPopulationConfig:
    rows: int = 4
    columns: int = 4
    seed: int = 0
    mean_annual_income: Decimal = Decimal("50000")
    periods_per_year: int = 12
    income_curve: Callable[[float], float] = PowerLorenz(2)
    ownership_curve: Callable[[float], float] = PowerLorenz(3)
    initial_cash: Decimal = Decimal("10000")
    reference_price: Decimal = Decimal("250000")
    price_spread: float = 0.4
    length_scale: float = 2.0
    placement_noise: float = 0.1
    placement_mode: Literal["income", "random"] = "income"
    rent_per_period: Decimal = Decimal("1000")

    def __post_init__(self) -> None:
        validate_shape(self.rows, self.columns)
        if type(self.periods_per_year) is not int or self.periods_per_year <= 0:
            raise ValueError("periods_per_year must be a positive integer")
        for name in ("mean_annual_income", "initial_cash", "reference_price", "rent_per_period"):
            validate_money(getattr(self, name), field=name)
        if self.reference_price == 0:
            raise ValueError("reference_price must be positive")
        if any(
            not isfinite(v) or v < 0
            for v in (
                self.price_spread,
                self.length_scale,
                self.placement_noise,
            )
        ):
            raise ValueError("noise parameters must be finite and nonnegative")
        numpy_stream(self.seed, "validation")
        if self.placement_mode not in ("income", "random"):
            raise ValueError("Unknown placement mode")


class GridPopulationFactory:
    @staticmethod
    def create(config: GridPopulationConfig) -> Scenario:
        count = config.rows * config.columns
        shares = lorenz_shares(config.income_curve, count)
        annual = allocate_money(
            config.mean_annual_income * count, shares, numpy_stream(config.seed, "income")
        )
        quota_array = allocate_counts(
            lorenz_shares(config.ownership_curve, count),
            count,
            numpy_stream(config.seed, "ownership-counts"),
        )
        prices = price_field(
            (config.rows, config.columns),
            reference_price=float(config.reference_price),
            spread=config.price_spread,
            length_scale=config.length_scale,
            rng=numpy_stream(config.seed, "prices"),
        )
        cells = [(a, b) for a in range(config.rows) for b in range(config.columns)]
        stored_prices = tuple(
            max(
                Decimal("0.01"),
                Decimal(str(float(prices[a, b]))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            )
            for a, b in cells
        )
        placement_rng = numpy_stream(config.seed, "placement")
        placement = (
            placement_rng.permutation(count)
            if config.placement_mode == "random"
            else match_residences(
                monetary_array(annual),
                monetary_array(stored_prices),
                noise=config.placement_noise,
                rng=placement_rng,
            )
        )
        residents = dict(enumerate(int(person) for person in placement))
        # Preserve income ordering while making ownership ranks within ties seed-dependent.
        tie_rng = numpy_stream(config.seed, "income-ranking")
        ranking = sorted(range(count), key=lambda i: (annual[i], tie_rng.random()))
        ranked_quotas = dict(zip(ranking, (int(q) for q in quota_array), strict=True))
        quotas = tuple(ranked_quotas[i] for i in range(count))
        owners: dict[int, int] = {}
        remaining = list(quotas)
        for cell, person in residents.items():
            if quotas[person]:
                owners[cell] = person
                remaining[person] -= 1
        # Shuffle capacity slots: uniform among remaining ownership slots, not owners.
        slots = [i for i, capacity in enumerate(remaining) for _ in range(capacity)]
        ownership = numpy_stream(config.seed, "ownership-titles")
        ownership.shuffle(slots)
        for cell in sorted(residents):
            if cell not in owners:
                owners[cell] = slots.pop()
        people = tuple(
            Entity(i + 1, config.initial_cash, value / config.periods_per_year, annual_income=value)
            for i, value in enumerate(annual)
        )
        homes = tuple(
            Home(
                id=j + 1,
                region_id=1,
                owner_id=owners[j] + 1,
                market_value=stored_prices[j],
                occupant_id=residents[j] + 1,
                rent=config.rent_per_period if owners[j] != residents[j] else Decimal(0),
                position=(a, b),
            )
            for j, (a, b) in enumerate(cells)
        )
        return Scenario(
            (Region(1, "Grid"),),
            people,
            tuple(Household(p.id, p.id) for p in people),
            homes,
            grid_shape=(config.rows, config.columns),
            seed=config.seed,
        )
