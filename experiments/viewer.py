"""Shared HTML and browser assets for recorded experiments and the local server."""

from pathlib import Path
from shutil import copyfile

VIEWER_TEMPLATE = Path(__file__).with_name("diagnostics.html")
VIEWER_ASSET_DIR = Path(__file__).with_name("ui")
VIEWER_ASSETS = {
    path.name: path
    for path in [*VIEWER_ASSET_DIR.glob("*.css"), *VIEWER_ASSET_DIR.glob("dist/*.js")]
    if path.suffix in {".css", ".js"}
}


def export_viewer_assets(output: Path) -> None:
    """Keep exports portable when served by any ordinary static HTTP server."""
    asset_dir = output / "ui"
    asset_dir.mkdir(parents=True, exist_ok=True)
    for name, source in VIEWER_ASSETS.items():
        copyfile(source, asset_dir / name)


def export_viewer(output: Path) -> None:
    """Export a small HTML shell and assets alongside assets/world-history.json."""
    export_viewer_assets(output)
    copyfile(VIEWER_TEMPLATE, output / "diagnostics.html")
