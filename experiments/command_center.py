"""Local research command center: uv run python -m experiments.command_center."""

import argparse
import json
from dataclasses import asdict
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from urllib.parse import urlsplit
from uuid import uuid4

from experiments.recording import WorldRecorder
from experiments.worlds import WorldSpec


def parse_spec(values: dict) -> WorldSpec:
    limits = {"seed": (0, 2**32 - 1), "periods": (1, 500), "rows": (3, 32), "columns": (3, 32)}
    if set(values) - {*limits, "name", "rate", "chaos_rate_ratio"}:
        raise ValueError("Unknown experiment setting")
    for key, (low, high) in limits.items():
        value = values.get(key, getattr(WorldSpec(), key))
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{key} must be an integer from {low} to {high}")
    for key, low, high in (("rate", 0, 10), ("chaos_rate_ratio", 1.001, 100)):
        value = values.get(key, getattr(WorldSpec(), key))
        if type(value) not in (int, float) or not low <= value <= high:
            raise ValueError(f"{key} must be between {low} and {high}")
    if values.get("rows", 16) * values.get("columns", 16) * values.get("periods", 120) > 128000:
        raise ValueError("Use fewer homes or periods (maximum 128,000 home-periods)")
    return WorldSpec(**values)


def run_experiment(spec: WorldSpec, output: Path) -> None:
    recorder = WorldRecorder(spec.create())
    for rate in spec.rates():
        recorder.step(disaster_rate=rate)
    data = recorder.data()
    data.update(configuration=asdict(spec), rates=spec.rates())
    serialized = json.dumps({"worlds": {spec.name: data}, "default": spec.name})
    (output / "assets").mkdir(parents=True)
    (output / "assets/world-history.json").write_text(serialized)
    template = Path(__file__).with_name("diagnostics.html").read_text()
    (output / "diagnostics.html").write_text(
        template.replace("__WORLD_DATA__", serialized.replace("<", "\\u003c"))
    )


def make_handler(root: Path) -> type[SimpleHTTPRequestHandler]:
    jobs: dict[str, dict] = {}
    lock = Lock()

    def execute(job_id: str, spec: WorldSpec) -> None:
        try:
            run_experiment(spec, root / "runs" / job_id)
            result = {"state": "complete", "url": f"/runs/{job_id}/diagnostics.html"}
        except Exception as error:
            result = {"state": "failed", "error": str(error)}
        with lock:
            jobs[job_id] = result

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

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/api/health":
                self.reply(200, {"ready": True})
            elif path.startswith("/api/runs/"):
                with lock:
                    job = jobs.get(path.rsplit("/", 1)[-1])
                self.reply(200 if job else 404, job or {"error": "Run not found"})
            else:
                if path == "/":
                    self.path = "/diagnostics.html"
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
                spec = parse_spec(values)
            except (ValueError, TypeError) as error:
                self.reply(400, {"error": str(error)})
                return
            with lock:
                if any(job["state"] == "running" for job in jobs.values()):
                    self.reply(
                        409,
                        {"error": "An experiment is already running. Try again when it finishes."},
                    )
                    return
                job_id = uuid4().hex
                jobs[job_id] = {"state": "running"}
            Thread(target=execute, args=(job_id, spec), daemon=True).start()
            self.reply(202, {"id": job_id, "state": "running"})

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
