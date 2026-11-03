"""Generate all three worlds: uv run python -m experiments.generate_worlds."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from experiments.diagnostic_fields import diagnostic_fields
from experiments.recording import WorldRecorder
from experiments.viewer import export_viewer
from experiments.worlds import WorldSpec


def generate(
    output: Path, *, seed: int = 42, periods: int = 120, rows: int = 8, columns: int = 8
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    worlds = {}
    for name in ("Peace", "Standard", "Chaos"):
        spec = WorldSpec(name=name, seed=seed, periods=periods, rows=rows, columns=columns)
        recorder = WorldRecorder(spec.create())
        for rate in spec.rates():
            recorder.step(disaster_rate=rate)
        data = recorder.data()
        data["diagnostics"] = diagnostic_fields(spec)
        data["configuration"] = asdict(spec)
        data["rates"] = spec.rates()
        worlds[name] = data
        print(f'"{name}": {len(recorder.frames)} snapshots generated')
    bundle = {"worlds": worlds, "default": "Standard"}
    serialized = json.dumps(bundle, separators=(",", ":"))
    (output / "assets").mkdir(parents=True, exist_ok=True)
    (output / "assets" / "world-history.json").write_text(serialized + "\n")
    export_viewer(output)
    print(f"Diagnostics: {output / 'diagnostics.html'}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("studies/webui"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--periods", type=int, default=120)
    args = parser.parse_args()
    generate(args.output, seed=args.seed, periods=args.periods)
    from experiments.study_report import generate as generate_report

    generate_report(args.output)


if __name__ == "__main__":
    main()
