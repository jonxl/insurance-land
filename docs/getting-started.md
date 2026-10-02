# Getting started

## Setup

The project uses uv to manage Python and development dependencies. Its Python requirement is `>=3.14`, and [.python-version](../.python-version) selects the 3.14 series for local use. Install uv in your development environment, then run these commands from the repository root:

```bash
uv sync --locked
uv run python -m src.main
```

`uv sync --locked` creates or synchronizes `.venv` using the checked-in [uv.lock](../uv.lock). The application uses Python's standard library; pytest, Ruff, and mypy are development dependencies.

[pyproject.toml](../pyproject.toml) sets `package = false`. uv manages this repository as an application. The `src` directory is an importable Python package, and modules use imports such as `from src.factories import EnvironmentFactory`.

Run the entry point as a module from the repository root so that those imports resolve consistently:

```bash
uv run python -m src.main
```

## What the entry point does

[src/main.py](../src/main.py) contains a `main()` function and the usual module entry guard. Importing the module defines the function; executing it starts the simulation.

`main()` creates this configuration:

| Region | People and households | Homes | Occupied homes | Vacant homes | People without a residence |
| --- | ---: | ---: | ---: | ---: | ---: |
| Coast | 10 | 12 | 10 | 2 | 0 |
| Inland | 20 | 18 | 18 | 0 | 2 |

The factory uses seed `42` to determine resident allocation and ownership. It assigns one controller to every person, including people without a residence. Each iteration of the three-period loop calls `environment.step()` and prints the number of successful and unsuccessful rent-payment actions.

A successful payment result means the action was accepted and settled according to the housing rules. An unsuccessful payment means the tenant did not have enough cash. The default controller only requests payments for occupied rental homes with positive rent.

## Create and inspect a small environment

This complete example can be run in a Python session started with `uv run python` from the repository root:

```python
from src.factories import EnvironmentFactory, PopulationConfig, RegionConfig

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

Change the configuration in `src/main.py` to choose the main simulation's population, seed, balances, income, values, and rents. The loop determines how many periods run. The [factories guide](factories.md) describes every configuration field.

## Verification commands

```bash
uv run pytest -q
uv run ruff check
uv run ruff format --check
uv run mypy
```

pytest checks behavior, Ruff checks lint and formatting rules, and mypy checks types in `src/` and `tests/`. See [development](development.md) for the test organization and coding conventions.
