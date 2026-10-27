"""Runnable toy experiment; policies are deterministic baselines, not trained RL."""

from decimal import Decimal

from agents.house import HouseAgent
from agents.insurance import InsurancePlanAgent
from agents.policies import cheapest_affordable_coverage
from domain.disasters import DisasterConfig
from domain.insurance import Insurer, InsurerObservation, Offer, Product
from factories import EnvironmentFactory, GridPopulationConfig


def quote_products(observation: InsurerObservation) -> tuple[Offer, ...]:
    return tuple(
        Offer(
            id=observation.firm.id * 10 + index,
            insurer_id=observation.firm.id,
            product=product,
            premium=Decimal(100 + 25 * observation.firm.id),
            limit=Decimal("500000") if product != Product.RENTERS else Decimal("10000"),
            deductible=Decimal("100"),
            term_periods=12,
            contents_value=Decimal("10000") if product == Product.RENTERS else Decimal(0),
        )
        for index, product in enumerate(Product, 1)
    )


def main() -> None:
    firms = tuple(Insurer(i, name, Decimal("1000000")) for i, name in enumerate("ABC", 1))
    environment = EnvironmentFactory.create(
        GridPopulationConfig(rows=4, columns=4, seed=42),
        agent_factory=lambda _: HouseAgent(insurance_policy=cheapest_affordable_coverage),
        disasters=DisasterConfig(rate=1.0, footprint_rows=2, footprint_columns=2),
        insurers=firms,
        insurer_agents={firm.id: InsurancePlanAgent(quote_products) for firm in firms},
    )
    contracts = environment.open_insurance()
    print(
        f"Created {len(environment.people)} people, {len(environment.homes)} homes, "
        f"{len(firms)} insurers, and {len(contracts)} contracts."
    )
    for _ in range(3):
        result = environment.step()
        losses = sum(len(event.losses) for event in result.disasters)
        paid = sum((claim.paid for claim in result.claims), Decimal(0))
        print(
            f"Period {result.period}: {len(result.disasters)} disasters, "
            f"{losses} homes destroyed, {paid} claims paid."
        )


if __name__ == "__main__":
    main()
