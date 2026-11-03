"""Read-only views by region, derived from domain records, never a second source of state."""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import TypeVar

from domain.models import Home
from utils.distributions import validate_shape

T = TypeVar("T")
# Row, then column, then the homes of that region in home-ID order.
RegionMatrix = tuple[tuple[tuple[T, ...], ...], ...]


@dataclass(frozen=True, slots=True)
class GridSnapshot:
    home_ids: RegionMatrix[int]
    prices: RegionMatrix[Decimal]
    owners: RegionMatrix[int]
    residents: RegionMatrix[int]
    destroyed: RegionMatrix[bool]


def grid_snapshot(homes: Iterable[Home], shape: tuple[int, int]) -> GridSnapshot:
    rows, columns = shape
    validate_shape(rows, columns)
    regions: dict[tuple[int, int], list[Home]] = {}
    for home in homes:
        position = home.position
        if position is None or not (position[0] < rows and position[1] < columns):
            raise ValueError("Every grid home needs a position within the grid")
        regions.setdefault(position, []).append(home)
    if len(regions) != rows * columns:
        raise ValueError("Every region must contain at least one home")
    board = tuple(tuple(tuple(regions[a, b]) for b in range(columns)) for a in range(rows))

    def view(read):
        return tuple(tuple(tuple(read(h) for h in region) for region in row) for row in board)

    return GridSnapshot(
        view(lambda h: h.id),
        view(lambda h: h.market_value),
        view(lambda h: h.owner_id),
        view(lambda h: h.occupant_id or 0),
        view(lambda h: h.destroyed),
    )
