# Insurance Land documentation

Insurance Land is a Python simulation foundation for a market of people, homes, and decision-making agents. Factories build the initial population, an `Environment` connects its objects, and `src/main.py` advances the simulation through a sequence of periods.

Each person has an individual budget, a single-person household, and a `HouseAgent`. A home records its owner and its optional resident separately. Rent is a behavior of the house agent, with payment settlement handled by the economic model.

## Reading guide

| Document | What it explains |
| --- | --- |
| [Getting started](getting-started.md) | uv setup, running the main loop, and inspecting a small simulation |
| [Architecture](architecture.md) | Directory layout, responsibilities, relationships, and state management |
| [Domain model](domain-model.md) | People, households, regions, homes, money, and housing operations |
| [Factories](factories.md) | Configuration, seeded population generation, explicit scenarios, and agent creation |
| [Agents](agents.md) | The `RLAgent` hierarchy, observations, actions, policies, and rent behavior |
| [Simulation lifecycle](simulation.md) | Environment assembly, step ordering, settlement, results, and failure handling |
| [Development](development.md) | Code organization, checks, behavioral tests, and extension workflow |

Start with getting started, then architecture. Read the domain model before changing economic behavior, and the simulation lifecycle before changing when actions take effect.

## Run the project

From the repository root:

```bash
uv sync --locked
uv run python -m src.main
```

The entry point creates two regions, 30 people, 30 households, and 30 homes, then runs three periods. See [getting started](getting-started.md) for the population breakdown and commands for verification.

## Core relationships

- A person is represented by `Entity`, which stores cash and income.
- Each person belongs to exactly one single-person `Household`.
- Each person has their own `HouseAgent` instance.
- A home has exactly one existing owner and at most one resident.
- A person occupies at most one home and may own multiple homes.
- A home's region determines the region of its resident's household.
- Agents choose actions; the environment validates them and coordinates settlement.

The class and field names in these documents match the source code. Links to implementation files are included throughout so that behavior can be traced to its owner.
