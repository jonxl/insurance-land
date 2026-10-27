from dataclasses import replace
from decimal import Decimal

import pytest

from factories import (
    EnvironmentFactory,
    PopulationConfig,
    PopulationFactory,
    RegionConfig,
)


def test_seed_reproduces_population_and_trajectory() -> None:
    config = PopulationConfig(
        regions=(RegionConfig("Coast", 10, 12), RegionConfig("Inland", 20, 18)), seed=42
    )
    scenario = PopulationFactory.create(config)
    assert scenario == PopulationFactory.create(config)
    assert scenario != PopulationFactory.create(replace(config, seed=43))

    first = EnvironmentFactory.create(config)
    second = EnvironmentFactory.create(config)
    for _ in range(3):
        assert first.step() == second.step()
    assert len(first.regions) == 2
    assert len(first.people) == len(first.households) == len(first.agents) == 30
    assert len(first.homes) == 30


def test_generated_population_preserves_relationships() -> None:
    environment = EnvironmentFactory.create(
        PopulationConfig(regions=(RegionConfig("Coast", 10, 12), RegionConfig("Inland", 20, 18)))
    )
    occupants = [home.occupant_id for home in environment.homes.values() if home.occupant_id]
    assert len(occupants) == len(set(occupants)) == 28
    assert sum(home.occupant_id is None for home in environment.homes.values()) == 2
    assert sum(environment.observe(person).residence is None for person in environment.people) == 2
    assert all(home.owner_id in environment.people for home in environment.homes.values())
    assert all(home.region_id in environment.regions for home in environment.homes.values())
    assert len({household.person_id for household in environment.households.values()}) == 30


@pytest.mark.parametrize("rate", [0.0, 1.0])
def test_owner_occupancy_rate_extremes(rate: float) -> None:
    scenario = PopulationFactory.create(
        PopulationConfig(regions=(RegionConfig("Coast", 8),), owner_occupancy_rate=rate)
    )
    assert all((home.owner_id == home.occupant_id) == bool(rate) for home in scenario.homes)
    assert all(home.rent == (Decimal("0") if rate else Decimal("1000")) for home in scenario.homes)


def test_single_owner_can_own_multiple_homes() -> None:
    environment = EnvironmentFactory.create(
        PopulationConfig(regions=(RegionConfig("Coast", 1, 3),), owner_occupancy_rate=0)
    )
    observation = environment.observe(1)
    assert len(observation.owned_homes) == 3
    assert observation.residence is not None
    assert all(home.owner_id == 1 and home.rent == 0 for home in environment.homes.values())


def test_zero_homes_does_not_create_a_special_person_type() -> None:
    environment = EnvironmentFactory.create(
        PopulationConfig(regions=(RegionConfig("Coast", 3, 0), RegionConfig("Empty", 0)))
    )
    assert len(environment.people) == 3
    assert not environment.homes
    assert all(environment.observe(person).residence is None for person in environment.people)
    assert len(environment.step().actions) == 3


@pytest.mark.parametrize(
    ("households", "homes"), [(-1, None), (1, -1), (0, 1), (True, None), (1, True)]
)
def test_invalid_population_counts_are_rejected(households: int, homes: int | None) -> None:
    with pytest.raises(ValueError):
        RegionConfig("Coast", households, homes)


@pytest.mark.parametrize("rate", [-0.1, 1.1, float("nan"), float("inf")])
def test_invalid_owner_occupancy_rate_is_rejected(rate: float) -> None:
    with pytest.raises(ValueError, match="Owner occupancy rate"):
        PopulationConfig(regions=(), owner_occupancy_rate=rate)


def test_population_budgets_and_contract_values_are_configurable() -> None:
    config = PopulationConfig(
        regions=(RegionConfig("Coast", 3),),
        initial_cash=Decimal("5"),
        income_per_period=Decimal("2"),
        home_value=Decimal("100"),
        rent_per_period=Decimal("3"),
        owner_occupancy_rate=0,
    )
    scenario = PopulationFactory.create(config)
    assert all(person.cash == 5 and person.income == 2 for person in scenario.people)
    assert all(home.market_value == 100 and home.rent == 3 for home in scenario.homes)
    with pytest.raises(ValueError, match="initial_cash"):
        replace(config, initial_cash=Decimal("-1"))
