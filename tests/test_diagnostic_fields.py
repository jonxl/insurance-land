import numpy as np
import pytest

from experiments.diagnostic_fields import diagnostic_fields
from experiments.recording import WorldRecorder
from experiments.worlds import WorldSpec


def test_compact_fields_preserve_exact_disaster_exposure() -> None:
    spec = WorldSpec(rows=4, columns=5, periods=2)
    fields = diagnostic_fields(spec)
    assert not {"price_noise", "risk_noise", "anchor_probabilities"} & fields.keys()
    anchors = spec.disasters().risk_probabilities((4, 5), seed=spec.seed)
    exposure = np.array(fields["hit_probability_per_event"])
    assert anchors.shape == (2, 3)
    assert anchors.sum() == pytest.approx(1)
    assert exposure.sum() == pytest.approx(9)  # Every event hits exactly nine cells.
    assert exposure[0, 0] == anchors[0, 0]
    assert exposure[1, 2] == pytest.approx(1)  # All valid footprints include this cell.
    assert fields == diagnostic_fields(spec)
    assert fields["ownership_lorenz"][-1] == fields["income_lorenz"][-1] == 1


def test_matched_worlds_share_risk_and_initial_distribution_targets() -> None:
    standard = diagnostic_fields(WorldSpec(name="Standard"))
    chaos = diagnostic_fields(WorldSpec(name="Chaos"))
    peace = diagnostic_fields(WorldSpec(name="Peace"))
    assert standard == chaos
    assert standard["hit_probability_per_event"] == peace["hit_probability_per_event"]
    assert peace["income_lorenz"][50] == 0.5
    assert standard["income_lorenz"][50] == 0.25


def test_actions_are_recorded_from_actual_step_results() -> None:
    recorder = WorldRecorder(WorldSpec(rows=3, columns=3, periods=2).create())
    assert recorder.frames[0]["actions"] == []
    result = recorder.step()
    assert recorder.frames[1]["actions"] == [
        {"person": a.person_id, "action": type(a.action).__name__, "paid": a.paid}
        for a in result.actions
    ]
