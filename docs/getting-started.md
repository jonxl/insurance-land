# Getting started

## Setup

The project uses uv to manage Python and development dependencies. Its Python requirement is `>=3.14`, and [.python-version](../.python-version) selects the 3.14 series for local use. Install uv in your development environment, then run these commands from the repository root:

```bash
uv sync --locked
uv run python main.py
```

`uv sync --locked` creates or synchronizes `.venv` using the checked-in [uv.lock](../uv.lock). The application uses Python's standard library; pytest, Ruff, and mypy are development dependencies.

[pyproject.toml](../pyproject.toml) sets `package = false`. uv manages this repository as an application. Application packages live at the repository root and use imports such as `from factories import EnvironmentFactory`.

Run the entry point from the repository root:

```bash
uv run python main.py
```

## What the entry point does

[main.py](../main.py) contains a `main()` function and the usual module entry guard. Importing the module defines the function; executing it starts the simulation.

`main()` creates a seeded 4-by-4 grid with 16 people and three insurance firms. Lorenz curves assign incomes and home counts, spatial noise generates prices, and income-biased matching assigns residences. The example opens insurance coverage and runs three periods, reporting disasters, destroyed homes, and paid claims.

Policies are deterministic examples, not trained agents. The [initial-distributions guide](initial-distributions.md) explains the reusable configuration, matrix snapshots, and explicit payment and disaster rules.

## Create and inspect a small environment

This complete example can be run in a Python session started with `uv run python` from the repository root:

```python
from factories import EnvironmentFactory, PopulationConfig, RegionConfig

environment = EnvironmentFactory.create(
    PopulationConfig(
        regions=(RegionConfig(name="Coast", households=4, homes=4),),
        seed=7,
    )
)

assert len(environment.people) == 4
assert len(environment.agents) == 4
assert environment.period == 0

observation = environment.observe(1)
print(observation.person.cash)
print(observation.residence)
print(observation.owned_homes)

result = environment.step()
assert result.period == 1
print(result.actions)
```

Change the configuration in `main.py` to choose the main simulation's population, seed, balances, income, values, and rents. The loop determines how many periods run. The [factories guide](factories.md) covers the original region-based factory; the [initial-distributions guide](initial-distributions.md) covers the grid factory.

## Verification commands

```bash
uv run pytest -q
uv run ruff check
uv run ruff format --check
uv run mypy
```

pytest checks behavior, Ruff checks lint and formatting rules, and mypy checks types in the application modules and `tests/`. See [development](development.md) for the test organization and coding conventions.
