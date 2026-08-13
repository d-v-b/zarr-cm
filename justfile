# Development tasks for zarr-cm.
#
# Requires `just` (https://just.systems) and `uv` (https://docs.astral.sh/uv/).
# Everything else is fetched on demand by uv, so no other setup is needed.
#
# The recipes that use the project environment all ask for the same dependency
# groups (`--all-groups`), so running them in any order never re-syncs .venv.

# List the available recipes
default:
    @just --list

# The package is reinstalled so that the hatch-vcs version recorded in the
# environment follows the current commit, which `test_version` checks.
[doc("Sync the local development environment (all dependency groups)")]
sync:
    uv sync --all-groups --reinstall-package zarr-cm

# Re-resolve uv.lock. Pass --upgrade to move pinned versions forward.
lock *args:
    uv lock {{ args }}

# Syncs first so the recorded version matches HEAD after a fresh commit.
[doc("Run every check that CI runs: lint, pylint, type check, tests")]
check: sync lint pylint typecheck test

# Run the pre-commit hooks (ruff, prettier, pyright on src, ...) over all files
lint *args:
    uvx prek run --all-files --show-diff-on-failure {{ args }}

# Install the pre-commit hooks into .git/hooks so they run on every commit
lint-install:
    uvx prek install

# Run Pylint over the package
pylint *args:
    uvx nox -s pylint -- {{ args }}

# Type check src/ and tests/ with pyright, as the typecheck nox session does
typecheck *args:
    uv run --all-groups --with nox pyright {{ args }}

# Run the test suite
test *args:
    uv run --all-groups pytest {{ args }}

# Run the test suite with coverage, as CI does
test-cov *args:
    uv run --all-groups pytest -ra --cov --cov-report=xml --cov-report=term --durations=20 {{ args }}

# Run the test suite against another Python version, in a throwaway environment
test-python version *args:
    uv run --isolated --all-groups --python {{ version }} pytest {{ args }}

# Serve the docs locally with live reload
docs *args:
    uv run --all-groups mkdocs serve --clean {{ args }}

# Build the docs into site/
docs-build *args:
    uv run --all-groups mkdocs build --clean {{ args }}

# Build an sdist and a wheel into dist/
build *args:
    uv build {{ args }}

# Check the vendored convention schemas against upstream main
check-upstream:
    uv run --no-project python .github/scripts/check_upstream.py

# Remove build, docs, and tool cache artifacts
clean:
    rm -rf build dist site .coverage coverage.xml .pytest_cache .mypy_cache .ruff_cache .nox
    find . -name '__pycache__' -type d -prune -exec rm -rf {} +
