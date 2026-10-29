"""Seeded distributions and allocation helpers for population and disaster setup."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from hashlib import sha256
from math import isfinite
from random import Random

import numpy as np
from numpy.typing import ArrayLike, NDArray

from utils.validation.money import validate_money


def random_stream(seed: int, component: str) -> Random:
    if type(seed) is not int:
        raise TypeError("seed must be an integer")
    digest = sha256(f"{seed}:{component}".encode()).digest()
    return Random(int.from_bytes(digest, "big"))


@dataclass(frozen=True, slots=True)
class PowerLorenz:
    exponent: float = 2.0

    def __post_init__(self) -> None:
        if not isfinite(self.exponent) or self.exponent < 1:
            raise ValueError("Lorenz exponent must be finite and at least one")

    def __call__(self, percentile: float) -> float:
        return float(percentile**self.exponent)


def round_counts(
    targets: Sequence[Decimal], total: int, rng: Random | np.random.Generator
) -> tuple[int, ...]:
    """Nearest-integer (halves up), correcting the largest residual with seeded ties."""
    if type(total) is not int or total < 0:
        raise ValueError("total must be a nonnegative integer")
    for target in targets:
        validate_money(target, field="target")
    if abs(sum(targets, Decimal(0)) - total) > Decimal("1e-20"):
        raise ValueError("targets must sum to total")
    counts = [int(v.to_integral_value(rounding=ROUND_HALF_UP)) for v in targets]
    difference = total - sum(counts)
    while difference:
        direction = 1 if difference > 0 else -1
        candidates = [i for i in range(len(counts)) if direction > 0 or counts[i] > 0]
        residuals = {i: direction * (targets[i] - counts[i]) for i in candidates}
        largest = max(residuals.values())
        selected = int(rng.choice([i for i in candidates if residuals[i] == largest]))
        counts[selected] += direction
        difference -= direction
    return tuple(counts)


def allocate_money(
    total: Decimal, shares: ArrayLike, rng: np.random.Generator
) -> tuple[Decimal, ...]:
    """Allocate exact cents, keeping all settlement arithmetic in Decimal."""
    validate_money(total, field="total")
    cents = total * 100
    if cents != cents.to_integral_value():
        raise ValueError("total must be an exact number of cents")
    values = _probabilities(shares, ndim=1)
    decimals = [Decimal(str(float(value))) for value in values]
    denominator = sum(decimals)
    targets = [cents * value / denominator for value in decimals]
    # Decimal division may leave a final context-rounding residual.
    targets[-1] += cents - sum(targets)
    return tuple(Decimal(n) / 100 for n in round_counts(targets, int(cents), rng))


def validate_shape(rows: int, columns: int) -> None:
    if any(type(v) is not int or v <= 0 for v in (rows, columns)):
        raise ValueError("grid dimensions must be positive integers")


FloatArray = NDArray[np.float64]
IntArray = NDArray[np.int64]
TOLERANCE = 1e-12


def numpy_stream(seed: int, component: str) -> np.random.Generator:
    """Stable labeled streams; independent of Python's randomized hash."""
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if not isinstance(component, str) or not component:
        raise ValueError("component must be a nonempty string")
    digest = sha256(f"{seed}:{component}".encode()).digest()
    return np.random.Generator(np.random.PCG64(int.from_bytes(digest, "big")))


def _array(values: ArrayLike, ndim: int) -> FloatArray:
    result = np.array(values, dtype=np.float64, copy=True)
    if result.ndim != ndim or not result.size or not np.isfinite(result).all():
        raise ValueError(f"Expected a nonempty finite {ndim}-dimensional array")
    return result


def _nonnegative(value: float, name: str) -> None:
    if not isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")


def _probabilities(values: ArrayLike, ndim: int) -> FloatArray:
    result = _array(values, ndim)
    if np.any(result < 0) or not np.isclose(result.sum(), 1, atol=TOLERANCE, rtol=0):
        raise ValueError("probabilities must be nonnegative and sum to one")
    return result / result.sum()


def smooth_field(noise: ArrayLike, length_scale: float) -> FloatArray:
    """Finite-grid Gaussian smoothing with unit marginal variance, without padding."""
    field = _array(noise, 2)
    _nonnegative(length_scale, "length_scale")
    if length_scale == 0:
        return field

    def weights(size: int) -> FloatArray:
        positions = np.arange(size, dtype=np.float64)
        # Tiny positive scales converge to identity; infinite distances are harmless.
        with np.errstate(over="ignore", under="ignore"):
            distances = (positions[:, None] - positions[None, :]) / length_scale
            matrix = np.exp(-0.5 * distances**2)
        return matrix / np.sqrt(np.sum(matrix**2, axis=1, keepdims=True))

    with np.errstate(over="ignore", invalid="ignore"):
        result = weights(field.shape[0]) @ field @ weights(field.shape[1]).T
    if not np.isfinite(result).all():
        raise ValueError("smoothing produced nonfinite values")
    return result


def lorenz_shares(curve: Callable[[float], float], count: int) -> FloatArray:
    """Individual shares in resource-rank order; validate sampled Lorenz boundaries."""
    if type(count) is not int or count <= 0:
        raise ValueError("count must be a positive integer")
    points = _array([curve(i / count) for i in range(count + 1)], 1)
    if (
        np.any(points < -TOLERANCE)
        or np.any(points > 1 + TOLERANCE)
        or abs(points[0]) > TOLERANCE
        or abs(points[-1] - 1) > TOLERANCE
    ):
        raise ValueError("Lorenz values must lie in [0, 1] with endpoints zero and one")
    points = np.clip(points, 0, 1)
    points[0], points[-1] = 0, 1
    shares = np.diff(points)
    if np.any(shares < -TOLERANCE) or np.any(np.diff(shares) < -TOLERANCE):
        raise ValueError("Lorenz curve must be nondecreasing and convex")
    shares = np.maximum(shares, 0)
    return shares / shares.sum()


def allocate_counts(shares: ArrayLike, total: int, rng: np.random.Generator) -> IntArray:
    """Half-up quota allocation with largest-residual correction and seeded ties."""
    values = _probabilities(shares, 1)
    if type(total) is not int or not 0 <= total <= 2**53 - 1:
        raise ValueError("total must be an integer between zero and 2**53 - 1")
    targets = total * values
    # Avoid adding 0.5 to large integers, which can round an integer upward.
    floors = np.floor(targets)
    counts = (floors + ((targets - floors) >= 0.5)).astype(np.int64)
    difference = total - sum(int(n) for n in counts)
    while difference:
        direction = 1 if difference > 0 else -1
        candidates = np.flatnonzero(
            np.ones(counts.size, dtype=bool) if direction > 0 else counts > 0
        )
        residuals = direction * (targets[candidates] - counts[candidates])
        tied = candidates[np.isclose(residuals, residuals.max(), atol=TOLERANCE, rtol=0)]
        selected = int(rng.choice(tied))
        counts[selected] += direction
        difference -= direction
    return counts


def price_field(
    shape: tuple[int, int],
    *,
    reference_price: float,
    spread: float,
    length_scale: float,
    rng: np.random.Generator,
) -> FloatArray:
    validate_shape(*shape)
    if not isfinite(reference_price) or reference_price <= 0:
        raise ValueError("reference_price must be finite and positive")
    _nonnegative(spread, "spread")
    _nonnegative(length_scale, "length_scale")
    field = smooth_field(rng.normal(size=shape), length_scale)
    with np.errstate(over="ignore", under="ignore", invalid="ignore"):
        prices = reference_price * np.exp(spread * field)
    if not np.isfinite(prices).all() or np.any(prices <= 0):
        raise ValueError("price parameters produce nonfinite or zero prices")
    return prices


def anchor_probabilities(weights: ArrayLike, footprint: tuple[int, int]) -> FloatArray:
    field = _array(weights, 2)
    validate_shape(*footprint)
    if np.any(field <= 0):
        raise ValueError("weights must be positive")
    rows, columns = field.shape
    height, width = footprint
    if height > rows or width > columns:
        raise ValueError("Disaster footprint must fit within the grid")
    eligible = field[: rows - height + 1, : columns - width + 1]
    with np.errstate(under="ignore"):
        scaled = eligible / eligible.max()
        probabilities = scaled / scaled.sum()
    if np.any(probabilities <= 0):
        raise ValueError("risk range produces zero probabilities")
    return probabilities


def monetary_array(values: Sequence[Decimal]) -> FloatArray:
    """Convert domain money for ranking without collapsing distinct monetary values."""
    result = _array([float(value) for value in values], 1)
    distinct = sorted(set(values))
    converted = [float(value) for value in distinct]
    if any(a >= b for a, b in zip(converted, converted[1:], strict=False)):
        raise ValueError("monetary magnitude loses ordering in float conversion")
    return result


def match_residences(
    incomes: ArrayLike,
    prices: ArrayLike,
    *,
    noise: float,
    rng: np.random.Generator,
) -> IntArray:
    income = _array(incomes, 1)
    price = _array(prices, 1)
    _nonnegative(noise, "noise")
    if income.size != price.size or np.any(income < 0) or np.any(price <= 0):
        raise ValueError("Matching requires equal counts, nonnegative incomes and positive prices")
    _, inverse, counts = np.unique(income, return_inverse=True, return_counts=True)
    percentiles = (np.cumsum(counts) - counts / 2) / income.size
    with np.errstate(over="ignore", invalid="ignore"):
        scores = percentiles[inverse] + noise * rng.normal(size=income.size)
    if not np.isfinite(scores).all():
        raise ValueError("placement noise produces nonfinite scores")
    people = np.lexsort((rng.permutation(income.size), scores))
    homes = np.lexsort((rng.permutation(price.size), price))
    residents = np.empty(income.size, dtype=np.int64)
    residents[homes] = people
    return residents


def sample_disasters(
    rate: float,
    probabilities: ArrayLike,
    rng: np.random.Generator,
    *,
    location_rng: np.random.Generator,
) -> IntArray:
    _nonnegative(rate, "rate")
    distribution = _probabilities(probabilities, 2)
    if rate == 0:
        return np.empty((0, 2), dtype=np.int64)
    try:
        count = rng.poisson(rate)
    except ValueError as exc:
        raise ValueError("rate exceeds the supported Poisson range") from exc
    if count == 0:
        return np.empty((0, 2), dtype=np.int64)
    indices = location_rng.choice(
        distribution.size, size=count, replace=True, p=distribution.ravel(order="C")
    )
    return np.column_stack(np.unravel_index(indices, distribution.shape)).astype(np.int64)
