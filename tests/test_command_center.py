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
