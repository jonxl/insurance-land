from collections.abc import Iterable
from typing import Protocol


class Identified(Protocol):
    @property
    def id(self) -> int: ...


def index_by_id[T: Identified](items: Iterable[T]) -> dict[int, T]:
    indexed: dict[int, T] = {}
    for item in items:
        if item.id in indexed:
            raise ValueError(f"Duplicate {type(item).__name__} ID {item.id}")
        indexed[item.id] = item
    return indexed
