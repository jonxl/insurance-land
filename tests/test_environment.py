from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal
from typing import Any, cast

import pytest

from agents.base import Action, Observation, PayRent, Wait
from agents.house import HouseAgent
from domain.models import Entity, Home, Household, Region
from environment import Environment, Scenario
from factories import EnvironmentFactory


@pytest.fixture
def scenario() -> Scenario:
    return Scenario(
        regions=(Region(1, "Coast"), Region(2, "Inland")),
        people=(
            Entity(10, cash=Decimal("1000"), income=Decimal("10")),
            Entity(20, cash=Decimal("50"), income=Decimal("60")),
            Entity(30, cash=Decimal("100")),
        ),
        households=(Household(100, 10), Household(200, 20), Household(300, 30)),
        homes=(
            Home(1, region_id=1, owner_id=10, market_value=Decimal("1000"), occupant_id=10),
            Home(
                2,
                region_id=1,
                owner_id=10,
                market_value=Decimal("1000"),
                occupant_id=20,
                rent=Decimal("100"),
            ),
            Home(3, region_id=2, owner_id=20, market_value=Decimal("1000")),
        ),
    )


def test_environment_connects_people_households_homes_and_regions(scenario: Scenario) -> None:
    environment = EnvironmentFactory.from_scenario(scenario)

    person = environment.observe(20)
    assert person.person == scenario.people[1]
    assert person.household == Household(200, 20)
    assert person.residence == scenario.homes[1]
    assert person.region == scenario.regions[0]
    assert person.owned_homes == (scenario.homes[2],)
    assert environment.households_in_region(1) == scenario.households[:2]
    assert environment.households_in_region(2) == ()
    assert environment.homes_in_region(2) == (scenario.homes[2],)
    assert environment.observe(30).residence is None
    assert environment.observe(30).region is None
    assert len({id(agent) for agent in environment.agents.values()}) == 3
    with pytest.raises(ValueError, match="Unknown region"):
        environment.homes_in_region(99)


def test_step_credits_income_once_and_settles_rent(scenario: Scenario) -> None:
    environment = EnvironmentFactory.from_scenario(scenario)
    before = environment.observe(20)

    result = environment.step()

    assert result.period == environment.period == 1
    assert environment.people[10].cash == Decimal("1110")
    assert environment.people[20].cash == Decimal("10")
    assert environment.people[30].cash == Decimal("100")
    assert [outcome.paid for outcome in result.actions] == [None, True, None]
    assert before.person.cash == Decimal("50")
    assert result.observations[20].person.cash == Decimal("10")

    second = environment.step()
    assert second.period == 2
    assert second.actions[1].paid is False
    assert environment.people[20].cash == Decimal("70")
    assert environment.homes[2].occupant_id == 20
    assert result.observations[20].person.cash == Decimal("10")


class RecordingAgent(HouseAgent):
    def __init__(self) -> None:
        self.observations: list[Observation] = []

    def decide(self, observation: Observation) -> Action:
        self.observations.append(observation)
        return self.pay_rent(observation)


def test_agents_decide_from_same_phase_before_any_payment(scenario: Scenario) -> None:
    agents = {person.id: RecordingAgent() for person in scenario.people}
    environment = Environment(scenario, agents)
    environment.step()

    assert agents[10].observations[0].person.cash == Decimal("1010")
    assert agents[20].observations[0].person.cash == Decimal("110")
    assert {agent.observations[0].period for agent in agents.values()} == {1}


def test_explicit_actions_bypass_agents(scenario: Scenario) -> None:
    agents = {person.id: RecordingAgent() for person in scenario.people}
    environment = Environment(scenario, agents)
    result = environment.step({10: Wait(), 20: Wait(), 30: Wait()})

    assert all(not agent.observations for agent in agents.values())
    assert all(outcome.paid is None for outcome in result.actions)
    assert environment.people[20].cash == Decimal("110")


@pytest.mark.parametrize(
    "actions",
    [
        {10: Wait()},
        {10: Wait(), 20: PayRent(1), 30: Wait()},
        {10: Wait(), 20: PayRent(99), 30: Wait()},
        {10: Wait(), 20: Wait(), 30: Wait(), 99: Wait()},
    ],
)
def test_invalid_actions_leave_period_and_economic_state_unchanged(
    scenario: Scenario, actions: Mapping[int, Action]
) -> None:
    environment = EnvironmentFactory.from_scenario(scenario)
    before = dict(environment.people)
    with pytest.raises(ValueError):
        environment.step(actions)
    assert environment.period == 0
    assert environment.people == before


def test_unknown_action_type_is_rejected_before_settlement(scenario: Scenario) -> None:
    environment = EnvironmentFactory.from_scenario(scenario)
    before = dict(environment.people)
    with pytest.raises(TypeError, match="Unsupported action"):
        environment.step({10: Wait(), 20: PayRent(2), 30: cast(Action, object())})
    assert environment.people == before
    assert environment.period == 0


def test_agent_failure_does_not_commit_income_or_period(scenario: Scenario) -> None:
    class FailingAgent(HouseAgent):
        def decide(self, observation: Observation) -> Action:
            raise RuntimeError("Controller failed")

    environment = EnvironmentFactory.from_scenario(scenario, agent_factory=lambda _: FailingAgent())
    before = dict(environment.people)
    with pytest.raises(RuntimeError, match="Controller failed"):
        environment.step()
    assert environment.people == before
    assert environment.period == 0


def test_population_and_controller_instances_are_independent(scenario: Scenario) -> None:
    first = EnvironmentFactory.from_scenario(scenario)
    second = EnvironmentFactory.from_scenario(scenario)
    first.step()

    assert second.people[20].cash == Decimal("50")
    assert second.period == 0
    assert first.agents[20] is not second.agents[20]


@pytest.mark.parametrize("missing_agent", [True, False])
def test_agent_mapping_must_match_people(scenario: Scenario, missing_agent: bool) -> None:
    agents = {person.id: HouseAgent() for person in scenario.people}
    if missing_agent:
        del agents[20]
    else:
        agents[99] = HouseAgent()
    with pytest.raises(ValueError, match="exactly one agent"):
        Environment(scenario, agents)


def test_agent_instance_cannot_be_shared_between_people(scenario: Scenario) -> None:
    agent = HouseAgent()
    with pytest.raises(ValueError, match="own agent instance"):
        EnvironmentFactory.from_scenario(scenario, agent_factory=lambda _: agent)


@pytest.mark.parametrize("field", ["regions", "people", "households", "homes"])
def test_duplicate_object_ids_are_rejected(scenario: Scenario, field: str) -> None:
    values = getattr(scenario, field)
    changes: dict[str, Any] = {field: (*values, values[0])}
    duplicate = replace(scenario, **changes)
    with pytest.raises(ValueError, match="Duplicate|already exists"):
        EnvironmentFactory.from_scenario(duplicate)


def test_household_membership_must_be_one_to_one(scenario: Scenario) -> None:
    invalid_households = (
        (Household(100, 99), Household(200, 20), Household(300, 30)),
        (Household(100, 10), Household(200, 10), Household(300, 30)),
        scenario.households[:2],
    )
    for households in invalid_households:
        with pytest.raises(ValueError, match="household"):
            EnvironmentFactory.from_scenario(replace(scenario, households=households))


def test_home_must_reference_an_existing_region(scenario: Scenario) -> None:
    homes = (replace(scenario.homes[0], region_id=99), *scenario.homes[1:])
    with pytest.raises(ValueError, match="Unknown region"):
        EnvironmentFactory.from_scenario(replace(scenario, homes=homes))


def test_public_collections_and_step_observations_are_read_only(scenario: Scenario) -> None:
    environment = EnvironmentFactory.from_scenario(scenario)
    with pytest.raises(TypeError):
        environment.people[10] = Entity(10)  # type: ignore[index]
    with pytest.raises(TypeError):
        environment.households[100] = Household(100, 30)  # type: ignore[index]
    result = environment.step()
    with pytest.raises(TypeError):
        result.observations[20] = result.observations[10]  # type: ignore[index]


def test_empty_environment_can_step() -> None:
    environment = EnvironmentFactory.from_scenario(Scenario((), (), (), ()))
    result = environment.step()
    assert result.period == 1
    assert result.actions == ()
    assert result.observations == {}
