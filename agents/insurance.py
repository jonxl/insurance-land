from collections.abc import Callable

from agents.base import RLAgent


class InsurancePlanAgent[ObservationT, ActionT](RLAgent[ObservationT, ActionT]):
    """Policy-controlled insurance role, independent of a particular learning library."""

    def __init__(self, policy: Callable[[ObservationT], ActionT]) -> None:
        self._policy = policy

    def decide(self, observation: ObservationT) -> ActionT:
        return self._policy(observation)
