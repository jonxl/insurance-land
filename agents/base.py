from abc import ABC, abstractmethod
from dataclasses import dataclass

from domain.models import Entity, Home, Household, Region


@dataclass(frozen=True, slots=True)
class Observation:
    period: int
    person: Entity
    household: Household
    residence: Home | None
    region: Region | None
    owned_homes: tuple[Home, ...]


@dataclass(frozen=True, slots=True)
class Wait:
    pass


@dataclass(frozen=True, slots=True)
class PayRent:
    home_id: int


type Action = Wait | PayRent


class RLAgent[ObservationT, ActionT](ABC):
    """Decision interface for policies; training is supplied by the learning algorithm."""

    @abstractmethod
    def decide(self, observation: ObservationT) -> ActionT:
        raise NotImplementedError
