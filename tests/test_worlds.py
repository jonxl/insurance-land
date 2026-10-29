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
    for spec, scenario in zip(specs, scenarios, strict=True):
        assert sum(p.cash for p in scenario.people) == 16 * 10000
        assert sum(p.annual_income or Decimal(0) for p in scenario.people) == 16 * 50000
        assert sum(spec.rates()) == pytest.approx(5)
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
