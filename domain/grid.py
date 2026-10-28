"""Read-only matrix views derived from domain records, never a second source of state."""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from domain.models import Home
from utils.distributions import validate_shape


@dataclass(frozen=True, slots=True)
class GridSnapshot:
    home_ids: tuple[tuple[int, ...], ...]
    prices: tuple[tuple[Decimal, ...], ...]
    owners: tuple[tuple[int, ...], ...]
    residents: tuple[tuple[int, ...], ...]
    destroyed: tuple[tuple[bool, ...], ...]


def grid_snapshot(homes: Iterable[Home], shape: tuple[int, int]) -> GridSnapshot:
    rows, columns = shape
    validate_shape(rows, columns)
    indexed: dict[tuple[int, int], Home] = {}
    for home in homes:
        position = home.position
        if position is None or not (position[0] < rows and position[1] < columns):
            raise ValueError("Every grid home needs a position within the grid")
        if position in indexed:
            raise ValueError("Grid positions must be unique")
        indexed[position] = home
    if len(indexed) != rows * columns:
        raise ValueError("Every grid cell must contain one home")
    board = tuple(tuple(indexed[a, b] for b in range(columns)) for a in range(rows))
    return GridSnapshot(
        tuple(tuple(h.id for h in row) for row in board),
        tuple(tuple(h.market_value for h in row) for row in board),
        tuple(tuple(h.owner_id for h in row) for row in board),
        tuple(tuple(h.occupant_id or 0 for h in row) for row in board),
        tuple(tuple(h.destroyed for h in row) for row in board),
    )
