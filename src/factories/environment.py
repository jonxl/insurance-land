from collections.abc import Callable, Mapping

from src.agents.house import HouseAgent
from src.agents.insurance import InsurancePlanAgent
from src.domain.disasters import DisasterConfig
from src.domain.insurance import Insurer, InsurerObservation, Offer
from src.domain.models import Entity
from src.environment import Environment, Scenario
from src.factories.grid import GridPopulationConfig, GridPopulationFactory
from src.factories.population import PopulationConfig, PopulationFactory


class EnvironmentFactory:
    @staticmethod
    def create(
        config: PopulationConfig | GridPopulationConfig,
        *,
        agent_factory: Callable[[Entity], HouseAgent] | None = None,
        disasters: DisasterConfig | None = None,
        insurers: tuple[Insurer, ...] = (),
        insurer_agents: Mapping[int, InsurancePlanAgent[InsurerObservation, tuple[Offer, ...]]]
        | None = None,
    ) -> Environment:
        return EnvironmentFactory.from_scenario(
            (
                GridPopulationFactory.create(config)
                if isinstance(config, GridPopulationConfig)
                else PopulationFactory.create(config)
            ),
            agent_factory=agent_factory,
            disasters=disasters,
            insurers=insurers,
            insurer_agents=insurer_agents,
        )

    @staticmethod
    def from_scenario(
        scenario: Scenario,
        *,
        agent_factory: Callable[[Entity], HouseAgent] | None = None,
        disasters: DisasterConfig | None = None,
        insurers: tuple[Insurer, ...] = (),
        insurer_agents: Mapping[int, InsurancePlanAgent[InsurerObservation, tuple[Offer, ...]]]
        | None = None,
    ) -> Environment:
        agents = {
            person.id: agent_factory(person) if agent_factory is not None else HouseAgent()
            for person in scenario.people
        }
        return Environment(
            scenario, agents, disasters=disasters, insurers=insurers, insurer_agents=insurer_agents
        )
