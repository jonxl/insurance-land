from decimal import Decimal

from agents import HouseAgent, InsurancePlanAgent, RLAgent
from agents.base import Observation, PayRent, Wait
from domain.models import Entity, Home, Household, Region


def test_house_agent_exposes_rent_as_behavior() -> None:
    observation = Observation(
        period=1,
        person=Entity(2, cash=Decimal("100")),
        household=Household(2, person_id=2),
        residence=Home(
            1,
            region_id=1,
            owner_id=1,
            market_value=Decimal("1000"),
            occupant_id=2,
            rent=Decimal("10"),
        ),
        region=Region(1, "Coast"),
        owned_homes=(),
    )
    agent = HouseAgent()
    assert isinstance(agent, RLAgent)
    assert agent.pay_rent(observation) == PayRent(1)
    assert agent.decide(observation) == PayRent(1)

    policy_agent = HouseAgent(policy=lambda _: Wait())
    assert policy_agent.decide(observation) == Wait()
    assert policy_agent.pay_rent(observation) == PayRent(1)


def test_insurance_plan_agent_uses_injected_policy() -> None:
    agent = InsurancePlanAgent[Decimal, Decimal](policy=lambda expected_cost: expected_cost * 2)
    assert isinstance(agent, RLAgent)
    assert agent.decide(Decimal("50")) == Decimal("100")
