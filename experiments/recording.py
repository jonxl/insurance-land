"""Observation-only recording of baseline simulation state and actual cash transfers."""

import json
from pathlib import Path
from typing import Any

from agents.base import PayRent
from environment import Environment, StepResult


class WorldRecorder:
    """Start immediately after opening insurance; step through this recorder thereafter.

    Money is serialized as decimal strings. Period zero includes opening premiums;
    later snapshots represent end-of-period state. Rent uses pre-step tenancy, so
    destruction later in the same period cannot erase its payment record.
    """

    def __init__(self, world: Environment) -> None:
        if world.period != 0:
            raise ValueError("Recording must start at period zero")
        self.world = world
        self.frames: list[dict[str, Any]] = []
        premiums = [
            dict(
                kind="premium",
                person=c.person_id,
                firm=c.offer.insurer_id,
                home=c.home_id,
                amount=str(c.offer.premium),
                contract=c.id,
            )
            for c in world.contracts
        ]
        self._capture(premiums, None)

    def step(self, *, disaster_rate: float | None = None) -> StepResult:
        before = dict(self.world.homes)
        result = self.world.step(disaster_rate=disaster_rate)
        transfers: list[dict[str, Any]] = [
            dict(kind="income", person=p.id, amount=str(p.income))
            for p in self.world.people.values()
        ]
        for outcome in result.actions:
            if isinstance(outcome.action, PayRent):
                home = before[outcome.action.home_id]
                if home.occupant_id != home.owner_id and home.rent:
                    transfers.append(
                        dict(
                            kind="rent",
                            person=outcome.person_id,
                            recipient=home.owner_id,
                            home=home.id,
                            amount=str(home.rent if outcome.paid else 0),
                            requested=str(home.rent),
                            paid=outcome.paid,
                        )
                    )
        contracts = {c.id: c for c in self.world.contracts}
        for claim in result.claims:
            contract = contracts[claim.contract_id]
            transfers.append(
                dict(
                    kind="claim",
                    person=contract.person_id,
                    firm=contract.offer.insurer_id,
                    home=claim.home_id,
                    contract=contract.id,
                    amount=str(claim.paid),
                    due=str(claim.due),
                    shortfall=str(claim.due - claim.paid),
                )
            )
        self._capture(transfers, result)
        return result

    def _capture(self, transfers: list[dict[str, Any]], result: StepResult | None) -> None:
        world = self.world
        self.frames.append(
            dict(
                period=world.period,
                people=[
                    dict(
                        id=p.id,
                        cash=str(p.cash),
                        income=str(p.income),
                        annual_income=str(p.annual_income or 0),
                    )
                    for p in world.people.values()
                ],
                homes=[
                    dict(
                        id=h.id,
                        owner=h.owner_id,
                        resident=h.occupant_id,
                        value=str(h.market_value),
                        rent=str(h.rent),
                        destroyed=h.destroyed,
                        position=h.position,
                    )
                    for h in world.homes.values()
                ],
                firms=[
                    dict(id=f.id, name=f.name, capital=str(f.capital))
                    for f in world.insurers.values()
                ],
                transfers=transfers,
                events=[]
                if result is None
                else [
                    dict(
                        id=i + 1,
                        cells=e.cells,
                        losses=[h.id for h in e.losses],
                        displaced=e.displaced_people,
                    )
                    for i, e in enumerate(result.disasters)
                ],
            )
        )

    def data(self) -> dict[str, Any]:
        contracts = [
            dict(
                id=c.id,
                person=c.person_id,
                firm=c.offer.insurer_id,
                home=c.home_id,
                product=str(c.offer.product),
                starts=c.starts_at,
                ends=c.ends_at,
            )
            for c in self.world.contracts
        ]
        return dict(
            frames=self.frames,
            contracts=contracts,
            timing="Period 0 is after opening premiums; other periods are end-of-period. "
            "Income and rent settle each period. Fixed baseline policies; "
            "no rebuilding or public-history delivery to agents.",
        )

    def export(self, output: Path) -> None:
        serialized = json.dumps(self.data(), separators=(",", ":"))
        (output / "assets").mkdir(parents=True, exist_ok=True)
        (output / "assets" / "world-history.json").write_text(serialized + "\n")
        template = Path(__file__).with_name("diagnostics.html").read_text()
        (output / "diagnostics.html").write_text(
            template.replace("__WORLD_DATA__", serialized.replace("<", "\\u003c"))
        )
