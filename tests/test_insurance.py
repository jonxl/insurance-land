from decimal import Decimal

import pytest

from agents.house import HouseAgent
from agents.insurance import InsurancePlanAgent
from agents.policies import cheapest_affordable_coverage
from domain.disasters import DisasterConfig
from domain.insurance import CoverageChoice, Insurer, InsurerObservation, Offer, Product
from environment import Environment
from factories import EnvironmentFactory, GridPopulationConfig


def quote(observation: InsurerObservation) -> tuple[Offer, ...]:
    return tuple(
        Offer(
            id=index,
            insurer_id=observation.firm.id,
            product=product,
            premium=Decimal("10"),
            limit=Decimal("1000"),
            deductible=Decimal("5"),
            term_periods=2,
            contents_value=Decimal("50") if product == Product.RENTERS else Decimal(0),
        )
        for index, product in enumerate(Product, 1)
    )


def insured_environment(capital: str = "1000") -> Environment:
    return EnvironmentFactory.create(
        GridPopulationConfig(
            rows=1,
            columns=2,
            reference_price=Decimal("100"),
            price_spread=0,
            mean_annual_income=Decimal(0),
            initial_cash=Decimal("100"),
            rent_per_period=Decimal(0),
            seed=1,
        ),
        agent_factory=lambda _: HouseAgent(insurance_policy=cheapest_affordable_coverage),
        disasters=DisasterConfig(rate=20, footprint_rows=1, footprint_columns=2),
        insurers=(Insurer(1, "A", Decimal(capital)),),
        insurer_agents={1: InsurancePlanAgent(quote)},
    )


def test_opening_and_claims_conserve_cash_and_use_pre_loss_values() -> None:
    env = insured_environment()
    with pytest.raises(ValueError, match="opening"):
        env.step()
    total_before = sum(p.cash for p in env.people.values()) + env.insurers[1].capital
    contracts = env.open_insurance()
    assert len(contracts) == 3  # One renter, landlord, and owner-occupier interest.
    assert {c.offer.product for c in contracts} == set(Product)
    assert env.insurers[1].capital == Decimal("1030")
    assert sum(p.cash for p in env.people.values()) == Decimal("170")
    result = env.step()
    assert len(result.claims) == 3
    assert sorted(c.due for c in result.claims) == [Decimal(45), Decimal(95), Decimal(95)]
    assert all(c.paid == c.due for c in result.claims)
    assert sum(p.cash for p in env.people.values()) + env.insurers[1].capital == total_before
    assert all(h.market_value == 0 for h in env.homes.values())
    assert not env.step().claims
    with pytest.raises(ValueError, match="once"):
        env.open_insurance()


def test_shortfall_is_recorded_without_negative_capital() -> None:
    env = insured_environment("0")
    env.open_insurance()
    result = env.step()
    assert sum(c.paid for c in result.claims) == 30
    assert sum(c.due for c in result.claims) == 235
    assert env.insurers[1].capital == 0


def test_expired_contracts_do_not_pay() -> None:
    env = insured_environment()
    env.open_insurance()
    env.step(disaster_rate=0)
    env.step(disaster_rate=0)
    assert not env.step().claims


def test_invalid_opening_rolls_back_all_purchases() -> None:
    env = insured_environment()
    before = dict(env.people)
    # First purchase is valid; the second uses a nonexistent home.
    renter_home = next(h for h in env.homes.values() if h.occupant_id != h.owner_id)
    assert renter_home.occupant_id is not None
    choices: dict[int, tuple[CoverageChoice, ...]] = {person: () for person in env.people}
    choices[renter_home.occupant_id] = (
        CoverageChoice(3, renter_home.id),
        CoverageChoice(1, 999),
    )
    with pytest.raises(ValueError, match="Unknown"):
        env.open_insurance(choices)
    assert dict(env.people) == before
    assert env.insurers[1].capital == 1000
    assert not env.contracts
    assert len(env.open_insurance()) == 3


def test_wrong_interest_and_duplicate_coverage_rejected() -> None:
    for duplicate in (False, True):
        env = insured_environment()
        home = next(h for h in env.homes.values() if h.occupant_id != h.owner_id)
        assert home.occupant_id is not None
        choices: dict[int, tuple[CoverageChoice, ...]] = {person: () for person in env.people}
        choices[home.occupant_id] = (
            (CoverageChoice(3, home.id), CoverageChoice(3, home.id))
            if duplicate
            else (CoverageChoice(1, home.id),)
        )
        with pytest.raises(ValueError, match="Duplicate|eligible"):
            env.open_insurance(choices)
        assert not env.contracts


def test_unaffordable_selection_is_rejected_atomically() -> None:
    def expensive(obs: InsurerObservation) -> tuple[Offer, ...]:
        return (Offer(1, obs.firm.id, Product.HOMEOWNERS, Decimal("1000"), Decimal("100")),)

    env = EnvironmentFactory.create(
        GridPopulationConfig(rows=1, columns=1, initial_cash=Decimal("1")),
        insurers=(Insurer(1, "A", Decimal(0)),),
        insurer_agents={1: InsurancePlanAgent(expensive)},
    )
    with pytest.raises(ValueError):
        env.open_insurance({1: (CoverageChoice(1, 1),)})
    assert env.people[1].cash == 1
    assert env.insurers[1].capital == 0


def test_claim_failure_rolls_back_disasters_and_can_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    from collections.abc import Sequence

    from domain.housing import HousingMarket
    from domain.insurance import Claim, InsuranceMarket
    from domain.models import Home

    first = insured_environment()
    second = insured_environment()
    first.open_insurance()
    second.open_insurance()
    before = first.grid_snapshot()
    original = InsuranceMarket.settle

    def fail(
        self: InsuranceMarket,
        market: HousingMarket,
        losses: Sequence[Home],
        period: int,
    ) -> tuple[Claim, ...]:
        original(self, market, losses, period)
        raise RuntimeError("Settlement failed after working-copy changes")

    with monkeypatch.context() as patch:
        patch.setattr(InsuranceMarket, "settle", fail)
        with pytest.raises(RuntimeError):
            first.step()
    assert first.period == 0
    assert first.grid_snapshot() == before
    assert not first.claims
    assert dict(first.people) == dict(second.people)
    assert dict(first.insurers) == dict(second.insurers)
    assert first.step() == second.step()


def test_quote_cannot_impersonate_another_insurer() -> None:
    env = EnvironmentFactory.create(
        GridPopulationConfig(rows=1, columns=1),
        insurers=(Insurer(1, "A", Decimal(0)),),
        insurer_agents={
            1: InsurancePlanAgent(
                lambda _: (Offer(1, 2, Product.HOMEOWNERS, Decimal(1), Decimal(10)),)
            )
        },
    )
    with pytest.raises(ValueError, match="own offers"):
        env.open_insurance()
    assert not env.contracts
