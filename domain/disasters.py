"""Poisson events whose zones are fixed rectangles or randomly sized squares.

Fixed rectangles sit entirely inside the grid, anchored at their upper-left cell.
Randomly sized squares are centered on the sampled cell and clipped at the grid edge.
"""

from dataclasses import dataclass
from math import isfinite

import numpy as np

from domain.models import Home
from utils.distributions import (
    FloatArray,
    TweedieRadius,
    anchor_probabilities,
    numpy_stream,
    sample_disasters,
    smooth_field,
    validate_shape,
)


@dataclass(frozen=True, slots=True)
class DisasterConfig:
    rate: float = 0.1  # Expected events per simulation period, not per year.
    footprint_rows: int = 1
    footprint_columns: int = 1
    risk_contrast: float = 0.0
    risk_length_scale: float = 2.0
    radius: TweedieRadius | None = None  # Draw each event's radius; replaces the footprint.

    def __post_init__(self) -> None:
        if not isfinite(self.rate) or self.rate < 0:
            raise ValueError("Disaster rate must be finite and nonnegative")
        validate_shape(self.footprint_rows, self.footprint_columns)
        if any(not isfinite(v) or v < 0 for v in (self.risk_contrast, self.risk_length_scale)):
            raise ValueError("risk parameters must be finite and nonnegative")
        if self.radius and (self.footprint_rows, self.footprint_columns) != (1, 1):
            raise ValueError("Randomly sized zones replace the fixed footprint")

    def risk_probabilities(self, shape: tuple[int, int], *, seed: int) -> FloatArray:
        """Build the episode's private risk field on an independent stream."""
        validate_shape(*shape)
        noise = numpy_stream(seed, "risk").normal(size=shape)
        with np.errstate(over="ignore", under="ignore", invalid="ignore"):
            weights = np.exp(self.risk_contrast * smooth_field(noise, self.risk_length_scale))
        probabilities = anchor_probabilities(weights, (self.footprint_rows, self.footprint_columns))
        probabilities.setflags(write=False)
        return probabilities

    def hit_probabilities(self, shape: tuple[int, int], *, seed: int) -> FloatArray:
        """Chance one event strikes each cell, counting every zone that could reach it."""
        anchors = self.risk_probabilities(shape, seed=seed)
        result = np.zeros(shape)
        if self.radius:
            reach = self.radius.reach(max(shape))
            rows, columns = np.ogrid[: shape[0], : shape[1]]
            for (row, column), probability in np.ndenumerate(anchors):
                distance = np.maximum(np.abs(rows - row), np.abs(columns - column))
                result += probability * reach[distance]
            return result
        for (row, column), probability in np.ndenumerate(anchors):
            result[
                row : row + self.footprint_rows, column : column + self.footprint_columns
            ] += probability
        return result

    def footprints(
        self,
        shape: tuple[int, int],
        *,
        seed: int,
        period: int,
        probabilities: FloatArray | None = None,
    ) -> tuple[tuple[tuple[int, int], ...], ...]:
        rows, columns = shape
        validate_shape(rows, columns)
        if self.footprint_rows > rows or self.footprint_columns > columns:
            raise ValueError("Disaster footprint must fit within the grid")
        if probabilities is None:
            probabilities = self.risk_probabilities(shape, seed=seed)
        expected = (rows - self.footprint_rows + 1, columns - self.footprint_columns + 1)
        if probabilities.shape != expected:
            raise ValueError("Probability shape must match eligible anchors")
        anchors = sample_disasters(
            self.rate,
            probabilities,
            numpy_stream(seed, f"disaster-counts:{period}"),
            location_rng=numpy_stream(seed, f"disaster-locations:{period}"),
        )
        if self.radius:
            radii = self.radius.sample(len(anchors), numpy_stream(seed, f"disaster-sizes:{period}"))
            return tuple(
                tuple(
                    (a, b)
                    for a in range(max(0, int(row) - int(r)), min(rows, int(row) + int(r) + 1))
                    for b in range(
                        max(0, int(column) - int(r)), min(columns, int(column) + int(r) + 1)
                    )
                )
                for (row, column), r in zip(anchors, radii, strict=True)
            )
        events = []
        for row, column in anchors:
            top, left = int(row), int(column)
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
