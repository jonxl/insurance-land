from collections.abc import Callable

from src.agents.base import Action, Observation, PayRent, RLAgent, Wait


class HouseAgent(RLAgent[Observation, Action]):
    def __init__(self, policy: Callable[[Observation], Action] | None = None) -> None:
        self._policy = policy

    def decide(self, observation: Observation) -> Action:
        if self._policy is not None:
            return self._policy(observation)
        return self.pay_rent(observation)

    def pay_rent(self, observation: Observation) -> Action:
        """Request a rent payment; the environment validates and settles it."""
        home = observation.residence
        if home is None or home.owner_id == observation.person.id or home.rent == 0:
            return Wait()
        return PayRent(home.id)
