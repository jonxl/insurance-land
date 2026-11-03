"""Matched Peace, Standard and Chaos worlds with fixed baseline policies."""

from dataclasses import dataclass, replace
from decimal import Decimal
from math import exp, isfinite, log
from typing import Literal

from agents.house import HouseAgent
from agents.insurance import InsurancePlanAgent
from agents.policies import assigned_affordable_coverage
from domain.disasters import DisasterConfig
from domain.insurance import Insurer, InsurerObservation, Offer, Product
from environment import Environment
from experiments.portfolios import insurer_portfolios
from factories import EnvironmentFactory, GridPopulationConfig, GridPopulationFactory
from utils.distributions import PowerLorenz, TweedieRadius


@dataclass(frozen=True)
class WorldSpec:
    name: Literal["Peace", "Standard", "Chaos"] = "Standard"
    chaos_rate_ratio: float = 10.0
    seed: int = 42
    rows: int = 8
    columns: int = 8
    periods: int = 120
    rate: float | None = None
    homes_per_region: int = 4
    radius_mean: float = 0.3
    radius_dispersion: float = 1.5

    def __post_init__(self) -> None:
        if self.rate is None:
            object.__setattr__(self, "rate", 0.1 if self.name == "Standard" else 0.5)
        if type(self.periods) is not int or self.periods <= 0:
            raise ValueError("periods must be a positive integer")
        if self.name not in ("Peace", "Standard", "Chaos"):
            raise ValueError("Unknown world")
        if not isfinite(self.chaos_rate_ratio) or self.chaos_rate_ratio <= 1:
            raise ValueError("Chaos rate ratio must be finite and greater than one")
        self.population()
        self.disasters()
        if min(self.rows, self.columns) < 3:
            raise ValueError("World requires a grid at least 3 by 3")

    def population(self) -> GridPopulationConfig:
        config = GridPopulationConfig(
            rows=self.rows,
            columns=self.columns,
            seed=self.seed,
            homes_per_region=self.homes_per_region,
        )
        if self.name == "Peace":
            config = replace(
                config, income_curve=PowerLorenz(1),
                ownership_curve=PowerLorenz(1),
                price_spread=0,
                home_price_spread=0,
            )
        return config

    def disasters(self) -> DisasterConfig:
        return DisasterConfig(
            rate=self.rate,
            radius=TweedieRadius(self.radius_mean, self.radius_dispersion),
            risk_contrast=1,
            risk_length_scale=2,
        )

    def rates(self) -> tuple[float, ...]:
        """Use rate as the period mean; Chaos ends at ratio times its starting rate."""
        if self.name != "Chaos" or self.periods == 1:
            return (self.rate,) * self.periods
        factors = [
            exp(log(self.chaos_rate_ratio) * t / (self.periods - 1)) for t in range(self.periods)
        ]
        average = sum(factors) / self.periods
        return tuple(self.rate * factor / average for factor in factors)

    def create(self) -> Environment:
        """Return a fresh world after opening insurance, before any exposure."""
        firms = tuple(Insurer(i, name, Decimal("10000000")) for i, name in enumerate("ABC", 1))

        def quotes(observation: InsurerObservation) -> tuple[Offer, ...]:
            return tuple(
                Offer(
                    id=observation.firm.id * 10 + index,
                    insurer_id=observation.firm.id,
                    product=product,
                    premium=Decimal(100 + 25 * observation.firm.id),
                    limit=Decimal("500000") if product != Product.RENTERS else Decimal("10000"),
                    deductible=Decimal("100"),
                    term_periods=self.periods,
                    contents_value=Decimal("10000") if product == Product.RENTERS else Decimal(0),
                )
                for index, product in enumerate(Product, 1)
            )

        scenario = GridPopulationFactory.create(self.population())
        assignments = insurer_portfolios(
            scenario.homes, [f.id for f in firms], self.population().ownership_curve, self.seed
        )
        scenario = replace(scenario, insurance_assignments=tuple(assignments.items()))
        world = EnvironmentFactory.from_scenario(
            scenario,
            disasters=self.disasters(),
            insurers=firms,
            insurer_agents={f.id: InsurancePlanAgent(quotes) for f in firms},
            agent_factory=lambda _: HouseAgent(
                insurance_policy=lambda observation: assigned_affordable_coverage(
                    observation, assignments
                )
            ),
        )
        world.open_insurance()
        return world
