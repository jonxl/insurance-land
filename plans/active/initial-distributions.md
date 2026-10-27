# Initial distributions and environment setup

Status: agreed modeling direction and discussion spec. This describes a proposed environment, not implemented simulation behavior. Numerical parameter choices and open rules are identified below.

## Purpose and agents

The environment connects a housing market and an insurance market. People and insurance firms are RL agents; learning algorithms and rewards will be discussed separately.

- A person can be a renter, owner-occupier, landlord, or a combination as their circumstances change. These are not permanently separate agent types.
- Homes are assets with locations, values, owners, and optional residents. Policies are contracts offered by insurer agents.
- A person occupies at most one home and may own multiple homes. Each home has one owner and at most one resident.
- External income is fixed per person after initialization. There are no simulated jobs, employers, or work schedules.
- Total cash is not fixed over time: external income enters the environment each period.

## 1. Global seed: reproducibility

- Configure one global seed for the environment.
- Derive component random streams for prices, residence placement, ownership assignment, and disasters from that seed using stable component labels.
- The same seed, settings, and generation algorithm reproduce the initial board and exogenous disaster draws. Reproducing the full trajectory also requires the same agent decisions and any learning-related randomness.
- Separate component streams prevent a change in placement from accidentally changing the price map or disaster sequence.
- Lorenz-derived income amounts can be deterministic; not every initialization component requires random draws.

## 2. Home prices: seeded Gaussian spatial noise

- Place homes on a fixed grid. Realistic streets, building appearance, and architectural details are unnecessary.
- Generate seeded Gaussian noise, smoothing it to create expensive and inexpensive neighborhoods.
- Convert the field into positive initial home values.
- Configure the general price level, price variation, and neighborhood size.
- Generate these values once. They do not permanently dictate future asking or transaction prices.
- Drop the previously discussed center-outward and coastal patterns.

Independent white Gaussian noise alone gives unrelated values at neighboring cells. Smoothing is what produces spatial neighborhoods.

### Candidate mathematical construction

The Gaussian field direction is agreed; this particular function is a concrete proposal rather than finalized implementation.

    epsilon[u] ~ Normal(0, 1)
    weight(x, u) = exp(-distance(x, u)^2 / (2 × length_scale^2))
    field[x] = sum_u(weight(x, u) × epsilon[u]) / sqrt(sum_u(weight(x, u)^2))
    initial_price[x] = reference_price × exp(price_spread × field[x])

- Sum over the finite grid, without wrapping boundaries.
- A positive length_scale controls neighborhood size. A zero-length-scale mode can explicitly use field = epsilon.
- The normalization gives unit marginal variance at each cell across seeds. Shared noise contributions correlate nearby cells.
- reference_price is positive and is the marginal median across seeds, not an exact board-wide mean.
- price_spread is nonnegative. Zero gives uniform prices.
- The exponential keeps prices positive; this candidate does not impose an upper bound.

Initial market value, sale price, rent, and insured/rebuilding value are separate concepts. Their relationships remain to be specified. Location stays with the home regardless of where its owner lives.

## 3. Personal income: Lorenz curve

- Set population size and average annual external income.
- Use an income Lorenz curve to divide total annual income among people.
- Assign each person their income once, keep it fixed, and credit the corresponding amount each simulation period.
- Do not redraw incomes each period and do not model jobs.
- Treat starting cash separately from annual income.

Average annual income sets the dollar scale; the Lorenz curve sets inequality. For example, 100 people with average annual income 30,000 collectively receive 3,000,000 annually, divided according to the curve.

A candidate deterministic construction for people ranked from lowest to highest income is:

    income[i] = N × mean_income × (L_income(i / N) - L_income((i - 1) / N))

For a period of dt years, credit income[i] × dt. This preserves total annual income N × mean_income before monetary rounding. The curve must be a valid income Lorenz curve; monetary precision and rounding remain open.

Rental income is additional and arises from actual tenant-to-owner payments. Income rank does not mean total wealth rank: cash and property wealth are distinct.

## 4. Residence placement: income rank plus random noise

- Rank people by external income and homes by initial price.
- Add seeded noise to people's placement scores.
- Sort by those scores and match people to homes in price order.
- Higher-income people tend to occupy higher-priced homes, with randomness controlling how close that association is.
- Assign each residence at most once. This initializes occupancy, not purchases or ownership.

Candidate score:

    residence_score[i] = income_percentile[i] + placement_noise × Normal(0, 1)

- Income percentiles lie between zero and one; equal incomes receive equal percentiles.
- Zero placement_noise gives income-ordered placement; seed-based tie handling avoids dependence on person IDs.
- Increasing noise weakens the relationship. Exactly income-independent placement can use a random permutation.
- The noise parameter is not itself a correlation coefficient.
- The income amounts and home values remain unchanged by placement.

The simplest baseline has equal numbers of people and homes and houses everyone. Surplus-home selection and housing-shortage allocation require additional rules and remain open.

## 5. Home ownership: a second Lorenz curve

- Use the same ordering of people as the income distribution, with consistent seeded ordering for income ties.
- Apply a separate ownership Lorenz curve to allocate shares of home counts along that ordering.
- Higher-income people therefore receive larger intended portfolios. The ownership curve may be more concentrated than the income curve.
- Convert fractional shares into whole-home counts while preserving the exact number of homes.
- Give everyone with a positive home count ownership of their assigned residence first.
- Allocate the remaining homes to owners with remaining portfolio capacity, using seeded assignment.
- People with zero homes rent their assigned residence from its owner. Owners with additional occupied homes are landlords.

Candidate fractional targets:

    target_home_count[i] = H × (L_ownership(i / N) - L_ownership((i - 1) / N))

The ownership curve is over the whole population, including nonowners. A flat initial segment can represent zero ownership among lower ranks. Round each target to the nearest integer, with halves rounded upward. If the total is below H, add one to the count with the largest target-minus-count difference. If it exceeds H, subtract one from a positive count with the largest count-minus-target difference. Recompute differences after each correction and repeat until the total is H, breaking ties using the seed. This preserves nonnegative whole-home counts. The realized finite-population curve may approximate rather than exactly match its target.

This construction assumes the baseline of one occupied residence per person and H = N. Each positive-count owner receives their residence, and remaining capacity exactly covers homes occupied by nonowners. Generalizing to vacancies or unhoused people needs an explicit extension.

Ownership counts and property wealth are not interchangeable:

    property_wealth[i] = sum(initial_price[home] for homes owned by person i)

Someone with more homes need not have more property wealth than every person with fewer homes. Residence and ownership remain distinct relationships, even though the initialization gives owners their residences first.

Initial rents, ownership-assignment details beyond capacity, and initial cash are still unresolved. Income-dependent placement is not an affordability check.

## 6. Insurance firms: configured conditions and opening round

- Create a configurable number of insurer RL agents, for example firms A, B, and C.
- Assign starting capital; its amount and whether it is equal across firms remain open.
- Each firm can offer homeowners, landlord, and renters insurance products.
- Let firms post initial prices, then let people select appropriate coverage.
- Activate contracts and settle premiums under a defined rule before disaster exposure begins.
- Insurance customer relationships emerge from this opening round rather than being randomly assigned.

Fixing product coverage while allowing firms to choose prices is a proposed simplification, not a finalized contract design. Optional versus mandatory coverage, affordability, renewals, deductibles, limits, covered hazards, and insolvency remain open.

One home can connect an owner's policy and a renter's policy covering different losses. Neither party automatically receives the full home value in a claim.

## 7. Natural disasters: Poisson frequency and fixed footprint

- Each period, draw the event count from Poisson(lambda).
- lambda is expected disasters per period, not the probability of a disaster.
- Each event selects a random grid location and applies the same fixed-size footprint.
- There is no separately randomized event size or damage severity in this setup.
- Set affected homes' modeled values to zero, mark them uninhabitable, and remove their occupancy relationships, displacing residents.
- Apply insurance contracts to resulting covered losses.

The event-count probability is:

    P(K = k) = lambda^k × exp(-lambda) / k!
    P(K >= 1) = 1 - exp(-lambda)

At lambda = 0, the count is always zero. Counts can exceed one. Increasing lambda produces more events on average, not larger events. If a rate is instead expressed per year, multiply by the period length in years before drawing the count. lambda can be configured or changed between periods; the current value controls the next draw.

Event centers can be sampled uniformly from eligible grid positions as a simple baseline. Footprint shape, size, and boundary handling still need a precise choice. Clipping at an edge can affect fewer homes; exact equal-size footprints require restricting centers or another explicit boundary rule. Event footprints may overlap.

Retain home identities, locations, ownership, and pre-loss valuations for loss accounting. Destruction does not remove people from the population or necessarily remove title. Already-destroyed homes do not generate duplicate building losses unless restored and subsequently damaged again.

Zeroing the whole modeled value is an intentional simplification. A future model could distinguish surviving land value from destroyed structures. Replacement housing, rent cessation, repairs/rebuilding, and claims-payment timing require follow-up rules.

## Initialization and execution order

1. Set population size, grid/home count, insurer count, time unit, global seed, and distribution parameters.
2. Generate the spatial price field and homes.
3. Generate fixed personal incomes and assign starting cash under a rule still to be selected.
4. Assign residences using income-dependent randomized placement.
5. Allocate whole-home ownership counts using the same income ordering; assign titles and establish landlord–tenant relationships and initial rents.
6. Create insurers with starting capital.
7. Run the opening insurance offer and purchase round, then activate coverage and settle premiums.
8. Begin ordinary periods with external income, agent decisions, payments, and disaster events.

The exact ordering within an ordinary period, including first income credit, premiums, disasters, and claims, remains open. There is no disaster during board creation or before the opening insurance round completes.

## Experimental controls

- Change income inequality while holding mean income fixed.
- Change ownership concentration while preserving the number of homes.
- Change placement noise while preserving incomes and the price field.
- Change spatial price parameters while preserving other selected inputs.
- Change lambda while holding the initial board and footprint fixed.
- Compare insurer behavior across reproducible boards and multiple seeds.

## Remaining discussion decisions

- Concrete Lorenz curve families and parameter values for income and ownership.
- Income precision, starting cash, initial rents, and first income-credit timing.
- Gaussian field and placement function confirmation and parameters.
- Residual property-assignment method after whole-home rounding.
- Extensions for vacancies, shortages, and population growth.
- Insurance coverage rules, capital, purchase constraints, and claims settlement.
- Disaster footprint and boundary handling, post-disaster housing, and rebuilding.
- RL observations, action sets, objectives, and training.

## Current implementation boundary

The current code separates ownership from occupancy and credits income each step. Its factory assigns uniform income, cash, and home values and randomizes housing allocation and ownership. It currently executes rent payments, not the proposed property-trading, insurance, spatial-price, ownership-curve, or disaster mechanisms. This spec and the accompanying preliminary report are discussion artifacts only.
