from collections.abc import Mapping
from dataclasses import dataclass, replace
from types import MappingProxyType

from agents.base import Action, Observation, PayRent, Wait
from agents.house import HouseAgent
from agents.insurance import InsurancePlanAgent
from domain.disasters import DisasterConfig, DisasterResult
from domain.grid import GridSnapshot, grid_snapshot
from domain.housing import HousingMarket
from domain.insurance import (
    Claim,
    Contract,
    CoverageChoice,
    InsuranceMarket,
    InsuranceObservation,
    Insurer,
    InsurerObservation,
    Offer,
)
from domain.models import Entity, Home, Household, Region
from utils.validation.collections import index_by_id


@dataclass(frozen=True, slots=True)
class Scenario:
    regions: tuple[Region, ...]
    people: tuple[Entity, ...]
    households: tuple[Household, ...]
    homes: tuple[Home, ...]
    grid_shape: tuple[int, int] | None = None
    seed: int = 0


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
    disasters: tuple[DisasterResult, ...] = ()
    claims: tuple[Claim, ...] = ()


class Environment:
    """One controller and budget per person; one person per household and residence."""

    def __init__(
        self,
        scenario: Scenario,
        agents: Mapping[int, HouseAgent],
        *,
        disasters: DisasterConfig | None = None,
        insurers: tuple[Insurer, ...] = (),
        insurer_agents: Mapping[int, InsurancePlanAgent[InsurerObservation, tuple[Offer, ...]]]
        | None = None,
    ) -> None:
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
        self._grid_shape = scenario.grid_shape
        self._seed = scenario.seed
        self._disasters = disasters
        if self._grid_shape is not None:
            grid_snapshot(self.homes.values(), self._grid_shape)
        if disasters is not None:
            if self._grid_shape is None:
                raise ValueError("Disasters require a grid scenario")
            if (
                disasters.footprint_rows > self._grid_shape[0]
                or disasters.footprint_columns > self._grid_shape[1]
            ):
                raise ValueError("Disaster footprint must fit within the grid")
        self._insurance = InsuranceMarket(insurers)
        self._insurer_agents = dict(insurer_agents or {})
        if self._insurer_agents.keys() != self._insurance.firms.keys():
            raise ValueError("Every insurer must have exactly one agent")
        if len({id(a) for a in self._insurer_agents.values()}) != len(self._insurer_agents):
            raise ValueError("Each insurer must have its own agent instance")

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

    @property
    def insurers(self) -> Mapping[int, Insurer]:
        return self._insurance.firms

    @property
    def contracts(self) -> tuple[Contract, ...]:
        return self._insurance.contracts

    @property
    def claims(self) -> tuple[Claim, ...]:
        return self._insurance.claims

    def grid_snapshot(self) -> GridSnapshot:
        if self._grid_shape is None:
            raise ValueError("This environment has no grid")
        return grid_snapshot(self.homes.values(), self._grid_shape)

    def open_insurance(
        self,
        choices: Mapping[int, tuple[CoverageChoice, ...]] | None = None,
    ) -> tuple[Contract, ...]:
        """Collect offers, then choices, and atomically activate optional coverage.

        Called at period zero before any exposure; premiums are paid up front.
        Controller-internal state is not rolled back if a policy fails.
        """
        if self.period != 0 or self._insurance.opened:
            raise ValueError("Insurance can only open once, before the first period")
        offers: list[Offer] = []
        for firm_id in sorted(self.insurers):
            observation = InsurerObservation(
                self.insurers[firm_id],
                tuple(self.people.values()),
                tuple(self.homes.values()),
                self.period,
            )
            quoted = self._insurer_agents[firm_id].decide(observation)
            if any(o.insurer_id != firm_id for o in quoted):
                raise ValueError("Insurer may only issue its own offers")
            offers.extend(quoted)
        index_by_id(offers)
        if choices is None:
            choices = {
                person_id: self._agents[person_id].choose_insurance(
                    InsuranceObservation(
                        self.people[person_id], tuple(self.homes.values()), tuple(offers)
                    )
                )
                for person_id in sorted(self.people)
            }
        market = self._market.copy()
        insurance = self._insurance.copy()
        insurance.open(market, offers, choices, starts_at=1)
        self._market = market
        self._insurance = insurance
        return insurance.contracts

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

    def step(
        self,
        actions: Mapping[int, Action] | None = None,
        *,
        disaster_rate: float | None = None,
    ) -> StepResult:
        """Credit income, settle rent, apply disasters, then pay covered claims.

        Rent settles by person ID and claims by contract ID. disaster_rate overrides
        the rate for this period only. Explicit actions cover every person and bypass
        controllers. Failure preserves economic state; controller internals cannot roll back.
        """
        if self.insurers and not self._insurance.opened:
            raise ValueError("Complete the opening insurance round before stepping")
        disaster_config = self._disasters
        if disaster_rate is not None:
            if disaster_config is None:
                raise ValueError("Configure a disaster footprint before overriding the rate")
            disaster_config = replace(disaster_config, rate=disaster_rate)
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
        disaster_results: list[DisasterResult] = []
        insurance = self._insurance.copy()
        claims: list[Claim] = []
        if disaster_config is not None and self._grid_shape is not None:
            for cells in disaster_config.footprints(
                self._grid_shape, seed=self._seed, period=period
            ):
                losses = market.destroy(cells)
                disaster_results.append(DisasterResult(cells, losses))
                claims.extend(insurance.settle(market, losses, period))
        observations = MappingProxyType(
            {person_id: self._observe(person_id, market, period) for person_id in person_ids}
        )
        self._market = market
        self._period = period
        self._insurance = insurance
        return StepResult(
            period=period,
            actions=tuple(outcomes),
            observations=observations,
            disasters=tuple(disaster_results),
            claims=tuple(claims),
        )
