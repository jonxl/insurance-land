"""Poisson events with a fixed rectangular footprint fully contained in the grid."""

from dataclasses import dataclass
from math import isfinite

from domain.models import Home
from utils.distributions import poisson_count, random_stream, validate_shape


@dataclass(frozen=True, slots=True)
class DisasterConfig:
    rate: float = 0.1  # Expected events per simulation period, not per year.
    footprint_rows: int = 1
    footprint_columns: int = 1

    def __post_init__(self) -> None:
        if not isfinite(self.rate) or self.rate < 0:
            raise ValueError("Disaster rate must be finite and nonnegative")
        validate_shape(self.footprint_rows, self.footprint_columns)

    def footprints(
        self,
        shape: tuple[int, int],
        *,
        seed: int,
        period: int,
    ) -> tuple[tuple[tuple[int, int], ...], ...]:
        rows, columns = shape
        validate_shape(rows, columns)
        if self.footprint_rows > rows or self.footprint_columns > columns:
            raise ValueError("Disaster footprint must fit within the grid")
        rng = random_stream(seed, f"disasters:{period}")
        events = []
        for _ in range(poisson_count(self.rate, rng)):
            top = rng.randrange(rows - self.footprint_rows + 1)
            left = rng.randrange(columns - self.footprint_columns + 1)
            events.append(
                tuple(
                    (a, b)
                    for a in range(top, top + self.footprint_rows)
                    for b in range(left, left + self.footprint_columns)
                )
            )
        return tuple(events)


@dataclass(frozen=True, slots=True)
class DisasterResult:
    cells: tuple[tuple[int, int], ...]
    losses: tuple[Home, ...]  # Immutable pre-loss records, including owner and resident.

    @property
    def displaced_people(self) -> tuple[int, ...]:
        return tuple(h.occupant_id for h in self.losses if h.occupant_id is not None)
