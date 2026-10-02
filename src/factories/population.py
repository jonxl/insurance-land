from dataclasses import dataclass
from decimal import Decimal
from random import Random

from src.domain.models import Entity, Home, Household, Region
from src.environment import Scenario
from src.utils.validation.money import validate_money


@dataclass(frozen=True, slots=True)
class RegionConfig:
    name: str
    households: int
    homes: int | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Region name cannot be empty")
        if type(self.households) is not int or self.households < 0:
            raise ValueError("Household count must be a nonnegative integer")
        if self.homes is not None and (type(self.homes) is not int or self.homes < 0):
            raise ValueError("Home count must be a nonnegative integer")
        if self.homes and not self.households:
            raise ValueError("Generating homes requires at least one owner in the region")


@dataclass(frozen=True, slots=True)
class PopulationConfig:
    regions: tuple[RegionConfig, ...]
    seed: int = 0
    initial_cash: Decimal = Decimal("10000")
    income_per_period: Decimal = Decimal("2000")
    home_value: Decimal = Decimal("250000")
    rent_per_period: Decimal = Decimal("1000")
    owner_occupancy_rate: float = 0.6

    def __post_init__(self) -> None:
        validate_money(self.initial_cash, field="initial_cash")
        validate_money(self.income_per_period, field="income_per_period")
        validate_money(self.home_value, field="home_value")
        validate_money(self.rent_per_period, field="rent_per_period")
        if not 0 <= self.owner_occupancy_rate <= 1:
            raise ValueError("Owner occupancy rate must be between zero and one")


class PopulationFactory:
    @staticmethod
    def create(config: PopulationConfig) -> Scenario:
        """Generate local ownership; seed controls owners, vacancies, and housing allocation.

        A region with only one person necessarily has that person own all its homes.
        Home shortages leave some people without a residence; extra homes are vacant.
        """
        random = Random(config.seed)
        regions: list[Region] = []
        people: list[Entity] = []
        households: list[Household] = []
        homes: list[Home] = []
        for region_id, spec in enumerate(config.regions, start=1):
            regions.append(Region(id=region_id, name=spec.name))
            resident_ids: list[int] = []
            for _ in range(spec.households):
                person_id = len(people) + 1
                people.append(Entity(person_id, config.initial_cash, config.income_per_period))
                households.append(Household(id=person_id, person_id=person_id))
                resident_ids.append(person_id)
            random.shuffle(resident_ids)
            home_count = spec.households if spec.homes is None else spec.homes
            for index in range(home_count):
                occupant_id = resident_ids[index] if index < len(resident_ids) else None
                if occupant_id is not None and (
                    len(resident_ids) == 1 or random.random() < config.owner_occupancy_rate
                ):
                    owner_id = occupant_id
                else:
                    owners = [person_id for person_id in resident_ids if person_id != occupant_id]
                    owner_id = random.choice(owners)
                rent = (
                    config.rent_per_period
                    if occupant_id is not None and occupant_id != owner_id
                    else Decimal("0")
                )
                homes.append(
                    Home(
                        id=len(homes) + 1,
                        region_id=region_id,
                        owner_id=owner_id,
                        market_value=config.home_value,
                        occupant_id=occupant_id,
                        rent=rent,
                    )
                )
        return Scenario(tuple(regions), tuple(people), tuple(households), tuple(homes))
