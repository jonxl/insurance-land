from decimal import Decimal
from math import exp, sqrt
from random import Random

import pytest

from src.utils.distributions import (
    PowerLorenz,
    allocate_money,
    gaussian_price_field,
    lorenz_shares,
    poisson_count,
    random_stream,
    round_counts,
)


def test_lorenz_allocations_preserve_total_and_inequality() -> None:
    shares = lorenz_shares(4, PowerLorenz(2))
    assert shares == (Decimal("0.0625"), Decimal("0.1875"), Decimal("0.3125"), Decimal("0.4375"))
    values = allocate_money(Decimal("101.03"), shares, Random(1))
    assert sum(values) == Decimal("101.03")
    assert list(values) == sorted(values)
    assert all(v * 100 == (v * 100).to_integral_value() for v in values)


@pytest.mark.parametrize(
    "targets,total",
    [
        (["0.4", "0.4", "2.2"], 3),
        (["0.5", "0.5", "1"], 2),
        (["0", "0", "0"], 0),
    ],
)
def test_rounding_corrects_both_directions(targets: list[str], total: int) -> None:
    decimals = [Decimal(v) for v in targets]
    counts = round_counts(decimals, total, Random(42))
    assert sum(counts) == total
    assert all(type(v) is int and v >= 0 for v in counts)
    assert counts == round_counts(decimals, total, Random(42))


def test_rounding_rejects_inconsistent_total() -> None:
    with pytest.raises(ValueError, match="sum"):
        round_counts([Decimal("0.2")], 3, Random(0))


def test_invalid_curves_are_rejected() -> None:
    for curve in (lambda p: p**0.5, lambda p: p / 2, lambda _: float("nan")):
        with pytest.raises(ValueError):
            lorenz_shares(8, curve)


def test_separable_price_field_matches_full_weight_formula() -> None:
    rng = Random(7)
    noise = [[rng.gauss(0, 1) for _ in range(3)] for _ in range(2)]
    actual = gaussian_price_field(
        2, 3, reference_price=100, spread=0.3, length_scale=1.2, rng=Random(7)
    )
    for a in range(2):
        for b in range(3):
            weights = [
                exp(-((a - u) ** 2 + (b - v) ** 2) / (2 * 1.2**2))
                for u in range(2)
                for v in range(3)
            ]
            weighted = sum(
                w * noise[u][v]
                for w, (u, v) in zip(
                    weights, ((u, v) for u in range(2) for v in range(3)), strict=True
                )
            ) / sqrt(sum(w * w for w in weights))
            assert actual[a][b] == pytest.approx(100 * exp(0.3 * weighted))


def test_zero_spread_and_independent_streams() -> None:
    prices = gaussian_price_field(
        2, 2, reference_price=100, spread=0, length_scale=0, rng=random_stream(42, "prices")
    )
    assert prices == ((100, 100), (100, 100))
    placement = random_stream(42, "placement")
    for _ in range(100):
        placement.random()
    assert random_stream(42, "prices").random() == random_stream(42, "prices").random()
    assert random_stream(42, "prices").random() != random_stream(42, "placement").random()


def test_poisson_moments_and_zero_probability() -> None:
    rng = Random(91)
    samples = [poisson_count(2, rng) for _ in range(20000)]
    mean = sum(samples) / len(samples)
    variance = sum((s - mean) ** 2 for s in samples) / len(samples)
    assert mean == pytest.approx(2, abs=0.05)
    assert variance == pytest.approx(2, abs=0.1)
    assert samples.count(0) / len(samples) == pytest.approx(exp(-2), abs=0.01)
    assert poisson_count(0, rng) == 0
    assert poisson_count(1000, Random(1)) > 0


@pytest.mark.parametrize("rate", [-1, float("nan"), float("inf")])
def test_invalid_poisson_rates(rate: float) -> None:
    with pytest.raises(ValueError):
        poisson_count(rate, Random(1))


def test_matching_respects_rank_and_preserves_one_to_one_assignment() -> None:
    from src.utils.distributions import match_residences

    incomes = [Decimal(10), Decimal(20), Decimal(30)]
    prices = [300.0, 100.0, 200.0]
    assert match_residences(incomes, prices, noise=0, rng=Random(1)) == (2, 0, 1)
    tied = match_residences([Decimal(10)] * 3, prices, noise=0, rng=Random(1))
    assert sorted(tied) == [0, 1, 2]
    assert tied == match_residences([Decimal(10)] * 3, prices, noise=0, rng=Random(1))
    with pytest.raises(ValueError):
        match_residences(incomes, prices[:2], noise=0, rng=Random(1))
