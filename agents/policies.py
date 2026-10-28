"""Small deterministic baselines that can be replaced by learned policies."""

from domain.insurance import CoverageChoice, InsuranceObservation, eligible_product


def cheapest_affordable_coverage(observation: InsuranceObservation) -> tuple[CoverageChoice, ...]:
    """Buy one eligible policy per home in ID order, within the upfront cash budget.

    This baseline compares premiums only; it does not optimize coverage quality.
    """
    cash = observation.person.cash
    choices = []
    for home in sorted(observation.homes, key=lambda h: h.id):
        product = eligible_product(observation.person.id, home)
        eligible = [o for o in observation.offers if o.product == product and o.premium <= cash]
        if eligible:
            offer = min(eligible, key=lambda o: (o.premium, o.id))
            choices.append(CoverageChoice(offer.id, home.id))
            cash -= offer.premium
    return tuple(choices)
