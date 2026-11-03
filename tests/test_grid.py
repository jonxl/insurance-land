from collections import Counter
from dataclasses import replace
from decimal import Decimal

import pytest

from domain.disasters import DisasterConfig
from domain.housing import HousingMarket
from factories import EnvironmentFactory, GridPopulationConfig, GridPopulationFactory
from utils.distributions import PowerLorenz, TweedieRadius, numpy_stream, price_field


def test_grid_is_reproducible_and_has_consistent_relationships() -> None:
    config = GridPopulationConfig(rows=3, columns=4, seed=42)
    scenario = GridPopulationFactory.create(config)
    assert scenario == GridPopulationFactory.create(config)
    environment = EnvironmentFactory.create(config)
    board = environment.grid_snapshot()
    assert len(board.prices) == 3 and len(board.prices[0]) == 4
    assert {v for row in board.residents for region in row for v in region} == set(
        environment.people
    )
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
    assert all(v > 0 for row in before.prices for region in row for v in region)
    assert all(v == 0 for row in after.prices for region in row for v in region)
    assert all(v == 0 for row in after.residents for region in row for v in region)
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
    with pytest.raises(ValueError, match="at least one home"):
        EnvironmentFactory.from_scenario(
            replace(
                scenario, homes=(scenario.homes[0], replace(scenario.homes[1], position=(0, 0)))
            )
        )


def test_hidden_risk_is_fixed_private_and_counts_are_independent() -> None:
    import numpy as np

    config = GridPopulationConfig(rows=4, columns=5, seed=21)
    uniform = DisasterConfig(rate=5, footprint_rows=2, risk_contrast=0)
    spatial = replace(uniform, risk_contrast=1.5)
    probabilities = spatial.risk_probabilities((4, 5), seed=21)
    assert not probabilities.flags.writeable
    assert np.ptp(probabilities) > 0
    np.testing.assert_array_equal(probabilities, spatial.risk_probabilities((4, 5), seed=21))
    first = EnvironmentFactory.create(config, disasters=uniform)
    second = EnvironmentFactory.create(config, disasters=spatial)
    assert first.grid_snapshot() == second.grid_snapshot()
    assert not hasattr(second.observe(1), "risk_probabilities")
    for _ in range(5):
        assert len(first.step().disasters) == len(second.step().disasters)
    with pytest.raises(ValueError):
        probabilities[0, 0] = 1


def test_larger_regions_hold_more_homes_and_people_still_match_homes() -> None:
    config = GridPopulationConfig(rows=6, columns=6, seed=5, homes_per_region=4)
    scenario = GridPopulationFactory.create(config)
    sizes = Counter(h.position for h in scenario.homes)
    assert len(sizes) == 36 and min(sizes.values()) >= 1 and max(sizes.values()) > 4
    assert len(scenario.homes) == len(scenario.people) == 144
    assert len(scenario.regions) == 36
    environment = EnvironmentFactory.from_scenario(scenario)
    regional = price_field(
        (6, 6),
        reference_price=float(config.reference_price),
        spread=config.price_spread,
        length_scale=config.length_scale,
        rng=numpy_stream(5, "prices"),
    )
    assert len({h.market_value for h in scenario.homes}) > 36  # Homes in a region can differ.
    for home in scenario.homes[:20]:
        same_region = environment.homes_in_region(home.region_id)
        assert {h.position for h in same_region} == {home.position}
        mean = sum(h.market_value for h in same_region) / len(same_region)
        assert float(mean) == pytest.approx(float(regional[home.position]), abs=0.01)
    assert sorted(h.occupant_id for h in scenario.homes) == list(range(1, 145))
    board = environment.grid_snapshot()
    assert [len(region) for row in board.home_ids for region in row] == [
        sizes[a, b] for a in range(6) for b in range(6)
    ]


def test_region_sizes_are_spatially_smooth_and_can_be_even() -> None:
    def spread(contrast: float, length_scale: float, seed: int):
        config = GridPopulationConfig(
            rows=8,
            columns=8,
            seed=seed,
            homes_per_region=4,
            region_size_contrast=contrast,
            region_size_length_scale=length_scale,
        )
        sizes = Counter(h.position for h in GridPopulationFactory.create(config).homes)
        return [[sizes[a, b] for b in range(8)] for a in range(8)]

    assert {v for row in spread(0, 2, 1) for v in row} == {4}  # No contrast: every region even.

    def neighbor_gap(contrast: float, length_scale: float) -> float:
        grids = [spread(contrast, length_scale, seed) for seed in range(30)]
        gaps = [abs(g[a][b] - g[a][b + 1]) for g in grids for a in range(8) for b in range(7)]
        return sum(gaps) / len(gaps)

    assert neighbor_gap(1, 2) < neighbor_gap(1, 0)  # Smoothing keeps neighbors alike.


def test_one_disaster_strikes_every_home_in_its_regions() -> None:
    config = GridPopulationConfig(rows=5, columns=5, seed=2, homes_per_region=3)
    environment = EnvironmentFactory.create(
        config, disasters=DisasterConfig(rate=3, radius=TweedieRadius(), risk_contrast=1)
    )
    at_cell = Counter(h.position for h in environment.homes.values())
    event = next(e for _ in range(20) for e in environment.step().disasters if e.losses)
    assert {h.position for h in event.losses} <= set(event.cells)
    assert len(event.losses) == sum(at_cell[c] for c in event.cells)


def test_random_placement_preserves_resources_and_ownership_quotas() -> None:
    base = GridPopulationConfig(rows=4, columns=5, seed=9)
    ranked = GridPopulationFactory.create(base)
    random = GridPopulationFactory.create(replace(base, placement_mode="random"))
    assert ranked.people == random.people
    assert [h.market_value for h in ranked.homes] == [h.market_value for h in random.homes]
    assert sorted(h.occupant_id for h in random.homes if h.occupant_id) == list(range(1, 21))
    for person in ranked.people:
        assert sum(h.owner_id == person.id for h in ranked.homes) == sum(
            h.owner_id == person.id for h in random.homes
        )
