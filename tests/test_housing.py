from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from domain.housing import HousingMarket
from domain.models import Entity, Home


@pytest.fixture
def market() -> HousingMarket:
    market = HousingMarket()
    for entity_id in range(1, 4):
        market.add_entity(Entity(id=entity_id, cash=Decimal("1000")))
    market.add_home(Home(id=1, region_id=1, owner_id=1, market_value=Decimal("500000")))
    market.add_home(Home(id=2, region_id=1, owner_id=1, market_value=Decimal("200000")))
    return market


def test_ownership_and_residence_are_independent(market: HousingMarket) -> None:
    market.move_in(1, 1, rent=Decimal("0"))
    market.move_in(2, 2, rent=Decimal("100"))

    assert len(market.owned_homes(1)) == 2
    assert market.owned_homes(2) == ()
    assert market.residence(1) == market.homes[1]
    assert market.residence(2) == market.homes[2]
    assert market.residence(3) is None


def test_rent_moves_cash_to_owner_and_conserves_total(market: HousingMarket) -> None:
    market.move_in(2, 2, rent=Decimal("100.25"))
    total_before = sum(entity.cash for entity in market.entities.values())

    assert market.pay_rent(2)
    assert market.entities[2].cash == Decimal("899.75")
    assert market.entities[1].cash == Decimal("1100.25")
    assert sum(entity.cash for entity in market.entities.values()) == total_before


def test_unaffordable_rent_preserves_balances_and_residence(market: HousingMarket) -> None:
    market.move_in(2, 2, rent=Decimal("1001"))
    before = dict(market.entities)

    assert not market.pay_rent(2)
    assert market.entities == before
    assert market.residence(2) == market.homes[2]


def test_transfer_keeps_occupancy_and_redirects_rent(market: HousingMarket) -> None:
    market.move_in(2, 2, rent=Decimal("100"))
    market.transfer_ownership(2, 3, rent=Decimal("100"))

    assert market.residence(2) == market.homes[2]
    assert market.owned_homes(3) == (market.homes[2],)
    assert market.pay_rent(2)
    assert market.entities[3].cash == Decimal("1100")
    assert market.entities[1].cash == Decimal("1000")


def test_tenant_can_become_owner_without_moving(market: HousingMarket) -> None:
    market.move_in(2, 2, rent=Decimal("100"))
    market.transfer_ownership(2, 2, rent=Decimal("0"))
    before = dict(market.entities)

    assert market.pay_rent(2)
    assert market.entities == before
    assert market.homes[2].owner_id == market.homes[2].occupant_id == 2


def test_move_clears_previous_occupancy_but_preserves_owner(market: HousingMarket) -> None:
    market.move_in(1, 2, rent=Decimal("100"))
    market.move_in(2, 2, rent=Decimal("200"))

    assert market.homes[1].occupant_id is None
    assert market.homes[1].rent == 0
    assert market.homes[1].owner_id == 1
    assert market.residence(2) == market.homes[2]


def test_failed_move_leaves_existing_residence_intact(market: HousingMarket) -> None:
    market.move_in(1, 2, rent=Decimal("100"))
    before = dict(market.homes)

    with pytest.raises(ValueError, match="nonnegative"):
        market.move_in(2, 2, rent=Decimal("-1"))
    assert market.homes == before

    market.move_in(2, 3, rent=Decimal("100"))
    with pytest.raises(ValueError, match="already occupied"):
        market.move_in(2, 2, rent=Decimal("100"))
    assert market.residence(2) == market.homes[1]


def test_unknown_owner_cannot_receive_title(market: HousingMarket) -> None:
    before = dict(market.homes)
    with pytest.raises(ValueError, match="Unknown owner"):
        market.transfer_ownership(1, 99, rent=Decimal("0"))
    assert market.homes == before


def test_home_registration_enforces_relationships(market: HousingMarket) -> None:
    with pytest.raises(ValueError, match="Unknown owner"):
        market.add_home(Home(id=3, region_id=1, owner_id=99, market_value=Decimal("1")))
    with pytest.raises(ValueError, match="Unknown occupant"):
        market.add_home(
            Home(id=3, region_id=1, owner_id=1, market_value=Decimal("1"), occupant_id=99)
        )
    market.move_in(1, 2, rent=Decimal("100"))
    with pytest.raises(ValueError, match="at most one home"):
        market.add_home(
            Home(id=3, region_id=1, owner_id=1, market_value=Decimal("1"), occupant_id=2)
        )
    assert len(market.homes) == 2


def test_duplicate_ids_cannot_overwrite_state(market: HousingMarket) -> None:
    with pytest.raises(ValueError, match="already exists"):
        market.add_entity(Entity(id=1))
    with pytest.raises(ValueError, match="already exists"):
        market.add_home(Home(id=1, region_id=9, owner_id=2, market_value=Decimal("1")))
    assert market.entities[1].cash == Decimal("1000")
    assert market.homes[1].owner_id == 1


def test_vacancy_and_owner_occupancy_do_not_charge_rent(market: HousingMarket) -> None:
    market.move_in(1, 1, rent=Decimal("0"))
    before = dict(market.entities)
    assert market.pay_rent(1)
    assert market.pay_rent(2)
    assert market.entities == before
    market.vacate(1)
    assert market.residence(1) is None
    assert market.homes[1].owner_id == 1


def test_public_state_cannot_be_mutated(market: HousingMarket) -> None:
    with pytest.raises(FrozenInstanceError):
        market.homes[1].owner_id = 99  # type: ignore[misc]
    with pytest.raises(TypeError):
        market.homes[1] = market.homes[2]  # type: ignore[index]


@pytest.mark.parametrize("value", ["-1", "NaN", "Infinity", "-Infinity"])
def test_invalid_money_is_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="finite and nonnegative"):
        Entity(id=1, cash=Decimal(value))


def test_float_money_is_rejected() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        Entity(id=1, cash=0.1)  # type: ignore[arg-type]


@pytest.mark.parametrize("occupant_id", [None, 1])
def test_only_tenants_can_be_charged_rent(occupant_id: int | None) -> None:
    with pytest.raises(ValueError, match="cannot charge rent"):
        Home(
            id=1,
            region_id=1,
            owner_id=1,
            market_value=Decimal("1"),
            occupant_id=occupant_id,
            rent=Decimal("100"),
        )
