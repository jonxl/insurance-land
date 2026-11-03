"""Research-only initialization fields; these are never passed to agent observations."""

from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from experiments.worlds import WorldSpec


def diagnostic_fields(spec: WorldSpec) -> dict[str, Any]:
    config = spec.population()
    disaster = spec.disasters()
    exposure = disaster.hit_probabilities((spec.rows, spec.columns), seed=spec.seed)
    percentiles = np.linspace(0, 1, 101)
    return {
        "hit_probability_per_event": exposure.tolist(),
        "income_lorenz": [config.income_curve(float(p)) for p in percentiles],
        "ownership_lorenz": [config.ownership_curve(float(p)) for p in percentiles],
        "settings": {
            "reference_price": str(config.reference_price),
            "price_spread": config.price_spread,
            "price_length_scale": config.length_scale,
            "home_price_spread": config.home_price_spread,
            "placement_noise": config.placement_noise,
            "risk_contrast": disaster.risk_contrast,
            "risk_length_scale": disaster.risk_length_scale,
            "homes_per_region": config.homes_per_region,
            "region_size_contrast": config.region_size_contrast,
            "region_size_length_scale": config.region_size_length_scale,
            "radius_mean": disaster.radius.mean,
            "radius_dispersion": disaster.radius.dispersion,
        },
        "policy": "Fixed baseline policies; no Q-learning training or rewards recorded.",
    }
