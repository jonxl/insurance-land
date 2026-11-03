# Development guide

## Code organization principles

Functions should represent coherent operations. A function can be useful even when it has one caller; its purpose and readability determine whether it deserves a name. Keep related work together and split a function when it takes on a separate responsibility.

Domain rules belong near the economic concepts they govern. For example, `HousingMarket.pay_rent` owns cash settlement, while `HouseAgent.pay_rent` owns the decision to request payment. The environment owns their sequencing.

Shared helpers belong in categorized utility packages. The current validation helpers live in `utils/validation/`:

| Helper | Responsibility |
| --- | --- |
| `validate_money` | Require a finite, nonnegative `Decimal` and provide field-specific errors |
| `index_by_id` | Build a unique-ID dictionary and reject duplicates |

Use comments and docstrings to explain important behavior, ordering, or reasoning. Names and ordinary control flow should communicate routine implementation details.

## Local workflow

From the repository root:

```bash
uv sync --locked
uv run python main.py
uv run pytest -q
uv run ruff check
uv run ruff format --check
uv run mypy
```

To apply the configured formatter:

```bash
uv run ruff format
```

Configuration lives in [pyproject.toml](../pyproject.toml). Ruff targets Python 3.14 and uses a 100-character line length. Enabled lint rule families cover Python errors, unused code, imports, common bug patterns, modernization, and simplification. mypy runs in strict mode over the application modules and `tests`.

pytest discovers tests in `tests/`, adds the repository root to the import path, and enables strict configuration and marker checking.

## Command-center development

The frontend uses Bun 1.2.18 as its package manager, script runtime, and test runner. Use Bun for all frontend commands; Python commands continue to use uv.

Edit the HTML shell in [experiments/diagnostics.html](../experiments/diagnostics.html), and TypeScript and CSS in [experiments/ui](../experiments/ui). TypeScript compiles to browser JavaScript in `experiments/ui/dist/`; include those generated files with source changes so Python users can run the command center without installing frontend tools.

From the repository root:

```bash
bun install --frozen-lockfile
bun run check
bun run build
bun run test
uv run pytest tests/test_command_center.py tests/test_worlds.py tests/test_viewer.py -q
```

`bun run check` checks types without writing files. `bun run test` builds the browser modules and runs the interaction and loading tests with Bun. These cover saved runs, progress, presets, experiment navigation, timeline behavior, and recording loading. They do not replace browser checks of layout or animation.

Run `bun run watch` while editing TypeScript. The command center serves the current HTML, CSS, and compiled JavaScript; refresh the browser after changes. Restart the server after changing Python code.

[.prettierrc.json](../.prettierrc.json) configures two-space indentation and a 100-character print width. Format browser source with Bun:

```bash
bunx --bun prettier@3.8.2 --write experiments/diagnostics.html 'experiments/ui/*.ts' 'experiments/ui/*.css'
```

[.prettierignore](../.prettierignore) excludes generated browser files. Exported pages load their recording JSON separately. Rebuild TypeScript before regenerating distributable reference pages and figures with `uv run python -m experiments.generate_worlds`; see [regeneration instructions](getting-started.md#regenerate-reference-recordings-and-figures).

## Dependency management

Use uv for Python dependency changes. Add application dependencies with `uv add <package>` and development tools with `uv add --dev <package>`. Keep `pyproject.toml` and `uv.lock` together when dependency requirements change.

The project is configured as an application with `package = false`. Application packages live at the repository root. Run `uv run python main.py` from that directory.

Use `bun add --dev <package>` for frontend development tools. Keep `package.json` and `bun.lock` together when dependencies change. Commit only the Bun frontend lockfile; use `bun install --frozen-lockfile` for reproducible installs.

## Test organization

| Test module | Behavior covered |
| --- | --- |
| [test_housing.py](../tests/test_housing.py) | Ownership versus residence, rent conservation, insufficient cash, moves, title transfers, monetary validation, and protected records |
| [test_factories.py](../tests/test_factories.py) | Seeded reproducibility, population counts, allocation, ownership probabilities, vacancies, and configuration validation |
| [test_environment.py](../tests/test_environment.py) | Object assembly, individual controllers, income timing, shared decision phase, action validation, state preservation on error, and result snapshots |
| [test_agents.py](../tests/test_agents.py) | House rent behavior, policy injection, and the insurance controller interface |

Tests should verify economic and orchestration behavior that could fail independently of code structure. Useful assertions include conservation of cash during transfers, preservation of residence during title changes, and unchanged economic state after rejected actions.

For a focused check:

```bash
uv run pytest tests/test_environment.py -q
```

## Working with records and relationships

Treat frozen records and read-only mappings as the public state interface. Route economic changes through domain operations. Derive residence and ownership from homes so related views cannot drift apart.

When adding a record field, establish its local validation rules in the model. When adding a reference to another object, establish relationship validation in the component that holds both collections. Update explicit scenario examples and factory-generated records when the construction contract changes.

## Adding decision behavior

A house policy consumes an `Observation` and returns an `Action`. A callable is appropriate for a focused decision rule; a `HouseAgent` subclass is appropriate for related behavior or controller state. Supply it through the environment factory's `agent_factory` argument.

When introducing a new action, define its data contract, validate who may request it, implement the economic transition, and place settlement deliberately within the period. Add behavioral tests for its successful effect and for rejected requests preserving state. The [simulation guide](simulation.md) describes the ordering that existing actions follow.

Keep learning-algorithm concerns in the policy or controller layer. The shared `RLAgent` interface describes observation-to-action decisions, and domain records describe the state those decisions affect.

## Keeping documentation accurate

Update the relevant guide when changing a public field, construction contract, command, or timing rule. Examples should use the actual import paths and configured entry point. The documentation index in [README.md](README.md) maps readers to each topic.

For a change spanning several layers, check the model guide, factories guide, agent guide, and simulation guide together so they describe the same behavior.
