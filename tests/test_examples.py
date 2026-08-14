from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent
_EXAMPLES_DIR = _PROJECT_ROOT / "examples"
# One subdirectory per example, holding <name>/<name>.py (zarr-python's layout).
_SCRIPTS = sorted(_EXAMPLES_DIR.glob("*/*.py"))


def test_examples_dir_is_populated() -> None:
    assert len(_SCRIPTS) >= 5, f"expected >=5 example scripts, found {_SCRIPTS}"


@pytest.mark.parametrize("script", _SCRIPTS, ids=lambda p: p.stem)
def test_example_is_documented(script: Path) -> None:
    """Every example ships its docs: a README beside it, a docs page, a nav entry."""
    name = script.parent.name
    assert script.name == f"{name}.py", "script is named after its directory"
    assert (script.parent / "README.md").is_file(), f"examples/{name}/README.md missing"
    docs_page = _PROJECT_ROOT / "docs" / "examples" / f"{name}.md"
    assert docs_page.is_file(), f"docs/examples/{name}.md missing"
    mkdocs = (_PROJECT_ROOT / "mkdocs.yml").read_text()
    assert f"examples/{name}.md" in mkdocs, f"examples/{name}.md not in mkdocs nav"


@pytest.mark.parametrize("script", _SCRIPTS, ids=lambda p: p.stem)
def test_example_runs_clean(script: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"{script.name} exited {result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    assert result.stdout.strip().endswith("OK")
