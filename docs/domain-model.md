# Domain model

The economic records are defined in [domain/models.py](../domain/models.py), and state transitions are implemented by [HousingMarket](../domain/housing.py).

## People: `Entity`

`Entity` is the economic representation of a person. `Environment.people` maps person IDs to these records.

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | `int` | Person identifier |
| `cash` | `Decimal` | Available cash, defaulting to zero |
| `income` | `Decimal` | Income credited each simulation period, defaulting to zero |

Owner and tenant are roles established by home references. The same person can occupy one home and own other homes. A person's budget remains attached to their `Entity`, regardless of the roles they take.

## Single-person households: `Household`

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | `int` | Household identifier |
| `person_id` | `int` | The household's single person |

Every person in an environment belongs to exactly one household. The household connects that person to housing queries; cash and income belong to the person. Residence is derived from home occupancy.

For example, `Household(id=100, person_id=10)` belongs to person 10. Its residence is the home whose `occupant_id` is 10.

## Regions: `Region`

`Region` stores an integer `id` and a nonblank `name`. Every home in an environment references an existing region.

`environment.homes_in_region(region_id)` returns that region's homes. `environment.households_in_region(region_id)` returns households whose people occupy those homes. A person's investment properties do not determine their household's region; their residence does.

If a person has no residence, their observation has `residence=None` and `region=None`.

## Homes: `Home`

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | `int` | Home identifier |
| `region_id` | `int` | Region containing the home |
| `owner_id` | `int` | Person who owns the home |
| `market_value` | `Decimal` | Recorded asset value |
| `occupant_id` | `int \| None` | Resident, or `None` for vacancy |
| `rent` | `Decimal` | Amount due for one rent-payment action |

Ownership and occupancy are independent relationships:

| State | Relationship | Rent rule |
| --- | --- | --- |
| Owner occupied | `owner_id == occupant_id` | Rent must be zero |
| Tenant occupied | Owner and resident differ | Rent is finite and nonnegative |
| Vacant | `occupant_id is None` | Rent must be zero |

Each home has one owner. Each home has at most one resident, and each person resides in at most one home. A person may own zero, one, or several homes. The generated population can include homes without residents and people without a residence.

Constructing a home validates its money values and its local rent rule. Registering it with a market checks that the owner and any resident exist and that the resident does not already occupy another home.

## Money

Money fields use `Decimal`. Construct decimal values from strings:

```python
from decimal import Decimal

rent = Decimal("1000.25")
cash = Decimal("2500.00")
assert cash - rent == Decimal("1499.75")
```

The shared `validate_money(value, field=...)` helper rejects non-Decimal input, negative values, NaN, and infinity. Values retain their supplied decimal precision; calculations follow Python's active decimal context. Monetary units and period length should be consistent across a scenario.

## Housing operations

`HousingMarket` provides the following operations. These are domain APIs; the environment's action loop calls `pay_rent` and `accrue_income` during a step.

| Method | Effect |
| --- | --- |
| `add_entity(entity)` | Register a person; reject a duplicate ID |
| `add_home(home)` | Register a validated home and its relationships |
| `owned_homes(entity_id)` | Return a tuple of the person's owned homes |
| `residence(entity_id)` | Return the person's occupied home or `None` |
| `move_in(home_id, entity_id, rent=...)` | Move the person into a vacant home and clear their previous occupancy |
| `vacate(home_id)` | Clear the resident and rent while preserving the owner |
| `transfer_ownership(home_id, new_owner_id, rent=...)` | Replace the owner and rent while preserving the resident |
| `pay_rent(home_id)` | Settle one payment if funds are sufficient |
| `accrue_income()` | Add each person's income to their cash |
| `copy()` | Create an independently updateable market with shared immutable records |

### Moving

`move_in` validates the destination and replacement home before changing the previous residence. An occupied destination is rejected. On a successful move, the previous home's resident becomes `None` and its rent becomes zero. The owners of both homes remain unchanged.

### Transferring ownership

`transfer_ownership` requires an existing new owner and an explicit rent value. The caller selects rent appropriate to the resulting relationship. If the resident becomes the owner, rent must become zero. This operation changes title and rent; its effect on cash is zero.

### Paying rent

For a tenant with enough cash, settlement subtracts rent from the tenant and adds exactly that amount to the owner. The total cash held by the two people stays constant.

If cash is insufficient, settlement returns `False` and preserves both balances and occupancy. Vacant homes, owner-occupied homes, and zero-rent homes return `True` without transferring cash. A direct domain call settles one payment each time; the environment determines the period's action schedule.

## Standalone domain example

```python
from decimal import Decimal

from domain.housing import HousingMarket
from domain.models import Entity, Home

market = HousingMarket()
market.add_entity(Entity(id=1, cash=Decimal("500")))
market.add_entity(Entity(id=2, cash=Decimal("1200")))
market.add_home(Home(id=1, region_id=1, owner_id=1, market_value=Decimal("250000")))
market.move_in(1, 2, rent=Decimal("1000"))

assert market.pay_rent(1)
assert market.entities[1].cash == Decimal("1500")
assert market.entities[2].cash == Decimal("200")

market.transfer_ownership(1, 2, rent=Decimal("0"))
assert market.homes[1].owner_id == market.homes[1].occupant_id == 2
```

Region registration is part of environment assembly. A standalone `HousingMarket` operates on its people and homes without maintaining a region collection.
