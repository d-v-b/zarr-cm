"""The upstream drift check tracks every convention this package models.

`.github/scripts/check_upstream.py` compares vendored schema snapshots
against each convention's upstream `main`. Its `TRACKED` dict is hand
maintained, so a newly added convention could silently ship untracked --
`stac` did briefly, and `license`/`uom` went untracked for longer. This pins
the tracked set to the package's own registry.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import zarr_cm

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "check_upstream.py"


def _tracked() -> dict[str, dict[str, str]]:
    spec = importlib.util.spec_from_file_location("check_upstream", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    tracked: dict[str, dict[str, str]] = module.TRACKED
    return tracked


def test_every_convention_is_tracked_for_drift() -> None:
    assert set(_tracked()) == set(zarr_cm.CONVENTION_NAMES)


def test_every_vendored_snapshot_exists_and_parses() -> None:
    for name, config in _tracked().items():
        path = REPO_ROOT / config["vendored"]
        assert path.is_file(), f"{name}: missing vendored snapshot {config['vendored']}"
        json.loads(path.read_text(encoding="utf-8"))
