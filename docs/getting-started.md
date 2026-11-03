# Getting started

## Setup

The project uses uv to manage Python and development dependencies. Its Python requirement is `>=3.14`, and [.python-version](../.python-version) selects the 3.14 series for local use. Install uv in your development environment, then run these commands from the repository root:

```bash
uv sync --locked
uv run python -m experiments.command_center
```

`uv sync --locked` creates or synchronizes `.venv` using the checked-in [uv.lock](../uv.lock). The application uses Python's standard library and NumPy. Matplotlib generates report figures; it is included with pytest, Ruff, and mypy in the development dependencies installed by this command.

[pyproject.toml](../pyproject.toml) sets `package = false`. uv manages this repository as an application. Application packages live at the repository root and use imports such as `from factories import EnvironmentFactory`.

## Run the command center

Open [http://127.0.0.1:8000](http://127.0.0.1:8000) after starting the server. It serves the included Dev Peace, Dev Standard, and Dev Chaos recordings and runs independent, named experiments. The experiment type determines its initial allocations and disaster-rate schedule; the name identifies the saved run.

Experiment settings include the seed, number of periods, grid dimensions, homes per region, disaster rate, and disaster-size parameters. The default run has 8-by-8 regions, 256 homes, seed 42, and 120 periods. [Experiment presets](initial-distributions.md#command-center-experiment-presets) describes the differences between types.

Maps show the recorded population and housing state. Research charts show distributions and outcomes over time. Playback and the event timeline inspect the same recorded periods; they do not rerun the simulation.

### Server options

The server listens locally on `127.0.0.1`. To use another port or an existing recording directory:

```bash
uv run python -m experiments.command_center --port 9000 --directory studies/webui
```

Open `http://127.0.0.1:9000` for this example. `--directory` defaults to `studies/webui` and controls both the served files and the location of saved experiments.

### Saved experiments

Runs execute in the background, with additional runs waiting while one is active. Progress is recorded by period. Closing or refreshing the browser does not stop the simulation, provided the server remains running.

Each run is saved under `studies/webui/runs/<id>/` by default. Its `run.json` stores the name, configuration, progress, and status; `assets/world-history.json` contains the completed snapshots, and `diagnostics.html` provides the recorded view. Completed experiments remain available after restarting the server.

Stopping the server interrupts unfinished runs. On restart, those runs are marked failed; they do not resume automatically. Their settings remain available for a new run.

### Regenerate reference recordings and figures

The repository includes reference recordings, so regeneration is optional:

```bash
uv run python -m experiments.generate_worlds
```

This regenerates the three reference experiments and report figures under `studies/webui`. It replaces those generated reference files, not the saved runs in `runs/`. The command accepts `--seed`, `--periods`, and `--output`; for example:

```bash
uv run python -m experiments.generate_worlds --seed 7 --periods 60 --output studies/example
uv run python -m experiments.command_center --directory studies/example
```

## Terminal example

Run the small terminal demonstration from the repository root:

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
