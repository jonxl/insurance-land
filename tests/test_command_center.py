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
    run_experiment(spec, tmp_path, title="My chaos world")
    bundle = json.loads((tmp_path / "assets/world-history.json").read_text())
    assert bundle["default"] == "Chaos"
    assert bundle["title"] == "My chaos world"
    assert list(bundle["worlds"]) == ["Chaos"]
    data = bundle["worlds"]["Chaos"]
    assert data["configuration"]["seed"] == 7
    assert len(data["frames"]) == 3
    assert data["rates"] == list(spec.rates())
    html = (tmp_path / "diagnostics.html").read_text()
    assert "__WORLD_DATA__" not in html
    assert "Create experiment" in html


def test_run_reports_real_progress(tmp_path):
    progress = []
    spec = WorldSpec(rows=3, columns=3, periods=3)
    run_experiment(spec, tmp_path, lambda period, stage: progress.append((period, stage)))
    assert progress == [
        (1, "Simulating"), (2, "Simulating"), (3, "Simulating"),
        (3, "Preparing snapshots"),
    ]


def test_library_saves_reopens_and_imports_existing_runs(tmp_path):
    from experiments.command_center import RunLibrary

    spec = WorldSpec(rows=3, columns=3, periods=2)
    run_experiment(spec, tmp_path / "runs" / "legacy")
    library = RunLibrary(tmp_path)
    saved = library.get("legacy")
    assert saved["state"] == "complete"
    assert saved["configuration"]["rate"] == 0.1
    assert saved["url"] == "/runs/legacy/diagnostics.html?view=map"
    assert RunLibrary(tmp_path).list() == library.list()


def test_library_queues_progress_and_keeps_failures(tmp_path, monkeypatch):
    from threading import Event
    from time import monotonic, sleep

    from experiments import command_center

    entered, release = Event(), Event()

    def slow_run(spec, output, progress, *, title):
        progress(1, "Simulating")
        entered.set()
        assert release.wait(5)
        if spec.seed == 8:
            raise ValueError("Example simulation error")

    monkeypatch.setattr(command_center, "run_experiment", slow_run)
    library = command_center.RunLibrary(tmp_path)
    first = library.create(WorldSpec(periods=2), "My saved world")
    assert entered.wait(3)
    try:
        second = library.create(WorldSpec(periods=2, seed=8), "Another world")
        assert library.get(first["id"])["completed_periods"] == 1
        assert library.get(second["id"])["state"] == "queued"
        manifest = tmp_path / "runs" / first["id"] / "run.json"
        assert json.loads(manifest.read_text())["title"] == "My saved world"
    finally:
        release.set()
    deadline = monotonic() + 3
    while any(j["state"] in ("queued", "running") for j in library.list()):
        assert monotonic() < deadline
        sleep(0.01)
    assert library.get(first["id"])["state"] == "complete"
    assert library.get(second["id"])["error"] == "Example simulation error"
    assert command_center.RunLibrary(tmp_path).list() == library.list()


def test_restart_marks_interrupted_worlds_failed(tmp_path):
    from experiments.command_center import RunLibrary

    directory = tmp_path / "runs" / "interrupted"
    directory.mkdir(parents=True)
    (directory / "run.json").write_text(json.dumps({
        "id": "interrupted", "title": "Interrupted experiment",
        "state": "running", "created_at": "2026-11-03",
        "configuration": {"periods": 5}, "completed_periods": 2,
    }))
    job = RunLibrary(tmp_path).get("interrupted")
    assert job["state"] == "failed"
    assert "server stopped" in job["error"]
    assert job["completed_periods"] == 2


def test_run_api_accepts_titles_and_lists_saved_worlds(tmp_path, monkeypatch):
    from io import BytesIO

    from experiments import command_center

    created = []

    def create(self, spec, title):
        created.append((spec, title))
        return {"id": "new", "title": title, "state": "queued"}

    monkeypatch.setattr(command_center.RunLibrary, "create", create)
    handler_type = command_center.make_handler(tmp_path)
    handler = handler_type.__new__(handler_type)
    replies = []
    handler.reply = lambda status, body: replies.append((status, body))
    handler.path = "/api/runs"

    def post(values):
        body = json.dumps(values).encode()
        handler.rfile = BytesIO(body)
        handler.headers = {"Content-Type": "application/json", "Content-Length": str(len(body))}
        handler.do_POST()

    post({"title": "  Low risk  ", "periods": 2})
    assert replies[-1] == (202, {"id": "new", "title": "Low risk", "state": "queued"})
    assert created[0][0].rate == 0.1
    post({"title": 123})
    assert replies[-1][0] == 400
    post({"title": "x" * 81})
    assert replies[-1][0] == 400
    handler.do_GET()
    assert replies[-1] == (200, {"runs": []})
