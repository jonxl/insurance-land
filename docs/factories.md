# Factories and scenario creation

Factories turn a population description into connected simulation objects. They support generated populations and explicitly specified scenarios through the same environment constructor.

## Factory interfaces

| Interface | Returns | Purpose |
| --- | --- | --- |
| `PopulationFactory.create(config)` | `Scenario` | Generate regions, people, households, and homes |
| `EnvironmentFactory.create(config, agent_factory=...)` | `Environment` | Generate a scenario and attach agents |
| `EnvironmentFactory.from_scenario(scenario, agent_factory=...)` | `Environment` | Attach agents to an explicit scenario |

Import these classes from `factories`. `Scenario` is defined in `environment` and contains tuples named `regions`, `people`, `households`, and `homes`.

## Region configuration

`RegionConfig` describes one generated region:

| Field | Default | Meaning |
| --- | --- | --- |
| `name` | Required | Nonblank region name |
| `households` | Required | Number of single-person households and therefore people |
| `homes` | `None` | Home count; `None` uses the household count |

Counts must be nonnegative integers; booleans are rejected as counts. A region with generated homes needs at least one person to own them. A zero-person, zero-home region is valid.

If there are fewer homes than people, the generated population has some people without a residence. Extra homes are vacant. Every generated home still has an owner.

## Population configuration

`PopulationConfig` applies common economic parameters to the generated regions:

| Field | Default | Meaning |
| --- | --- | --- |
| `regions` | Required | Tuple of `RegionConfig` objects |
| `seed` | `0` | Seed for a local `random.Random` generator |
| `initial_cash` | `Decimal("10000")` | Starting cash for each person |
| `income_per_period` | `Decimal("2000")` | Income assigned to each person |
| `home_value` | `Decimal("250000")` | Recorded value assigned to each home |
| `rent_per_period` | `Decimal("1000")` | Rent assigned to tenant-occupied homes |
| `owner_occupancy_rate` | `0.6` | Probability that an allocated resident owns their residence |

The owner-occupancy rate is a probability per occupied home, rather than an exact population quota. It must fall between zero and one. A one-person region necessarily assigns all its homes to that person, including their residence.

```python
from decimal import Decimal

from factories import EnvironmentFactory, PopulationConfig, RegionConfig

config = PopulationConfig(
    regions=(
        RegionConfig(name="Coast", households=10, homes=12),
        RegionConfig(name="Inland", households=20, homes=18),
    ),
    seed=42,
    initial_cash=Decimal("8000"),
    income_per_period=Decimal("2400"),
    home_value=Decimal("300000"),
    rent_per_period=Decimal("1200"),
    owner_occupancy_rate=0.5,
)
environment = EnvironmentFactory.create(config)
assert len(environment.people) == 30
```

## Population generation algorithm

For each region, in configuration order, the population factory:

1. Assigns the region an ID starting at 1.
2. Creates the requested people and one household per person. Person IDs increase across the whole population; generated household IDs equal their person IDs.
3. Shuffles the region's person IDs using the local random generator.
4. Allocates residents to homes from that shuffled list until it exhausts people or homes.
5. For an occupied home, selects owner occupancy according to the configured probability. Otherwise, it selects a different person from that region as owner.
6. Assigns an owner from the same region to each vacant home.
7. Assigns positive or zero configured rent to tenant-occupied homes, and zero rent to owner-occupied or vacant homes.

Home IDs increase across all regions. Selecting owners separately for each home permits one person to own several properties.

The same configuration and seed reproduce the generated records under the same implementation and runtime. Changing the region order or counts changes how random draws are consumed. A custom agent's randomness is managed by that agent separately from population generation.

## Explicit scenarios

Use `from_scenario` when exact ownership, residence, balances, or IDs matter:

```python
from decimal import Decimal

from domain.models import Entity, Home, Household, Region
from environment import Scenario
from factories import EnvironmentFactory

scenario = Scenario(
    regions=(Region(id=1, name="Coast"),),
    people=(
        Entity(id=10, cash=Decimal("1000"), income=Decimal("100")),
        Entity(id=20, cash=Decimal("500"), income=Decimal("200")),
    ),
    households=(Household(id=100, person_id=10), Household(id=200, person_id=20)),
    homes=(
        Home(
            id=1,
            region_id=1,
            owner_id=10,
            occupant_id=20,
            market_value=Decimal("250000"),
            rent=Decimal("300"),
        ),
    ),
)
environment = EnvironmentFactory.from_scenario(scenario)
assert environment.observe(20).household.id == 200
assert environment.observe(10).residence is None
assert environment.step().observations[20].person.cash == Decimal("400")
```

The environment checks references and one-to-one relationships when assembling a scenario. An explicitly constructed scenario can express cross-region property ownership because every home references an owner by person ID.

## Creating controllers

Both environment factory methods accept `agent_factory`, a callable taking an `Entity` and returning a `HouseAgent`. It is called once per person. Omitting it creates a fresh default `HouseAgent` for each person.

```python
from agents import HouseAgent
from agents.base import Wait
from factories import EnvironmentFactory, PopulationConfig, RegionConfig

environment = EnvironmentFactory.create(
    PopulationConfig(regions=(RegionConfig(name="Coast", households=3),)),
    agent_factory=lambda person: HouseAgent(policy=lambda observation: Wait()),
)
result = environment.step()
assert all(outcome.paid is None for outcome in result.actions)
```

The environment requires distinct controller instances. A factory can construct agents with person-specific policy parameters or state. Creating a fresh environment from a scenario creates an independent economic state and, through the default factory, fresh agents.
