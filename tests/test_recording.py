import json
from decimal import Decimal
from pathlib import Path

import pytest

from experiments.recording import WorldRecorder
from experiments.standard import StandardWorld


def test_recorded_transfers_reconcile_every_balance_and_preserve_history(tmp_path: Path) -> None:
    world = StandardWorld(rows=4, columns=4, periods=3, rate=20).create()
    recorder = WorldRecorder(world)
    initial = json.dumps(recorder.frames[0], sort_keys=True)
    for _ in range(3):
        before = {i: p.cash for i, p in world.people.items()}
        capitals = {i: f.capital for i, f in world.insurers.items()}
        recorder.step()
        frame = recorder.frames[-1]
        for t in frame["transfers"]:
            amount = Decimal(t["amount"])
            if t["kind"] == "income":
                before[t["person"]] += amount
            elif t["kind"] == "rent":
                before[t["person"]] -= amount
                before[t["recipient"]] += amount
            elif t["kind"] == "claim":
                before[t["person"]] += amount
                capitals[t["firm"]] -= amount
        assert before == {i: p.cash for i, p in world.people.items()}
        assert capitals == {i: f.capital for i, f in world.insurers.items()}
    assert initial == json.dumps(recorder.frames[0], sort_keys=True)
    # Rent paid before destruction survives in the history.
    assert any(
        t["kind"] == "rent" and Decimal(t["amount"]) > 0 for t in recorder.frames[1]["transfers"]
    )
    assert recorder.frames[1]["events"]
    recorder.export(tmp_path)
    history = json.loads((tmp_path / "assets" / "world-history.json").read_text())
    assert len(history["frames"]) == 4
    assert "__WORLD_DATA__" not in (tmp_path / "diagnostics.html").read_text()
    assert history["frames"][0]["transfers"][0]["kind"] == "premium"


def test_recording_must_start_before_steps() -> None:
    world = StandardWorld(rows=3, columns=3).create()
    world.step()
    with pytest.raises(ValueError, match="period zero"):
        WorldRecorder(world)
