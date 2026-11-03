"""Local research command center: uv run python -m experiments.command_center."""

import argparse
import json
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from urllib.parse import urlsplit
from uuid import uuid4

from experiments.diagnostic_fields import diagnostic_fields
from experiments.recording import WorldRecorder
from experiments.viewer import VIEWER_ASSETS, VIEWER_TEMPLATE, export_viewer
from experiments.worlds import WorldSpec


def parse_spec(values: dict) -> WorldSpec:
    limits = {
        "seed": (0, 2**32 - 1),
        "periods": (1, 500),
        "rows": (3, 32),
        "columns": (3, 32),
        "homes_per_region": (1, 16),
    }
    decimals = (
        ("rate", 0, 10),
        ("chaos_rate_ratio", 1.001, 100),
        ("radius_mean", 0.01, 2),
        ("radius_dispersion", 0.1, 5),
    )
    if set(values) - {*limits, "name", *(key for key, _, _ in decimals)}:
        raise ValueError("Unknown experiment setting")
    for key, (low, high) in limits.items():
        value = values.get(key, getattr(WorldSpec(), key))
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{key} must be an integer from {low} to {high}")
    for key, low, high in decimals:
        value = values.get(key, getattr(WorldSpec(), key))
        if type(value) not in (int, float) or not low <= value <= high:
            raise ValueError(f"{key} must be between {low} and {high}")
    spec = WorldSpec(**values)
    if spec.rows * spec.columns * spec.homes_per_region * spec.periods > 128000:
        raise ValueError("Use fewer homes or periods (maximum 128,000 home-periods)")
    return spec


def run_experiment(
    spec: WorldSpec, output: Path, progress: Callable[[int, str], None] | None = None,
    *, title: str | None = None,
) -> None:
    recorder = WorldRecorder(spec.create())
    for period, rate in enumerate(spec.rates(), 1):
        recorder.step(disaster_rate=rate)
        if progress:
            progress(period, "Simulating")
    if progress:
        progress(spec.periods, "Preparing snapshots")
    data = recorder.data()
    data.update(configuration=asdict(spec), rates=spec.rates(), diagnostics=diagnostic_fields(spec))
    serialized = json.dumps({"worlds": {spec.name: data}, "default": spec.name, "title": title})
    (output / "assets").mkdir(parents=True, exist_ok=True)
    (output / "assets/world-history.json").write_text(serialized)
    export_viewer(output)


class RunLibrary:
    """Persist saved worlds and serialize simulation work in the background."""

    def __init__(self, root: Path):
        self.root = root
        self.lock = Lock()
        self.worker_lock = Lock()
        self.jobs: dict[str, dict] = {}
        for directory in sorted((root / "runs").glob("*")):
            if not directory.is_dir():
                continue
            manifest = directory / "run.json"
            try:
                if manifest.exists():
                    job = json.loads(manifest.read_text())
                else:
                    bundle = json.loads((directory / "assets/world-history.json").read_text())
                    config = bundle["worlds"][bundle["default"]]["configuration"]
                    job = {
                        "id": directory.name, "title": f'{config["name"]} experiment',
                        "configuration": config, "state": "complete",
                        "completed_periods": config["periods"],
                        "created_at": datetime.fromtimestamp(
                            directory.stat().st_mtime, UTC,
                        ).isoformat(),
                    }
                job["id"] = directory.name
                job["url"] = f"/runs/{directory.name}/diagnostics.html?view=map"
                if job["state"] in ("running", "queued"):
                    job.update(
                        state="failed", error="The server stopped before this experiment finished.",
                    )
                self.jobs[directory.name] = job
                self._save(job)
            except (OSError, ValueError, KeyError, TypeError):
                continue

    def _save(self, job: dict) -> None:
        directory = self.root / "runs" / job["id"]
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / "run.json.tmp"
        temporary.write_text(json.dumps(job))
        temporary.replace(directory / "run.json")

    def update(self, job_id: str, **changes) -> None:
        with self.lock:
            self.jobs[job_id].update(changes)
            self._save(self.jobs[job_id])

    def list(self) -> list[dict]:
        with self.lock:
            return sorted(
                (dict(job) for job in self.jobs.values()),
                key=lambda job: job["created_at"], reverse=True,
            )

    def get(self, job_id: str) -> dict | None:
        with self.lock:
            return dict(self.jobs[job_id]) if job_id in self.jobs else None

    def create(self, spec: WorldSpec, title: str) -> dict:
        job_id = uuid4().hex
        job = {
            "id": job_id, "title": title or f"{spec.name} experiment",
            "configuration": asdict(spec), "state": "queued", "completed_periods": 0,
            "stage": "Waiting to start", "created_at": datetime.now(UTC).isoformat(),
            "url": f"/runs/{job_id}/diagnostics.html?view=map",
        }
        with self.lock:
            self.jobs[job_id] = job
            self._save(job)
        Thread(target=self.execute, args=(job_id, spec), daemon=True).start()
        return dict(job)

    def execute(self, job_id: str, spec: WorldSpec) -> None:
        with self.worker_lock:
            try:
                self.update(job_id, state="running", stage="Creating experiment")
                run_experiment(
                    spec, self.root / "runs" / job_id,
                    lambda period, stage: self.update(
                        job_id, completed_periods=period, stage=stage,
                    ),
                    title=self.get(job_id)["title"],
                )
                self.update(job_id, state="complete", stage="Ready to explore")
            except Exception as error:
                self.update(job_id, state="failed", error=str(error))


def make_handler(root: Path) -> type[SimpleHTTPRequestHandler]:
    library = RunLibrary(root)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(root), **kwargs)

        def reply(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def browser_file(self, source: Path) -> None:
            content_type = {
                ".html": "text/html; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".js": "text/javascript; charset=utf-8",
            }[source.suffix]
            body = source.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            asset_name = path.rpartition("/ui/")[2] if "/ui/" in path else None
            if asset_name in VIEWER_ASSETS:
                self.browser_file(VIEWER_ASSETS[asset_name])
            elif path == "/api/health":
                self.reply(200, {"ready": True})
            elif path == "/api/runs":
                self.reply(200, {"runs": library.list()})
            elif path.startswith("/api/runs/"):
                job = library.get(path.rsplit("/", 1)[-1])
                self.reply(200 if job else 404, job or {"error": "Run not found"})
            else:
                if path == "/":
                    self.path = "/diagnostics.html"
                if urlsplit(self.path).path.endswith("/diagnostics.html"):
                    page = Path(self.translate_path(urlsplit(self.path).path))
                    recording = page.parent / "assets/world-history.json"
                    if recording.is_file():
                        self.browser_file(VIEWER_TEMPLATE)
                        return
                super().do_GET()

        def do_POST(self) -> None:
            if self.path != "/api/runs":
                self.reply(404, {"error": "Unknown endpoint"})
                return
            # Only same-origin JSON requests may launch work on this local machine.
            origin = self.headers.get("Origin")
            if origin and origin != f"http://{self.headers.get('Host')}":
                self.reply(403, {"error": "Use the local command center to start experiments"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 4096 or self.headers.get("Content-Type") != "application/json":
                    raise ValueError("Expected a small JSON configuration")
                values = json.loads(self.rfile.read(length))
                if not isinstance(values, dict):
                    raise ValueError("Expected a configuration object")
                title = values.pop("title", "")
                if not isinstance(title, str) or len(title) > 80:
                    raise ValueError("Experiment name must be at most 80 characters")
                spec = parse_spec(values)
            except (ValueError, TypeError) as error:
                self.reply(400, {"error": str(error)})
                return
            job = library.create(spec, title.strip())
            self.reply(202, job)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--directory", type=Path, default=Path("studies/webui"))
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(args.directory.resolve()))
    print(f"Research command center: http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
