from decimal import Decimal
from math import exp, sqrt
from random import Random

import numpy as np
import pytest

from utils.distributions import (
    PowerLorenz,
    allocate_counts,
    allocate_money,
    anchor_probabilities,
    lorenz_shares,
    numpy_stream,
    price_field,
    round_counts,
    sample_disasters,
    smooth_field,
)


def test_lorenz_allocations_preserve_total_and_inequality() -> None:
    shares = lorenz_shares(PowerLorenz(2), 4)
    np.testing.assert_array_equal(shares, [0.0625, 0.1875, 0.3125, 0.4375])
    values = allocate_money(Decimal("101.03"), shares, np.random.default_rng(1))
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
            lorenz_shares(curve, 8)


def test_separable_price_field_matches_full_weight_formula() -> None:
    rng = np.random.default_rng(7)
    noise = rng.normal(size=(2, 3))
    actual = price_field(
        (2, 3), reference_price=100, spread=0.3, length_scale=1.2, rng=np.random.default_rng(7)
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
    prices = price_field(
        (2, 2), reference_price=100, spread=0, length_scale=0, rng=numpy_stream(42, "prices")
    )
    np.testing.assert_array_equal(prices, np.full((2, 2), 100))
    placement = numpy_stream(42, "placement")
    for _ in range(100):
        placement.random()
    assert numpy_stream(42, "prices").random() == numpy_stream(42, "prices").random()
    assert numpy_stream(42, "prices").random() != numpy_stream(42, "placement").random()


def test_poisson_moments_and_zero_probability() -> None:
    rng = np.random.default_rng(91)
    locations = np.random.default_rng(92)
    samples = [len(sample_disasters(2, [[1.0]], rng, location_rng=locations)) for _ in range(20000)]
    assert np.mean(samples) == pytest.approx(2, abs=0.05)
    assert np.var(samples) == pytest.approx(2, abs=0.1)
    assert samples.count(0) / len(samples) == pytest.approx(exp(-2), abs=0.01)
    assert sample_disasters(0, [[1.0]], rng, location_rng=locations).shape == (0, 2)


@pytest.mark.parametrize("rate", [-1, float("nan"), float("inf"), 1e30])
def test_invalid_poisson_rates(rate: float) -> None:
    with pytest.raises(ValueError):
        sample_disasters(
            rate, [[1.0]], np.random.default_rng(1), location_rng=np.random.default_rng(2)
        )


def test_matching_respects_rank_and_preserves_one_to_one_assignment() -> None:
    from utils.distributions import match_residences

    incomes = [10.0, 20.0, 30.0]
    prices = [300.0, 100.0, 200.0]
    np.testing.assert_array_equal(
        match_residences(incomes, prices, noise=0, rng=np.random.default_rng(1)), [2, 0, 1]
    )
    tied = match_residences([10.0] * 3, prices, noise=0, rng=np.random.default_rng(1))
    assert sorted(tied) == [0, 1, 2]
    np.testing.assert_array_equal(
        tied, match_residences([10.0] * 3, prices, noise=0, rng=np.random.default_rng(1))
    )
    with pytest.raises(ValueError):
        match_residences(incomes, prices[:2], noise=0, rng=np.random.default_rng(1))


def test_smoothing_variance_and_copy_contract() -> None:
    basis = np.eye(6).reshape(6, 2, 3)
    coefficients = np.stack([smooth_field(e, 1.2) for e in basis])
    np.testing.assert_allclose(np.sum(coefficients**2, axis=0), np.ones((2, 3)))
    original = np.arange(6.0).reshape(2, 3)
    copy = smooth_field(original, 0)
    np.testing.assert_array_equal(copy, original)
    copy[0, 0] = -10
    assert original[0, 0] == 0
    np.testing.assert_array_equal(smooth_field([[2.0]], 20), [[2.0]])
    np.testing.assert_array_equal(smooth_field(original, 1e-300), original)


def test_anchor_normalization_excludes_invalid_corners() -> None:
    weights = np.array([[1.0, 3.0, 100], [50, 50, 50]])
    np.testing.assert_allclose(anchor_probabilities(weights, (2, 2)), [[0.25, 0.75]])
    np.testing.assert_array_equal(anchor_probabilities(weights, (2, 3)), [[1]])
    np.testing.assert_allclose(
        anchor_probabilities(np.ones((3, 4)), (2, 2)), np.full((2, 3), 1 / 6)
    )
    assert weights[0, 2] == 100
    np.testing.assert_allclose(
        anchor_probabilities(np.full((2, 2), 1e308), (1, 1)), np.full((2, 2), 0.25)
    )


@pytest.mark.parametrize(
    "shares,total,expected",
    [
        ([0.5, 0.5], 1, [0, 1]),
        ([0.1, 0.1, 0.8], 4, [0, 1, 3]),
        ([0.2, 0.8], 0, [0, 0]),
        ([1.0], 2**53 - 1, [2**53 - 1]),
    ],
)
def test_numpy_counts_conserve_quotas(shares: list[float], total: int, expected: list[int]) -> None:
    first = allocate_counts(shares, total, np.random.default_rng(42))
    assert sum(int(x) for x in first) == total
    assert sorted(first) == sorted(expected)
    np.testing.assert_array_equal(first, allocate_counts(shares, total, np.random.default_rng(42)))


def test_sampling_weighted_locations_and_stream_isolation() -> None:
    probabilities = np.array([[0.1, 0.2], [0.0, 0.7]])
    anchors = sample_disasters(
        30000, probabilities, numpy_stream(12, "count"), location_rng=numpy_stream(12, "location")
    )
    frequencies = np.bincount(anchors[:, 0] * 2 + anchors[:, 1], minlength=4) / len(anchors)
    np.testing.assert_allclose(frequencies, probabilities.ravel(), atol=0.015, rtol=0)
    other = sample_disasters(
        30000, [[1.0]], numpy_stream(12, "count"), location_rng=numpy_stream(12, "location")
    )
    assert len(other) == len(anchors)
    assert np.all(other == 0)  # Repeated anchors are retained.
    count_rng, location_rng = numpy_stream(1, "c"), numpy_stream(1, "l")
    before = (count_rng.bit_generator.state, location_rng.bit_generator.state)
    sample_disasters(0, probabilities, count_rng, location_rng=location_rng)
    assert before == (count_rng.bit_generator.state, location_rng.bit_generator.state)


def test_invalid_numerical_inputs_do_not_sample() -> None:
    rng = np.random.default_rng(4)
    before = rng.bit_generator.state
    for shares in ([0.1, 0.2], [-1.0, 2.0], [float("nan")], []):
        with pytest.raises(ValueError):
            allocate_counts(shares, 10, rng)
    for total in (-1, True, 2**53):
        with pytest.raises(ValueError):
            allocate_counts([1.0], total, rng)
    for field in ([], [[float("nan")]], [[float("inf")]]):
        with pytest.raises(ValueError):
            smooth_field(field, 1)
    for weights in ([[0.0]], [[-1.0]], [[float("inf")]]):
        with pytest.raises(ValueError):
            anchor_probabilities(weights, (1, 1))
    with pytest.raises(ValueError):
        anchor_probabilities([[1]], (2, 1))
    with pytest.raises(ValueError):
        price_field((2, 2), reference_price=100, spread=-1, length_scale=1, rng=rng)
    assert rng.bit_generator.state == before


def test_money_conversion_preserves_ties_and_rejects_collapsed_values() -> None:
    from utils.distributions import monetary_array

    np.testing.assert_array_equal(monetary_array([Decimal("1.01"), Decimal("1.01")]), [1.01, 1.01])
    with pytest.raises(ValueError, match="ordering"):
        monetary_array([Decimal("10000000000000000.00"), Decimal("10000000000000000.01")])
    shares = lorenz_shares(PowerLorenz(2), 13)
    money = allocate_money(Decimal("999.99"), shares, numpy_stream(9, "money"))
    assert sum(money) == Decimal("999.99")


def test_zero_spread_preserves_draw_consumption() -> None:
    first, second = numpy_stream(4, "p"), numpy_stream(4, "p")
    price_field((3, 4), reference_price=100, spread=0, length_scale=2, rng=first)
    price_field((3, 4), reference_price=100, spread=0.4, length_scale=2, rng=second)
    assert first.bit_generator.state == second.bit_generator.state
