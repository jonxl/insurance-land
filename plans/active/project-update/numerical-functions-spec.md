# NumPy numerical functions for simulation setup and disasters

Status: implementation specification for review; runtime changes are not yet implemented.

Source: [Project Update, October 28, 2026](project-update.pdf), especially sections 4–8. This specification covers the numerical foundation discussed alongside that report. Q-learning, payment schedules, property trading, and experiment reporting are separate work.

## 1. Purpose and boundaries

Express the report's mathematical operations as reusable functions. NumPy supplies arrays, Gaussian draws, Poisson draws, weighted choices, and matrix operations. Our functions supply the model equations, validation, ordering conventions, and relationships between those operations.

The flow is:

```text
Configuration and component random generators
    → price field, income shares, ownership counts, residence assignment
    → existing Scenario / Home / Entity records
    → opening insurance round
    → sampled disaster locations each period
    → existing damage and claims settlement
```

Hidden risk follows its own initialization path:

```text
Independent Gaussian noise → smooth_field → exponential weights
    → anchor_probabilities → fixed private distribution for the episode
```

Some functions are deterministic transformations; others sample random outcomes. Lorenz shares and smoothing do not require random sampling. Keeping that distinction explicit makes the intermediate results inspectable and testable.

Keep these functions in `utils/distributions.py` initially. Factories compose them for setup; `domain/disasters.py` composes them for events. Numerical functions must not mutate homes, cash, contracts, or input arrays.

## 2. Shared conventions

- Floating numerical outputs are NumPy `float64` arrays. Index/count outputs are `int64` arrays; reject totals outside the supported integer range before conversion.
- Coordinates and person indices are zero-based inside numerical functions. Existing domain IDs remain one-based and are assigned by the factory.
- Grid flattening uses row-major order throughout. For a grid with `columns` columns, flat index `j` corresponds to `divmod(j, columns)`.
- Accept array-like numerical inputs, validate dimensions, and convert internally. Reject empty arrays, nonfinite inputs, and invalid dimensions. Boolean values are not valid counts, dimensions, or seeds.
- Functions return new arrays and never alter caller inputs. Deterministic functions consume no randomness.
- Scalar parameters such as spreads, lengths, and rates must be finite and satisfy the bounds below.
- Use absolute tolerance `1e-12`, with zero relative tolerance, for probability sums, sampled Lorenz validation, and residual ties. Reject materially invalid inputs; repair only numerical deviations within this tolerance.
- Validate inputs before drawing randomness. Numerical failures must not commit simulation state.
- NumPy values are a calculation layer. Domain cash, premiums, claims, and stored money continue to use `Decimal`.

The signatures below are proposed public contracts. `FloatArray` and `IntArray` denote NumPy arrays of the dtypes above; the implementation should provide corresponding `numpy.typing` annotations.

## 3. Reproducible random streams

Provide a NumPy generator helper:

```python
def numpy_stream(seed: int, component: str) -> np.random.Generator:
    ...
```

Require a nonnegative integer seed and a nonempty component label. Derive seed material from a stable digest of the global seed and label, using the existing SHA-256 convention as the starting point. Use an explicitly selected NumPy bit generator, `PCG64`, rather than Python's process-dependent `hash()` or global `np.random` state.

Use distinct labels for `prices`, `risk`, `income`, `income-ranking`, `ownership-counts`, `ownership-titles`, and `placement`. Disaster counts and locations use separate labels including sequence/run/period identity where applicable.

This is a migration from `random.Random`: identical old and new seeds are not expected to produce identical draws. Reproducibility applies to the new algorithm and recorded dependency versions. Existing behavior tests should preserve mathematical invariants rather than old sampled boards.

For period events, derive fresh count/location generators from the period's stable identity. A failed step can then retry the same draws without advancing persistent generator state. Match those identities across worlds for controlled comparisons; changing risk probabilities must not change the Poisson count stream.

The future run lifecycle must supply distinct run identities. Until that exists, the environment's monotonic period counter is sufficient for a single continuous simulation.

## 4. `smooth_field`

```python
def smooth_field(noise: FloatArray, length_scale: float) -> FloatArray:
    ...
```

Input: a nonempty two-dimensional finite matrix `noise` with shape `(rows, columns)` and a nonnegative length scale. Output: a new matrix of the same shape.

For positive length scale, implement exactly:

```text
w[a,b,u,v] = exp(-((a-u)^2 + (b-v)^2) / (2 * length_scale^2))
Z[a,b] = sum(w[a,b,u,v] * noise[u,v]) / sqrt(sum(w[a,b,u,v]^2))
```

Sum only over the finite input grid. There is no wrapping, reflection, padding, or kernel truncation. At zero length scale return a copy of `noise`.

Use separability to avoid constructing a full cell-pair matrix:

```text
A[a,u] = exp(-0.5 * ((a-u) / length_scale)^2)
B[b,v] = exp(-0.5 * ((b-v) / length_scale)^2)
Normalize each row of A and B by its Euclidean norm.
Z = A @ noise @ B.T
```

Time is O(rows × columns × (rows + columns)); storage is O(rows² + columns² + rows × columns). For extreme positive length scales, handle arithmetic limits deliberately and reject nonfinite results.

The normalization gives unit marginal variance when the input is independent standard Gaussian noise. It does not force a particular realized field to have sample mean zero or sample variance one. Do not rescale individual realizations or normalize the kernel by its sum.

## 5. `lorenz_shares`

```python
def lorenz_shares(curve: Callable[[float], float], count: int) -> FloatArray:
    ...
```

Require a positive integer count. Evaluate the callable at `i / count` for `i = 0, ..., count`; scalar callables such as the existing `PowerLorenz` remain supported. Vectorized callable support is optional, not a prerequisite.

```text
shares[i] = L((i+1)/count) - L(i/count)
```

Validate sampled values: finite, within `[0, 1]`, endpoints zero and one, nondecreasing values, and nondecreasing adjacent increments (sampled convexity). These checks do not prove convexity between sampling points.

Within the shared tolerance, snap endpoints to their specified values, clip tiny negative increments to zero, and normalize the resulting shares. Return shape `(count,)`, nonnegative shares summing to one within floating precision, in low-to-high resource-rank order. Reject larger discrepancies instead of silently repairing the curve.

This function is deterministic. It defines resource shares; it does not randomly draw incomes. Use separate calls for income and ownership curves along the same person ranking.

## 6. `allocate_counts`

```python
def allocate_counts(
    shares: FloatArray,
    total: int,
    rng: np.random.Generator,
) -> IntArray:
    ...
```

Input shares must be a nonempty one-dimensional finite nonnegative vector summing to one within tolerance. Normalize accepted floating drift. Require a nonnegative integer total supported by the output dtype and safe numerical allocation range. For this float-based routine, cap total at `2**53 - 1`; money allocation remains separate.

Algorithm:

1. Compute `targets = total * shares`.
2. Round each target half upward using `floor(target + 0.5)`, with boundary handling that avoids rounding overflow at the supported maximum. Do not use NumPy's default ties-to-even rounding.
3. If counts sum below total, increment an entry with the largest `target - count`.
4. If counts sum above total, decrement a positive entry with the largest `count - target`.
5. Recompute residuals after every correction and continue until the sum equals total.
6. Break residual ties within tolerance uniformly with `rng.choice` over eligible indices.

Use an overflow-safe sum when determining the correction. Output shape matches shares; all values are nonnegative integers and their sum is exactly total. At total zero, return zeros without drawing randomness.

This is quota allocation with random tie-breaking, not multinomial sampling. A multinomial would introduce additional ownership inequality absent from the report's construction.

## 7. `price_field`

```python
def price_field(
    shape: tuple[int, int],
    *,
    reference_price: float,
    spread: float,
    length_scale: float,
    rng: np.random.Generator,
) -> FloatArray:
    ...
```

Require positive integer dimensions, positive reference price, and nonnegative spread and length scale.

```python
noise = rng.normal(loc=0.0, scale=1.0, size=shape)
smoothed = smooth_field(noise, length_scale)
prices = reference_price * np.exp(spread * smoothed)
```

Return positive finite unrounded prices with the requested shape. Reject overflow, underflow to zero, and nonfinite results with an explanatory `ValueError`. Do not silently cap unusually expensive homes.

At zero spread, output exactly the reference price in every cell. Still draw the noise matrix so changing spread alone preserves the generator consumption convention. Reference price is the marginal median across seeds, not a required board-wide mean.

At the factory boundary, convert each value with `Decimal(str(value))`, round half upward to cents, and retain the existing minimum initial price of one cent. Use those stored prices for placement so price ties correspond to the actual domain values.

### Reusing smoothing for hidden risk

Use the independent `risk` generator to draw a Gaussian matrix once per episode. Apply `smooth_field` with `risk_length_scale`, then transform to weights with `exp(risk_contrast * smoothed)`.

Require finite nonnegative contrast. At contrast zero, weights are uniform. This composition may be a small private helper; it must reuse `smooth_field` rather than duplicate smoothing code. Reject nonfinite or zero generated weights rather than silently flattening the risk map.

## 8. `anchor_probabilities`

```python
def anchor_probabilities(
    weights: FloatArray,
    footprint: tuple[int, int],
) -> FloatArray:
    ...
```

Require a nonempty two-dimensional finite strictly positive weight matrix with grid shape `(rows, columns)`. Footprint dimensions `(height, width)` must be positive integers and fit within the grid.

Valid anchors are upper-left corners where the whole footprint fits. Define:

```text
anchor_shape = (rows - height + 1, columns - width + 1)
eligible = weights[:anchor_shape[0], :anchor_shape[1]]
probabilities = eligible / sum(eligible)
```

Use max-scaling before summation to avoid overflow during normalization. If numerical range causes an intended positive probability to become zero, reject the parameters rather than silently discard locations.

Return a two-dimensional probability matrix with `anchor_shape`. Keeping this shape makes coordinate interpretation explicit. Weights at invalid anchors are excluded from normalization. Weight belongs to the anchor itself; do not sum or average weights over its footprint.

This function is deterministic. It does not sample an event and does not return per-home damage probabilities. A home's exposure depends on all anchors whose footprints overlap that home.

## 9. `match_residences`

```python
def match_residences(
    incomes: FloatArray,
    prices: FloatArray,
    *,
    noise: float,
    rng: np.random.Generator,
) -> IntArray:
    ...
```

Require nonempty one-dimensional vectors of equal length, finite nonnegative incomes, finite positive prices, and finite nonnegative noise strength. Here `noise` means the scalar placement parameter tau, not a supplied noise matrix.

For each person `i`, calculate the shared midrank percentile of their income group:

```text
r[i] = (number with lower income + 0.5 * number with equal income) / N
z = rng.normal(size=N)
score = r + noise * z
```

Sort people by score and homes by price, ascending. Break exact score and price ties using seeded random permutations as secondary ranks; this provides unique tie keys without favoring input IDs. Assign the lowest-ranked person to the lowest-ranked home, and so on.

Return `residents[home_index] = person_index`, shape `(N,)`, containing every index from zero through `N-1` once. For factory grids, flatten home prices in row-major order before calling.

At zero noise, placement respects income ordering with random ordering within ties. Draw the same normal-vector and tie-permutation shapes even at zero noise. Larger noise weakens sorting but is not itself a correlation coefficient.

Income equality must follow the cent-rounded domain amounts. At the adapter boundary, verify float conversion preserves ordering and equality groups; reject unsupported magnitudes rather than merge distinct monetary values through conversion.

An exactly income-independent baseline uses `rng.permutation(N)` directly and is selected explicitly by the factory. Do not approximate it with an arbitrarily large noise parameter.

## 10. `sample_disasters`

```python
def sample_disasters(
    rate: float,
    probabilities: FloatArray,
    rng: np.random.Generator,
    *,
    location_rng: np.random.Generator,
) -> IntArray:
    ...
```

The extra explicit `location_rng` keeps count and location randomness independent. `rng` is the count generator. Require finite nonnegative rate and a nonempty two-dimensional finite nonnegative probability matrix summing to one within tolerance. Normalize accepted floating drift. The anchor builder produces strictly positive entries; the sampler also accepts intentional zero-probability locations.

```python
event_count = rng.poisson(rate)
flat_indices = location_rng.choice(
    probabilities.size,
    size=event_count,
    replace=True,
    p=probabilities.ravel(order="C"),
)
```

Convert indices back to `(row, column)` using the probability matrix shape. Return an integer array of shape `(event_count, 2)` in draw order. At rate zero, return shape `(0, 2)` without consuming either generator. A sampled zero count consumes no location randomness.

Sampling is with replacement: repeated anchors and overlapping footprints are expected. Never deduplicate or sort events. Rate is expected events per period, not event probability or an annual rate.

Reject rates beyond NumPy's supported Poisson range with a clear error. Do not clip rates or event counts, because that changes the specified distribution. Practical experiment-size limits belong in configuration validation.

The returned array contains anchor coordinates only. `DisasterConfig.footprints` expands each anchor into its rectangle. `Environment.step` continues to apply damage and settle claims after each event, preserving pre-loss records and excluding repeated building losses.

## 11. Composition example

This is illustrative future code, not an existing API:

```python
shape = (16, 16)
footprint = (3, 3)
seed = 42

prices = price_field(
    shape,
    reference_price=250_000.0,
    spread=0.4,
    length_scale=2.0,
    rng=numpy_stream(seed, "prices"),
)

income_shares = lorenz_shares(PowerLorenz(2), count=256)
ownership_shares = lorenz_shares(PowerLorenz(3), count=256)
home_counts = allocate_counts(
    ownership_shares, total=256,
    rng=numpy_stream(seed, "ownership-counts"),
)
# Factory: allocate annual income exactly in cents; convert stored incomes
# and prices for placement; assign residences, then titles using home_counts.

risk_noise = numpy_stream(seed, "risk").normal(size=shape)
risk_weights = np.exp(1.0 * smooth_field(risk_noise, length_scale=2.0))
probabilities = anchor_probabilities(risk_weights, footprint)

# Per-period execution; keep probabilities fixed during this episode.
period = 1
anchors = sample_disasters(
    rate=0.5,
    probabilities=probabilities,
    rng=numpy_stream(seed, f"disaster-counts:{period}"),
    location_rng=numpy_stream(seed, f"disaster-locations:{period}"),
)
for row, column in anchors:
    # Expand footprint, destroy intact homes, settle claims, record event.
    pass
```

Normal, Poisson, choice, permutation, exponential, and matrix multiplication are NumPy capabilities. We implement the functions that combine them according to the report.

## 12. Integration and compatibility

1. Add NumPy as a runtime dependency compatible with the project's Python version and update the lockfile during implementation. No SciPy dependency is required for the specified finite-grid operator.
2. Add the NumPy stream helper and extract `smooth_field`. Implement the new numerical contracts before migrating callers.
3. Migrate `GridPopulationFactory` to the new price, share, count, and placement functions. Change the existing `lorenz_shares(count, curve)` signature to the specified `(curve, count)` at all call sites and tests in the same change.
4. Preserve exact income budgets. Adapt the existing Decimal money allocator to consume shares by converting through decimal strings and normalizing in Decimal arithmetic, then perform residual correction in integer cents. Do not use float summation to settle cash. Separate this adapter from `allocate_counts`.
5. Preserve a common income ranking for ownership targets, including seeded income ties. Give each positive-quota person their assigned residence, then shuffle residual owner-capacity slots with the independent ownership-title generator. Each title must have exactly one owner and realized counts must equal quotas.
6. Initialize hidden risk once and store its probability matrix privately in the environment/disaster configuration. Keep it independent of price and placement streams. Prevent mutation through caller-owned arrays by copying and making retained configuration arrays read-only.
7. Replace uniform anchor draws with `sample_disasters`; zero risk contrast recovers uniform valid-anchor sampling. Use period-specific generators to preserve failed-step retry behavior.
8. Keep risk weights and probabilities out of household and insurer observations. Existing returned event footprints remain public data; persistent public history is a subsequent integration task.
9. Remove or delegate superseded `gaussian_price_field` and `poisson_count` implementations after migrating references. Retain existing Python `Random` helpers only where still used by the legacy population factory; do not silently change their return type.

No change to income/rent timing, insurance terms, or damage rules is part of this refactor. Tests that encode the current timing continue to apply until the separate payment-lifecycle implementation.

## 13. Acceptance criteria

Tests must establish the mathematical contracts and integration invariants:

- Smoothing agrees with the direct full-weight equation on a small nonsquare grid, including edges; zero length returns an independent copy; a one-cell grid preserves its noise value.
- The smoothing operator's coefficient squared sums equal one at every location. This verifies marginal variance without fragile single-field sample-variance assertions.
- Linear and power Lorenz curves produce expected shares; invalid endpoints, monotonicity, and sampled convexity are rejected.
- Count allocation covers half-up cases, corrections in both directions, seeded residual ties, zero total, and exact conservation.
- Price generation gives uniform prices at zero spread, positive finite values otherwise, and reproducible outputs. Invalid/extreme parameters fail clearly.
- Anchor probabilities normalize over eligible anchors only; uniform weights give uniform anchors; a full-grid footprint yields a `(1, 1)` matrix containing one.
- Placement is a permutation, preserves income/price inputs, respects zero-noise ordering, handles equal incomes without ID bias, and follows its documented mapping direction.
- Poisson zero-rate and weighted one-location cases behave exactly. Multi-draw checks of event-count mean/variance and location frequencies use seeded samples and statistically justified tolerances.
- Repeated anchors survive sampling and still produce only one building loss per home in integration tests.
- Changing placement settings does not alter prices, risk probabilities, or ownership quotas. Changing risk contrast does not alter count draws for a fixed period/rate.
- Failed simulation steps retry the same event draws and preserve cash, homes, contracts, and period state.
- Total income in cents, home count, ownership quotas, initial one-resident-per-home allocation, and insurance cash conservation remain valid after migration.

Run the existing test suite and new numerical/integration tests, then the repository's Ruff and mypy checks. Record the NumPy version used for reproducibility. Completion means the simulation uses these functions, not just that standalone helpers exist.
