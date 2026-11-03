import numpy as np
import pytest

from domain.disasters import DisasterConfig
from experiments.diagnostic_fields import diagnostic_fields
from experiments.recording import WorldRecorder
from experiments.worlds import WorldSpec
from utils.distributions import TweedieRadius, numpy_stream


def test_compact_fields_preserve_exact_disaster_exposure() -> None:
    spec = WorldSpec(rows=4, columns=5, periods=2)
    fields = diagnostic_fields(spec)
    assert not {"price_noise", "risk_noise", "anchor_probabilities"} & fields.keys()
    centers = spec.disasters().risk_probabilities((4, 5), seed=spec.seed)
    exposure = np.array(fields["hit_probability_per_event"])
    assert centers.shape == (4, 5)
    assert centers.sum() == pytest.approx(1)
    assert np.all(exposure >= centers)  # A cell is struck whenever it is the center.
    assert np.all(exposure <= 1)
    assert fields == diagnostic_fields(spec)
    assert fields["ownership_lorenz"][-1] == fields["income_lorenz"][-1] == 1


def test_radius_odds_follow_the_tweedie_tail() -> None:
    radius = TweedieRadius()
    reach = radius.reach(8)
    expected = -np.diff(reach)
    radii = radius.sample(400_000, numpy_stream(7, "radius-check"))
    observed = np.bincount(radii, minlength=7)[:7] / radii.size
    np.testing.assert_allclose(observed, expected, atol=0.002)
    assert expected[0] == pytest.approx(0.908, abs=1e-3)
    assert expected[1] == pytest.approx(0.077, abs=1e-3)
    assert expected[2] == pytest.approx(0.013, abs=1e-3)
    assert reach[3] == pytest.approx(1 / 448, rel=0.01)


def test_tweedie_parameters_set_mean_variance_and_large_zone_odds() -> None:
    radius = TweedieRadius(mean=0.3, dispersion=1.5)
    jumps = numpy_stream(7, "tweedie-check").poisson(radius.jump_rate, 400_000)
    values = numpy_stream(8, "tweedie-check").gamma(jumps, radius.jump_mean)
    assert values.mean() == pytest.approx(0.3, abs=0.005)
    assert values.var() == pytest.approx(1.5 * 0.3**1.5, abs=0.01)
    assert TweedieRadius(dispersion=1).reach(4)[3] < radius.reach(4)[3]
    for bad in ({"mean": 0}, {"dispersion": -1}, {"mean": float("nan")}):
        with pytest.raises(ValueError, match="finite and positive"):
            TweedieRadius(**bad)


def test_zones_are_centered_squares_clipped_at_the_grid_edge() -> None:
    disaster = DisasterConfig(rate=4, radius=TweedieRadius(dispersion=3), risk_contrast=1)
    seen_sizes = set()
    for period in range(1, 400):
        for cells in disaster.footprints((6, 6), seed=3, period=period):
            rows = {a for a, _ in cells}
            columns = {b for _, b in cells}
            assert len(cells) == len(rows) * len(columns)  # A filled rectangle, no gaps.
            assert all(0 <= a < 6 and 0 <= b < 6 for a, b in cells)  # Clipped, not wrapped.
            seen_sizes.add(len(cells))
    assert 1 in seen_sizes and max(seen_sizes) > 9
    with pytest.raises(ValueError, match="replace"):
        DisasterConfig(radius=TweedieRadius(), footprint_rows=2)


def test_hit_probabilities_match_simulated_events() -> None:
    disaster = DisasterConfig(rate=1, radius=TweedieRadius(), risk_contrast=1)
    shape = (6, 7)
    exact = disaster.hit_probabilities(shape, seed=11)
    centers = disaster.risk_probabilities(shape, seed=11)
    hits, events = np.zeros(shape), 0
    for period in range(1, 40_001):
        for cells in disaster.footprints(shape, seed=11, period=period, probabilities=centers):
            events += 1
            for cell in cells:
                hits[cell] += 1
    np.testing.assert_allclose(hits / events, exact, atol=0.012)
    fixed = DisasterConfig(footprint_rows=2, footprint_columns=3, risk_contrast=1)
    anchors = fixed.risk_probabilities((4, 5), seed=11)
    assert fixed.hit_probabilities((4, 5), seed=11).sum() == pytest.approx(6)
    assert fixed.hit_probabilities((4, 5), seed=11)[0, 0] == anchors[0, 0]


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
