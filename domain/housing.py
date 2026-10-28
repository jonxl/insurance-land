from collections.abc import Iterable, Mapping
from dataclasses import replace
from decimal import Decimal
from types import MappingProxyType

from domain.models import Entity, Home


class HousingMarket:
    """Own state changes; derive ownership and residence from homes."""

    def __init__(self) -> None:
        self._entities: dict[int, Entity] = {}
        self._homes: dict[int, Home] = {}

    @property
    def entities(self) -> Mapping[int, Entity]:
        return MappingProxyType(self._entities)

    @property
    def homes(self) -> Mapping[int, Home]:
        return MappingProxyType(self._homes)

    def copy(self) -> HousingMarket:
        market = HousingMarket()
        market._entities = self._entities.copy()
        market._homes = self._homes.copy()
        return market

    def accrue_income(self) -> None:
        updated = {
            entity_id: replace(entity, cash=entity.cash + entity.income)
            for entity_id, entity in self._entities.items()
        }
        self._entities.update(updated)

    def add_entity(self, entity: Entity) -> None:
        if entity.id in self._entities:
            raise ValueError(f"Entity {entity.id} already exists")
        self._entities[entity.id] = entity

    def add_home(self, home: Home) -> None:
        if home.id in self._homes:
            raise ValueError(f"Home {home.id} already exists")
        if home.owner_id not in self._entities:
            raise ValueError(f"Unknown owner {home.owner_id}")
        if home.occupant_id is not None:
            if home.occupant_id not in self._entities:
                raise ValueError(f"Unknown occupant {home.occupant_id}")
            if self.residence(home.occupant_id) is not None:
                raise ValueError("An entity can occupy at most one home")
        self._homes[home.id] = home

    def owned_homes(self, entity_id: int) -> tuple[Home, ...]:
        if entity_id not in self._entities:
            raise ValueError(f"Unknown entity {entity_id}")
        return tuple(home for home in self._homes.values() if home.owner_id == entity_id)

    def residence(self, entity_id: int) -> Home | None:
        if entity_id not in self._entities:
            raise ValueError(f"Unknown entity {entity_id}")
        return next(
            (home for home in self._homes.values() if home.occupant_id == entity_id),
            None,
        )

    def move_in(self, home_id: int, entity_id: int, *, rent: Decimal) -> None:
        """Set rent per payment call and move out of any previous residence."""
        home = self._homes[home_id]
        if home.destroyed:
            raise ValueError("Cannot occupy a destroyed home")
        previous = self.residence(entity_id)
        if home.occupant_id is not None:
            raise ValueError(f"Home {home_id} is already occupied")
        occupied = replace(home, occupant_id=entity_id, rent=rent)
        if previous is not None:
            self._homes[previous.id] = replace(previous, occupant_id=None, rent=Decimal("0"))
        self._homes[home_id] = occupied

    def vacate(self, home_id: int) -> None:
        home = self._homes[home_id]
        self._homes[home_id] = replace(home, occupant_id=None, rent=Decimal("0"))

    def transfer_ownership(self, home_id: int, new_owner_id: int, *, rent: Decimal) -> None:
        """Transfer title without moving the occupant or settling a sale or debt."""
        home = self._homes[home_id]
        if new_owner_id not in self._entities:
            raise ValueError(f"Unknown owner {new_owner_id}")
        self._homes[home_id] = replace(home, owner_id=new_owner_id, rent=rent)

    def pay_rent(self, home_id: int) -> bool:
        """Settle one payment; return False on insufficient funds without changing state."""
        home = self._homes[home_id]
        if home.occupant_id is None or home.occupant_id == home.owner_id or home.rent == 0:
            return True
        tenant = self._entities[home.occupant_id]
        owner = self._entities[home.owner_id]
        if tenant.cash < home.rent:
            return False
        paid_tenant = replace(tenant, cash=tenant.cash - home.rent)
        paid_owner = replace(owner, cash=owner.cash + home.rent)
        self._entities[tenant.id] = paid_tenant
        self._entities[owner.id] = paid_owner
        return True

    def destroy(self, cells: Iterable[tuple[int, int]]) -> tuple[Home, ...]:
        """Destroy intact homes once; retain titles and return pre-loss snapshots."""
        affected = set(cells)
        losses = tuple(
            h for h in self._homes.values() if h.position in affected and not h.destroyed
        )
        for home in losses:
            self._homes[home.id] = replace(
                home, market_value=Decimal(0), occupant_id=None, rent=Decimal(0), destroyed=True
            )
        return losses

    def adjust_cash(self, person_id: int, amount: Decimal) -> None:
        """Apply an external cash flow, rejecting insufficient funds via Entity validation."""
        person = self._entities[person_id]
        self._entities[person_id] = replace(person, cash=person.cash + amount)
