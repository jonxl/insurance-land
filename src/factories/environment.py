from collections.abc import Callable

from src.agents.house import HouseAgent
from src.domain.models import Entity
from src.environment import Environment, Scenario
from src.factories.population import PopulationConfig, PopulationFactory


class EnvironmentFactory:
    @staticmethod
    def create(
        config: PopulationConfig,
        *,
        agent_factory: Callable[[Entity], HouseAgent] | None = None,
    ) -> Environment:
        return EnvironmentFactory.from_scenario(
            PopulationFactory.create(config), agent_factory=agent_factory
        )

    @staticmethod
    def from_scenario(
        scenario: Scenario,
        *,
        agent_factory: Callable[[Entity], HouseAgent] | None = None,
    ) -> Environment:
        agents = {
            person.id: agent_factory(person) if agent_factory is not None else HouseAgent()
            for person in scenario.people
        }
        return Environment(scenario, agents)
