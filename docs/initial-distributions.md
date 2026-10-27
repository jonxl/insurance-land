# Initial distributions and insurance experiments

The initial-distributions model now has a reusable implementation. Its records remain in `src/domain`, construction in `src/factories`, decisions in `src/agents`, and pure mathematical helpers in `src/utils/distributions.py`. It uses the standard library and `Decimal` money; no numerical or learning-library dependency is required.

Run the example from the repository root:

```bash
uv run python -m src.main
```

The example creates a 4-by-4 grid, 16 people, and three insurers. Its fixed quoting and cheapest-affordable purchasing policies demonstrate the interfaces; they are not trained agents.

## Generate a reproducible population

```python
from decimal import Decimal
from src.factories import EnvironmentFactory, GridPopulationConfig
from src.utils.distributions import PowerLorenz

config = GridPopulationConfig(
    rows=4,
    columns=4,
    seed=42,
    mean_annual_income=Decimal("50000"),
    periods_per_year=12,
    income_curve=PowerLorenz(2),
    ownership_curve=PowerLorenz(3),
    reference_price=Decimal("250000"),
    price_spread=0.4,
    length_scale=2.0,
    placement_noise=0.1,
    initial_cash=Decimal("10000"),
    rent_per_period=Decimal("1000"),
)
environment = EnvironmentFactory.create(config)
board = environment.grid_snapshot()
print(board.prices, board.owners, board.residents, board.destroyed)
```

`GridPopulationFactory.create(config)` returns a `Scenario` without attaching controllers. `EnvironmentFactory.create` attaches a distinct `HouseAgent` to each person; `agent_factory` supplies alternatives. Existing `PopulationConfig`, `RegionConfig`, and explicit scenarios continue to work.

This factory implements the report's one-home-per-person baseline. A home has a zero-based `(row, column)` position, an owner, and a resident. The grid is represented as a single region initially. People may own several homes or none. Owners receive their own residence before remaining titles are assigned. Remaining owner-capacity slots are shuffled, making assignment uniform among slots, not among owners.

Matrix snapshots are immutable tuples derived from home records. They are not a second mutable source of truth. Vacancies are `0` in the resident matrix. `home_ids` maps cells to the IDs used by actions and contracts.

### Mathematical utilities

- `random_stream(seed, component)` derives independent `Random` instances using SHA-256, without changing process-global randomness. Same seed, label, algorithm, and parameters reproduce the stream.
- `lorenz_shares(count, curve)` accepts a callable on `[0, 1]`. It validates endpoints, monotonicity, and convexity at population boundaries. Behavior between those boundaries is the curve author's responsibility.
- `PowerLorenz(exponent)` is a configurable example family; its exponent must be at least one.
- `round_counts(targets, total, rng)` rounds halves upward and corrects the largest residual until the total matches. Seeded randomness resolves ties.
- `allocate_money(total, shares, rng)` preserves an exact cent-denominated total, including rounding corrections.
- `gaussian_price_field(...)` implements the finite-grid, variance-normalized Gaussian field using separable smoothing. Its runtime is proportional to `rows * columns * (rows + columns)`, rather than storing all cell-pair weights.
- `match_residences(incomes, prices, noise=..., rng=...)` performs reusable noisy midrank matching without modifying inputs or assuming ownership. Equal-income ownership ranks are broken by a separate seeded stream.
- `poisson_count(rate, rng)` uses exponential arrival times. Zero rate produces no events; invalid or non-finite rates are rejected. Runtime grows with expected event count.

Annual income is allocated once and stored as `Entity.annual_income`. `Entity.income` is the fixed per-period amount: annual income divided by `periods_per_year`. Recurring division uses Decimal precision and is not rounded to cents each period. Annual allocations and home prices use cents; exceptionally small positive generated prices have a one-cent floor. Cash and initial tenant rent are explicit configurable constants, not inferred from wealth. Reference price denotes a marginal median, not an exact map mean. Grid shape and all relevant settings are needed alongside the seed to reproduce an experiment.

## Natural disasters

```python
from src.domain.disasters import DisasterConfig

environment = EnvironmentFactory.create(
    config,
    disasters=DisasterConfig(rate=0.5, footprint_rows=2, footprint_columns=2),
)
result = environment.step()
for event in result.disasters:
    print(event.cells, event.losses, event.displaced_people)

# Override only this period's rate; the footprint remains fixed.
environment.step(disaster_rate=2.0)
```

The rate is expected events per simulation period. Each event uniformly selects an eligible top-left position for a fixed rectangle fully contained in the grid. There is no edge clipping or wrapping, so the affected cell count is fixed. Overlap is allowed; already destroyed homes do not generate another building loss.

The working market sets destroyed homes' value and rent to zero, clears their resident, and retains their owner and location. `DisasterResult.losses` contains immutable pre-loss `Home` records for newly destroyed homes. Displaced people remain in the population and continue receiving income; attempting to move into a destroyed home is rejected. Rebuilding and relocation policies are not yet modeled.

Disaster streams are derived from the global seed and period number. Rejected steps do not advance the exposure sequence. Changing one period's rate does not shift later periods' streams.

## Insurance opening and claims

See `src/main.py` for a complete three-firm example. Supply `Insurer` records and one `InsurancePlanAgent[InsurerObservation, tuple[Offer, ...]]` per insurer to `EnvironmentFactory.create`. Each insurer policy receives immutable financial and housing observations and returns offers with globally unique IDs belonging to that firm.

A `HouseAgent` accepts an `insurance_policy` callable that receives `InsuranceObservation` and returns `CoverageChoice(offer_id, home_id)` objects. The provided `cheapest_affordable_coverage` baseline buys the cheapest eligible offer for each home in ID order while respecting its upfront cash budget. It does not compare coverage quality. Without a purchasing policy, the default is to decline optional insurance.

Call `environment.open_insurance()` once before the first step when firms are configured. Alternatively, provide a complete mapping of explicit choices keyed by person ID. The opening round collects all firm offers before purchasing decisions. Unknown references, ineligible products, duplicate interests, and unaffordable choices reject the entire economic update. The environment cannot step with configured firms until the opening round completes.

These are explicit toy contract rules:

- Premiums are paid once up front; contracts start in period 1 and expire after `term_periods`.
- Homeowners coverage applies to an owner's residence. Landlord coverage applies to their other homes, including vacant homes in this simplified model. Renters coverage applies to a nonowner resident.
- Building loss is the home's pre-disaster market value. Renters loss is the offer's explicit `contents_value`; the model does not infer possessions from home value.
- Claim amount is `min(limit, max(0, loss - deductible))`.
- Claims settle immediately after each disaster in contract-ID order. Payment is capped by available insurer capital; `Claim.due` and `Claim.paid` preserve the shortfall. Unpaid amounts are not automatically retried.
- Each contract pays for at most one total-loss event. Expired contracts and interests no longer matching the pre-loss ownership/residence receive no payment.

`environment.insurers`, `contracts`, and `claims` expose immutable records. Payouts and premiums transfer money; only external income adds money. Renewals, debts, reinsurance, additional living expenses, property sales, labor markets, and learned rewards/training are not inferred by these utilities.

## Timing and failure behavior

Each successful step credits income, collects and validates housing actions, settles rent by person ID, generates disasters, pays claims, and returns post-event observations. Insurer and housing state commit together. Invalid actions or settlement errors leave both economic states and the period unchanged. Stateful controller internals are not rolled back.

The report left some timing and contract rules open. The explicit choices above make the toy experiment runnable and reviewable; they are not research findings or assertions about real insurance practice.

## Checks

```bash
uv run pytest -q
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy
```
