from decimal import Decimal

import pytest

from experiments.standard import StandardWorld


def test_standard_world_opens_coverage_and_reproduces_trajectory() -> None:
    spec = StandardWorld(rows=4, columns=4, periods=3)
    first, second = spec.create(), spec.create()
    assert first.period == 0
    assert first.contracts
    assert all(c.ends_at == 3 for c in first.contracts)
    assert sum(p.annual_income or Decimal(0) for p in first.people.values()) == 16 * 50000
    total_cash = sum(p.cash for p in first.people.values()) + sum(
        firm.capital for firm in first.insurers.values()
    )
    assert total_cash == 16 * 10000 + 3 * 10000000
    assert first.grid_snapshot() == second.grid_snapshot()
    for _ in range(3):
        assert first.step() == second.step()


@pytest.mark.parametrize("periods", [0, -1, True])
def test_standard_rejects_invalid_horizon(periods: int) -> None:
    with pytest.raises(ValueError):
        StandardWorld(periods=periods)
