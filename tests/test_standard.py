from decimal import Decimal

import pytest

from experiments.standard import StandardWorld
from experiments.standard_report import home_tiles
from factories import GridPopulationFactory


def test_standard_world_opens_coverage_and_reproduces_trajectory() -> None:
    spec = StandardWorld(rows=4, columns=4, periods=3)
    first, second = spec.create(), spec.create()
    assert first.period == 0
    assert first.contracts
    assert all(c.ends_at == 3 for c in first.contracts)
    assert sum(p.annual_income or Decimal(0) for p in first.people.values()) == 64 * 50000
    total_cash = sum(p.cash for p in first.people.values()) + sum(
        firm.capital for firm in first.insurers.values()
    )
    assert total_cash == 64 * 10000 + 3 * 10000000
    assert first.grid_snapshot() == second.grid_snapshot()
    for _ in range(3):
        assert first.step() == second.step()


@pytest.mark.parametrize("periods", [0, -1, True])
def test_standard_rejects_invalid_horizon(periods: int) -> None:
    with pytest.raises(ValueError):
        StandardWorld(periods=periods)


def test_report_draws_every_home_inside_its_region() -> None:
    spec = StandardWorld(rows=4, columns=4, periods=1)
    homes = GridPopulationFactory.create(spec.population()).homes
    tiles, blocks = home_tiles(homes, (4, 4))
    assert len(tiles) == len(homes) == 64
    assert sorted(t[0] for t in tiles) == sorted(h.owner_id for h in homes)
    assert sum(w * h for _, _, _, w, h in tiles) == pytest.approx(16)
    # Every home covers the same area, so a neighborhood's size follows its home count.
    assert {round(w * h, 9) for _, _, _, w, h in tiles} == {0.25}
    assert len(blocks) == 16
