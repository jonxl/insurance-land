"""Research-only initialization fields; these are never passed to agent observations."""

from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from experiments.worlds import WorldSpec


def diagnostic_fields(spec: WorldSpec) -> dict[str, Any]:
    config = spec.population()
    disaster = spec.disasters()
    shape = (spec.rows, spec.columns)
    anchors = disaster.risk_probabilities(shape, seed=spec.seed)
    exposure = np.zeros(shape)
    for (row, column), probability in np.ndenumerate(anchors):
        exposure[
            row : row + disaster.footprint_rows, column : column + disaster.footprint_columns
        ] += probability
    percentiles = np.linspace(0, 1, 101)
    return {
        "hit_probability_per_event": exposure.tolist(),
        "income_lorenz": [config.income_curve(float(p)) for p in percentiles],
        "ownership_lorenz": [config.ownership_curve(float(p)) for p in percentiles],
        "settings": {
            "reference_price": str(config.reference_price),
            "price_spread": config.price_spread,
            "price_length_scale": config.length_scale,
            "placement_noise": config.placement_noise,
            "risk_contrast": disaster.risk_contrast,
            "risk_length_scale": disaster.risk_length_scale,
            "footprint": [disaster.footprint_rows, disaster.footprint_columns],
        },
        "policy": "Fixed baseline policies; no Q-learning training or rewards recorded.",
    }
