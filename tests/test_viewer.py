"""Verify that exported pages and server routes load the same browser assets."""

import json
import re
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path

import pytest

from experiments.command_center import make_handler, run_experiment
from experiments.generate_worlds import generate
from experiments.recording import WorldRecorder
from experiments.viewer import VIEWER_ASSETS, VIEWER_TEMPLATE, export_viewer
from experiments.worlds import WorldSpec


class AssetReferences(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []
        self.inline_scripts = 0
        self.inline_styles = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "script" and not values.get("src"):
            self.inline_scripts += 1
        if tag == "style":
            self.inline_styles += 1
        reference = values.get("src") if tag == "script" else values.get("href")
        if reference and reference.startswith("ui/"):
            self.references.append(reference)


@pytest.mark.parametrize("kind", ["reference", "experiment", "recorder"])
def test_exports_ship_html_assets_and_separate_recording(tmp_path: Path, kind: str) -> None:
    spec = WorldSpec(rows=3, columns=3, periods=2)
    if kind == "reference":
        generate(tmp_path, rows=3, columns=3, periods=2)
    elif kind == "experiment":
        run_experiment(spec, tmp_path, title="Separate assets")
    else:
        WorldRecorder(spec.create()).export(tmp_path)
    html = (tmp_path / "diagnostics.html").read_text()
    assert html == VIEWER_TEMPLATE.read_text()
    assert len(html.encode()) < 30000
    parser = AssetReferences()
    parser.feed(html)
    assert parser.inline_scripts == parser.inline_styles == 0
    assert set(parser.references) == {"ui/diagnostics.css", "ui/bootstrap.js"}
    for reference in parser.references:
        assert (tmp_path / reference).is_file()
    for name, source in VIEWER_ASSETS.items():
        exported = tmp_path / "ui" / name
        assert exported.read_bytes() == source.read_bytes()
        if exported.suffix == ".js":
            for module in re.findall(r"from ['\"](\./[^'\"]+)['\"]", exported.read_text()):
                assert (exported.parent / module).is_file()
    data = json.loads((tmp_path / "assets/world-history.json").read_text())
    assert data
    assert '"frames"' not in html


@pytest.mark.parametrize("prefix", ["", "/runs/legacy"])
def test_server_serves_current_assets_for_root_and_legacy_recordings(
    tmp_path: Path, prefix: str,
) -> None:
    output = tmp_path / prefix.lstrip("/")
    (output / "assets").mkdir(parents=True)
    recording = '{"marker":"recording stays separate"}'
    (output / "assets/world-history.json").write_text(recording)
    (output / "diagnostics.html").write_text("old inline export")
    handler_type = make_handler(tmp_path)
    handler = handler_type.__new__(handler_type)
    handler.directory = str(tmp_path)
    handler.headers = {}
    status_codes = []
    headers = {}
    handler.send_response = lambda status, message=None: status_codes.append(status)
    handler.send_header = lambda name, value: headers.update({name: value})
    handler.end_headers = lambda: None
    expected = {"diagnostics.html": VIEWER_TEMPLATE}
    expected.update({f"ui/{name}": source for name, source in VIEWER_ASSETS.items()})
    for relative, source in expected.items():
        handler.path = f"{prefix}/{relative}?view=map"
        handler.wfile = BytesIO()
        handler.do_GET()
        assert status_codes[-1] == 200
        assert handler.wfile.getvalue() == source.read_bytes()
        if relative.endswith(".js"):
            assert headers["Content-Type"] == "text/javascript; charset=utf-8"
        elif relative.endswith(".css"):
            assert headers["Content-Type"] == "text/css; charset=utf-8"
    handler.path = f"{prefix}/assets/world-history.json"
    handler.wfile = BytesIO()
    handler.do_GET()
    assert status_codes[-1] == 200
    assert handler.wfile.getvalue().decode() == recording
    assert not (output / "ui").exists()  # Legacy saves use the server's current sources.


def test_export_does_not_change_recorded_data(tmp_path: Path) -> None:
    (tmp_path / "assets").mkdir()
    recording = tmp_path / "assets/world-history.json"
    recording.write_text('{"existing":true}')
    export_viewer(tmp_path)
    assert recording.read_text() == '{"existing":true}'
