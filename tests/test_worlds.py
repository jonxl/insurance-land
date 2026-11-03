import json
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from experiments.generate_worlds import generate
from experiments.worlds import WorldSpec
from factories import GridPopulationFactory


def test_matched_worlds_initial_conditions_and_rate_budgets() -> None:
    specs = [
        WorldSpec(name=name, rows=4, columns=4, periods=10)
        for name in ("Peace", "Standard", "Chaos")
    ]
    scenarios = [GridPopulationFactory.create(s.population()) for s in specs]
    peace = scenarios[0]
    assert {h.market_value for h in peace.homes} == {Decimal(250000)}
    assert all(h.owner_id == h.occupant_id for h in peace.homes)
    assert {p.annual_income for p in peace.people} == {Decimal(50000)}
    assert scenarios[1] == scenarios[2]
    # Every world shares one geography, so comparisons see the same homes in the same places.
    assert [h.position for h in peace.homes] == [h.position for h in scenarios[1].homes]
    for spec, scenario in zip(specs, scenarios, strict=True):
        assert len(scenario.homes) == len(scenario.people) == 64
        assert sum(p.cash for p in scenario.people) == 64 * 10000
        assert sum(p.annual_income or Decimal(0) for p in scenario.people) == 64 * 50000
        assert sum(spec.rates()) == pytest.approx(1 if spec.name == "Standard" else 5)
        np.testing.assert_array_equal(
            spec.disasters().risk_probabilities((4, 4), seed=42),
            specs[0].disasters().risk_probabilities((4, 4), seed=42),
        )
    rates = specs[2].rates()
    assert all(b > a for a, b in zip(rates, rates[1:], strict=False))
    assert rates[-1] / rates[0] == pytest.approx(10)
    assert WorldSpec(name="Chaos", periods=1).rates() == (0.5,)


def test_export_contains_all_worlds_and_no_whole_world_chart(tmp_path: Path) -> None:
    generate(tmp_path, periods=2, rows=3, columns=3)
    bundle = json.loads((tmp_path / "assets" / "world-history.json").read_text())
    assert set(bundle["worlds"]) == {"Peace", "Standard", "Chaos"}
    assert all(len(w["frames"]) == 3 for w in bundle["worlds"].values())
    html = (tmp_path / "diagnostics.html").read_text()
    assert "worldChart" not in html
    assert "Whole-world history" not in html
    assert "__WORLD_DATA__" not in html


@pytest.mark.parametrize("name", ["Peace", "Standard", "Chaos"])
def test_insurers_follow_existing_owner_portfolios(name):
    spec = WorldSpec(name=name, rows=4, columns=4, periods=3)
    world = spec.create()
    original = GridPopulationFactory.create(spec.population())
    assignments = world.insurance_assignments
    assert set(assignments) == set(world.homes)
    assert set(assignments.values()) == {1, 2, 3}
    assert set(c.offer.insurer_id for c in world.contracts) == {1, 2, 3}
    assert all(c.offer.insurer_id == assignments[c.home_id] for c in world.contracts)
    assert tuple(world.homes.values()) == original.homes
    for owner in {home.owner_id for home in original.homes}:
        assert len({assignments[h.id] for h in original.homes if h.owner_id == owner}) == 1
    assert assignments == spec.create().insurance_assignments
    for _ in spec.rates():
        world.step()
    assert assignments == world.insurance_assignments


def test_standard_and_chaos_share_insurer_field():
    assert WorldSpec(name="Standard").create().insurance_assignments == (
        WorldSpec(name="Chaos").create().insurance_assignments
    )
