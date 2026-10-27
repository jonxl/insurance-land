from dataclasses import replace
from decimal import Decimal

import pytest

from src.domain.disasters import DisasterConfig
from src.domain.housing import HousingMarket
from src.factories import EnvironmentFactory, GridPopulationConfig, GridPopulationFactory
from src.utils.distributions import PowerLorenz


def test_grid_is_reproducible_and_has_consistent_relationships() -> None:
    config = GridPopulationConfig(rows=3, columns=4, seed=42)
    scenario = GridPopulationFactory.create(config)
    assert scenario == GridPopulationFactory.create(config)
    environment = EnvironmentFactory.create(config)
    board = environment.grid_snapshot()
    assert len(board.prices) == 3 and len(board.prices[0]) == 4
    assert {v for row in board.residents for v in row} == set(environment.people)
    assert (
        sum(p.annual_income or Decimal(0) for p in scenario.people)
        == 12 * config.mean_annual_income
    )
    counts = [sum(h.owner_id == p.id for h in scenario.homes) for p in scenario.people]
    assert sum(counts) == 12
    assert 0 in counts and max(counts) > 1
    for person, count in zip(scenario.people, counts, strict=True):
        residence = next(h for h in scenario.homes if h.occupant_id == person.id)
        assert (residence.owner_id == person.id) == (count > 0)
        assert residence.rent == (0 if count else config.rent_per_period)
    original = dict(environment.people)
    environment.step(disaster_rate=None)
    assert all(environment.people[i].income == p.income for i, p in original.items())
    assert board == environment.grid_snapshot()  # Financial changes do not mutate grid data.


def test_placement_changes_do_not_change_prices_or_quotas() -> None:
    base = GridPopulationConfig(rows=4, columns=4, seed=42, placement_noise=0)
    first = GridPopulationFactory.create(base)
    second = GridPopulationFactory.create(replace(base, placement_noise=100))
    assert [h.market_value for h in first.homes] == [h.market_value for h in second.homes]
    assert first.people == second.people
    assert [h.occupant_id for h in first.homes] != [h.occupant_id for h in second.homes]
    for p in first.people:
        assert sum(h.owner_id == p.id for h in first.homes) == sum(
            h.owner_id == p.id for h in second.homes
        )


def test_equal_ownership_and_single_cell() -> None:
    config = GridPopulationConfig(rows=1, columns=1, ownership_curve=PowerLorenz(1))
    environment = EnvironmentFactory.create(config)
    assert environment.homes[1].owner_id == environment.homes[1].occupant_id == 1


def test_disaster_displaces_once_preserves_title_and_snapshot() -> None:
    environment = EnvironmentFactory.create(
        GridPopulationConfig(rows=2, columns=2, seed=3),
        disasters=DisasterConfig(rate=20, footprint_rows=2, footprint_columns=2),
    )
    before = environment.grid_snapshot()
    result = environment.step()
    losses = [h for event in result.disasters for h in event.losses]
    assert len(result.disasters) > 1
    assert len(losses) == 4
    assert len({i for event in result.disasters for i in event.displaced_people}) == 4
    after = environment.grid_snapshot()
    assert after.owners == before.owners
    assert all(v > 0 for row in before.prices for v in row)
    assert all(v == 0 for row in after.prices for v in row)
    assert all(v == 0 for row in after.residents for v in row)
    assert all(environment.observe(i).residence is None for i in environment.people)
    assert not any(e.losses for e in environment.step().disasters)


def test_rate_override_and_invalid_step_preserve_disaster_sequence() -> None:
    config = GridPopulationConfig(rows=2, columns=3, seed=23)
    disaster = DisasterConfig(rate=4, footprint_rows=1, footprint_columns=2)
    first = EnvironmentFactory.create(config, disasters=disaster)
    second = EnvironmentFactory.create(config, disasters=disaster)
    with pytest.raises(ValueError):
        first.step({})
    assert first.step() == second.step()
    assert not first.step(disaster_rate=0).disasters
    assert len(first.grid_snapshot().prices) == 2


def test_destroyed_homes_cannot_be_occupied() -> None:
    scenario = GridPopulationFactory.create(GridPopulationConfig(rows=1, columns=1))
    market = HousingMarket()
    market.add_entity(scenario.people[0])
    market.add_home(scenario.homes[0])
    market.destroy(((0, 0),))
    with pytest.raises(ValueError, match="destroyed"):
        market.move_in(1, 1, rent=Decimal(0))


def test_invalid_grid_and_footprint() -> None:
    with pytest.raises(ValueError):
        GridPopulationConfig(rows=0)
    with pytest.raises(ValueError, match="fit"):
        EnvironmentFactory.create(
            GridPopulationConfig(rows=1, columns=1), disasters=DisasterConfig(footprint_rows=2)
        )
    scenario = GridPopulationFactory.create(GridPopulationConfig(rows=1, columns=2))
    with pytest.raises(ValueError, match="unique"):
        EnvironmentFactory.from_scenario(
            replace(
                scenario, homes=(scenario.homes[0], replace(scenario.homes[1], position=(0, 0)))
            )
        )
