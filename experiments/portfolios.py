"""Map whole existing ownership portfolios to insurers without moving home titles."""

from collections.abc import Callable, Sequence
from decimal import Decimal

from domain.models import Home
from utils.distributions import allocate_counts, lorenz_shares, numpy_stream


def insurer_portfolios(
    homes: Sequence[Home], firm_ids: Sequence[int], curve: Callable[[float], float], seed: int
) -> dict[int, int]:
    if not firm_ids or len(set(firm_ids)) != len(firm_ids):
        raise ValueError("Insurers must be nonempty and unique")
    values: dict[int, Decimal] = {}
    for home in homes:
        values[home.owner_id] = values.get(home.owner_id, Decimal(0)) + home.market_value
    rng = numpy_stream(seed, "insurance-portfolios")
    owners = sorted(sorted(values), key=lambda owner: (values[owner], rng.random()))
    # Reserve one whole owner portfolio per firm when the world has enough owners.
    minimum = int(len(owners) >= len(firm_ids))
    counts = (
        allocate_counts(
            lorenz_shares(curve, len(firm_ids)), len(owners) - minimum * len(firm_ids), rng
        )
        + minimum
    )
    ordering = rng.permutation(sorted(firm_ids))
    assignment = {}
    offset = 0
    for firm, count in zip(ordering, counts, strict=True):
        for owner in owners[offset : offset + int(count)]:
            assignment[owner] = int(firm)
        offset += int(count)
    return {home.id: assignment[home.owner_id] for home in homes}
