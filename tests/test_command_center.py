import json

import pytest

from experiments.command_center import parse_spec, run_experiment
from experiments.worlds import WorldSpec


@pytest.mark.parametrize(
    "values",
    [
        {"periods": 0},
        {"seed": True},
        {"rows": 33},
        {"rate": float("nan")},
        {"name": "unknown"},
        {"command": "anything"},
        {"rows": 32, "columns": 32, "periods": 500},
    ],
)
def test_invalid_run_settings(values):
    with pytest.raises(ValueError):
        parse_spec(values)


def test_homes_per_region_reaches_the_world_and_counts_toward_the_limit():
    spec = parse_spec({"rows": 3, "columns": 3, "homes_per_region": 2, "periods": 2})
    assert len(spec.create().homes) == 18
    with pytest.raises(ValueError, match="home-periods"):
        parse_spec({"rows": 32, "columns": 32, "homes_per_region": 16, "periods": 10})
    with pytest.raises(ValueError):
        parse_spec({"homes_per_region": 0})


def test_radius_settings_reach_the_disaster_config():
    radius = parse_spec({"radius_mean": 0.2, "radius_dispersion": 1}).disasters().radius
    assert (radius.mean, radius.dispersion) == (0.2, 1)
    with pytest.raises(ValueError, match="radius_dispersion"):
        parse_spec({"radius_dispersion": 0})


def test_run_exports_selected_world_and_settings(tmp_path):
    spec = WorldSpec(name="Chaos", rows=3, columns=3, periods=2, seed=7)
    run_experiment(spec, tmp_path)
    bundle = json.loads((tmp_path / "assets/world-history.json").read_text())
    assert bundle["default"] == "Chaos"
    assert list(bundle["worlds"]) == ["Chaos"]
    data = bundle["worlds"]["Chaos"]
    assert data["configuration"]["seed"] == 7
    assert len(data["frames"]) == 3
    assert data["rates"] == list(spec.rates())
    html = (tmp_path / "diagnostics.html").read_text()
    assert "__WORLD_DATA__" not in html
    assert "Start experiment" in html
