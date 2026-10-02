from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from src.agents.base import Action, Observation, PayRent, Wait
from src.agents.house import HouseAgent
from src.domain.housing import HousingMarket
from src.domain.models import Entity, Home, Household, Region
from src.utils.validation.collections import index_by_id


@dataclass(frozen=True, slots=True)
class Scenario:
    regions: tuple[Region, ...]
    people: tuple[Entity, ...]
    households: tuple[Household, ...]
    homes: tuple[Home, ...]


@dataclass(frozen=True, slots=True)
class ActionResult:
    person_id: int
    action: Action
    paid: bool | None


@dataclass(frozen=True, slots=True)
class StepResult:
    period: int
    actions: tuple[ActionResult, ...]
    observations: Mapping[int, Observation]


class Environment:
    """One controller and budget per person; one person per household and residence."""

    def __init__(self, scenario: Scenario, agents: Mapping[int, HouseAgent]) -> None:
        self._regions = index_by_id(scenario.regions)
        self._households = index_by_id(scenario.households)
        people = index_by_id(scenario.people)
        households_by_person: dict[int, Household] = {}
        for household in self._households.values():
            if household.person_id not in people:
                raise ValueError(f"Unknown household member {household.person_id}")
            if household.person_id in households_by_person:
                raise ValueError("A person must belong to exactly one household")
            households_by_person[household.person_id] = household
        if households_by_person.keys() != people.keys():
            raise ValueError("Every person must have a household")
        if agents.keys() != people.keys():
            raise ValueError("Every person must have exactly one agent")
        if len({id(agent) for agent in agents.values()}) != len(agents):
            raise ValueError("Each person must have their own agent instance")
        self._households_by_person = households_by_person
        self._agents = dict(agents)
        self._market = HousingMarket()
        for person in people.values():
            self._market.add_entity(person)
        for home in scenario.homes:
            if home.region_id not in self._regions:
                raise ValueError(f"Unknown region {home.region_id}")
            self._market.add_home(home)
        self._period = 0

    @property
    def period(self) -> int:
        return self._period

    @property
    def people(self) -> Mapping[int, Entity]:
        return self._market.entities

    @property
    def homes(self) -> Mapping[int, Home]:
        return self._market.homes

    @property
    def households(self) -> Mapping[int, Household]:
        return MappingProxyType(self._households)

    @property
    def regions(self) -> Mapping[int, Region]:
        return MappingProxyType(self._regions)

    @property
    def agents(self) -> Mapping[int, HouseAgent]:
        return MappingProxyType(self._agents)

    def observe(self, person_id: int) -> Observation:
        return self._observe(person_id, self._market, self._period)

    def _observe(self, person_id: int, market: HousingMarket, period: int) -> Observation:
        residence = market.residence(person_id)
        return Observation(
            period=period,
            person=market.entities[person_id],
            household=self._households_by_person[person_id],
            residence=residence,
            region=self._regions[residence.region_id] if residence is not None else None,
            owned_homes=market.owned_homes(person_id),
        )

    def homes_in_region(self, region_id: int) -> tuple[Home, ...]:
        if region_id not in self._regions:
            raise ValueError(f"Unknown region {region_id}")
        return tuple(home for home in self.homes.values() if home.region_id == region_id)

    def households_in_region(self, region_id: int) -> tuple[Household, ...]:
        return tuple(
            self._households_by_person[home.occupant_id]
            for home in self.homes_in_region(region_id)
            if home.occupant_id is not None
        )

    def step(self, actions: Mapping[int, Action] | None = None) -> StepResult:
        """Accrue income, collect decisions, then settle in ascending person ID order.

        Explicit actions must cover every person and bypass controllers. Invalid actions
        leave economic state unchanged; controller-internal state cannot be rolled back.
        """
        if actions is not None and actions.keys() != self.people.keys():
            raise ValueError("Actions must cover every person exactly once")
        market = self._market.copy()
        market.accrue_income()
        period = self._period + 1
        person_ids = sorted(self.people)
        decisions = (
            dict(actions)
            if actions is not None
            else {
                person_id: self._agents[person_id].decide(self._observe(person_id, market, period))
                for person_id in person_ids
            }
        )
        for person_id, action in decisions.items():
            if isinstance(action, PayRent):
                home = market.homes.get(action.home_id)
                if home is None or home.occupant_id != person_id:
                    raise ValueError("A person can only pay rent for their own residence")
            elif not isinstance(action, Wait):
                raise TypeError(f"Unsupported action for person {person_id}")
        outcomes: list[ActionResult] = []
        for person_id in person_ids:
            action = decisions[person_id]
            paid = market.pay_rent(action.home_id) if isinstance(action, PayRent) else None
            outcomes.append(ActionResult(person_id=person_id, action=action, paid=paid))
        observations = MappingProxyType(
            {person_id: self._observe(person_id, market, period) for person_id in person_ids}
        )
        self._market = market
        self._period = period
        return StepResult(period=period, actions=tuple(outcomes), observations=observations)
