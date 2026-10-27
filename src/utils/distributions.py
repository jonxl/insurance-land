"""Seeded distributions and allocation helpers for population and disaster setup."""

from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from hashlib import sha256
from math import exp, isfinite, sqrt
from random import Random

from src.utils.validation.money import validate_money


def random_stream(seed: int, component: str) -> Random:
    if type(seed) is not int:
        raise TypeError("seed must be an integer")
    digest = sha256(f"{seed}:{component}".encode()).digest()
    return Random(int.from_bytes(digest, "big"))


def lorenz_shares(count: int, curve: Callable[[float], float]) -> tuple[Decimal, ...]:
    """Validate the curve on population boundaries and return exact-sum shares.

    Convexity between sampled boundaries is the caller's responsibility.
    """
    if type(count) is not int or count <= 0:
        raise ValueError("count must be a positive integer")
    values = [curve(i / count) for i in range(count + 1)]
    if any(not isfinite(v) or not 0 <= v <= 1 for v in values):
        raise ValueError("Lorenz values must be finite and in [0, 1]")
    if values[0] != 0 or values[-1] != 1:
        raise ValueError("Lorenz endpoints must be zero and one")
    slopes = [b - a for a, b in zip(values, values[1:], strict=False)]
    if any(v < 0 for v in slopes) or any(
        b + 1e-12 < a for a, b in zip(slopes, slopes[1:], strict=False)
    ):
        raise ValueError("Lorenz curve must be nondecreasing and convex")
    points = [Decimal(str(v)) for v in values]
    return tuple(b - a for a, b in zip(points, points[1:], strict=False))


@dataclass(frozen=True, slots=True)
class PowerLorenz:
    exponent: float = 2.0

    def __post_init__(self) -> None:
        if not isfinite(self.exponent) or self.exponent < 1:
            raise ValueError("Lorenz exponent must be finite and at least one")

    def __call__(self, percentile: float) -> float:
        return float(percentile**self.exponent)


def round_counts(targets: Sequence[Decimal], total: int, rng: Random) -> tuple[int, ...]:
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
        selected = rng.choice([i for i in candidates if residuals[i] == largest])
        counts[selected] += direction
        difference -= direction
    return tuple(counts)


def allocate_money(total: Decimal, shares: Sequence[Decimal], rng: Random) -> tuple[Decimal, ...]:
    """Allocate a cent-denominated total without losing money to rounding."""
    validate_money(total, field="total")
    cents = total * 100
    if cents != cents.to_integral_value():
        raise ValueError("total must be an exact number of cents")
    counts = round_counts([cents * share for share in shares], int(cents), rng)
    return tuple(Decimal(count) / 100 for count in counts)


def validate_shape(rows: int, columns: int) -> None:
    if any(type(v) is not int or v <= 0 for v in (rows, columns)):
        raise ValueError("grid dimensions must be positive integers")


def gaussian_price_field(
    rows: int,
    columns: int,
    *,
    reference_price: float,
    spread: float,
    length_scale: float,
    rng: Random,
) -> tuple[tuple[float, ...], ...]:
    """Apply separable Gaussian weights normalized to unit marginal variance.

    Runtime is O(rows * columns * (rows + columns)); no dense cell-pair matrix.
    """
    validate_shape(rows, columns)
    if not isfinite(reference_price) or reference_price <= 0:
        raise ValueError("reference_price must be finite and positive")
    if any(not isfinite(v) or v < 0 for v in (spread, length_scale)):
        raise ValueError("spread and length_scale must be finite and nonnegative")
    noise = [[rng.gauss(0, 1) for _ in range(columns)] for _ in range(rows)]

    def weights(size: int) -> list[list[float]]:
        result = []
        for i in range(size):
            distances = [(i - j) / length_scale for j in range(size)]
            row = [exp(-0.5 * distance * distance) for distance in distances]
            norm = sqrt(sum(v * v for v in row))
            result.append([v / norm for v in row])
        return result

    if length_scale:
        horizontal = weights(columns)
        vertical = weights(rows)
        smoothed = [
            [sum(w * v for w, v in zip(horizontal[b], row, strict=True)) for b in range(columns)]
            for row in noise
        ]
        noise = [
            [sum(vertical[a][u] * smoothed[u][b] for u in range(rows)) for b in range(columns)]
            for a in range(rows)
        ]
    try:
        prices = tuple(tuple(reference_price * exp(spread * v) for v in row) for row in noise)
    except OverflowError as exc:
        raise ValueError("price parameters overflow; reduce spread") from exc
    if any(not isfinite(v) or v <= 0 for row in prices for v in row):
        raise ValueError("price parameters produce non-finite or zero prices")
    return prices


def match_residences(
    incomes: Sequence[Decimal],
    prices: Sequence[float],
    *,
    noise: float,
    rng: Random,
) -> tuple[int, ...]:
    """Return person indices in home order; equal incomes share a midrank percentile.

    No affordability or ownership assumption is made. Inputs are not modified.
    """
    if len(incomes) != len(prices) or not incomes:
        raise ValueError("Matching requires equal positive counts of people and homes")
    if not isfinite(noise) or noise < 0:
        raise ValueError("Placement noise must be finite and nonnegative")
    for income in incomes:
        validate_money(income, field="income")
    if any(not isfinite(price) or price <= 0 for price in prices):
        raise ValueError("Placement prices must be finite and positive")
    frequencies = Counter(incomes)
    percentiles: dict[Decimal, float] = {}
    below = 0
    for value, count in sorted(frequencies.items()):
        percentiles[value] = (below + count / 2) / len(incomes)
        below += count
    people = sorted(
        range(len(incomes)),
        key=lambda i: (
            percentiles[incomes[i]] + noise * rng.gauss(0, 1),
            rng.random(),
        ),
    )
    homes = sorted(range(len(prices)), key=lambda j: (prices[j], rng.random()))
    residents = [0] * len(homes)
    for home, person in zip(homes, people, strict=True):
        residents[home] = person
    return tuple(residents)


def poisson_count(rate: float, rng: Random) -> int:
    """Count exponential arrivals in a unit period; avoids exp(-rate) underflow.

    Cost is linear in the expected event count, as is event application itself.
    """
    if not isfinite(rate) or rate < 0:
        raise ValueError("Poisson rate must be finite and nonnegative")
    if rate == 0:
        return 0
    count = 0
    arrival = rng.expovariate(1.0)
    while arrival <= rate:
        count += 1
        arrival += rng.expovariate(1.0)
    return count
