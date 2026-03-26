# Version Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add version tracking to ccindex so users know when they're running an old version, with a `--version` flag, `ccindex version` command, upgrade pre-check, and an interactive `ccindex release` wizard.

**Architecture:** A module-level `_VERSION` constant (read from `importlib.metadata`) provides the installed version everywhere. A `_fetch_latest_release()` helper hits the GitHub Releases API via stdlib `urllib` with graceful degradation. The `release` wizard edits `pyproject.toml` + `__init__.py`, commits, tags, pushes, and optionally creates a GitHub Release via `gh`.

**Tech Stack:** Python stdlib (`importlib.metadata`, `urllib.request`, `json`), Click, `subprocess` for git/gh.

---

## File Map

| File | Change |
|------|--------|
| `codebase_context/__init__.py` | bump `__version__` to `"2.0.0"` |
| `pyproject.toml` | bump `version` to `"2.0.0"` |
| `codebase_context/cli.py` | add `_VERSION`, `_fetch_latest_release`, `_parse_version`; add `--version` to group; add `version` and `release` commands; update `upgrade` |
| `tests/test_cli_version.py` | new — all version/release tests |

---

## Task 1: Version constant, `__init__.py` bump, `--version` flag

**Files:**
- Modify: `codebase_context/__init__.py`
- Modify: `pyproject.toml`
- Modify: `codebase_context/cli.py` (imports + group decorator)
- Test: `tests/test_cli_version.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_version.py
"""Tests for ccindex version control commands."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from codebase_context.cli import cli, _fetch_latest_release, _parse_version


@pytest.fixture()
def runner():
    return CliRunner()


def test_version_flag_exits_0(runner):
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0


def test_version_flag_contains_version_string(runner):
    result = runner.invoke(cli, ["--version"])
    # output should contain a semver-like string, e.g. "2.0.0"
    import re
    assert re.search(r"\d+\.\d+\.\d+", result.output)
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_cli_version.py -v
```

Expected: `ImportError` — `_fetch_latest_release` and `_parse_version` don't exist yet. That's fine — we'll implement them in Task 2. For now just verify the `--version` tests exist and the import fails as expected.

- [ ] **Step 3: Bump version files**

`codebase_context/__init__.py` — change the single line:
```python
__version__ = "2.0.0"
```

`pyproject.toml` — change:
```toml
version     = "2.0.0"
```

- [ ] **Step 4: Add `_VERSION` constant and `--version` to cli group**

At the top of `codebase_context/cli.py`, after the existing imports, add:

```python
try:
    from importlib.metadata import version as _meta_version
    _VERSION = _meta_version("codebase-context")
except Exception:
    _VERSION = "0.0.0+dev"
```

Update the `cli` group definition to add `@click.version_option`:

```python
@click.group()
@click.version_option(_VERSION, prog_name="ccindex")
@click.option(
    "--root",
    default=None,
    metavar="PATH",
    help="Project root (default: nearest .git directory or cwd)",
)
@click.pass_context
def cli(ctx: click.Context, root: str | None) -> None:
    """codebase-context — Tree-sitter + RAG for Claude Code agents"""
    ctx.ensure_object(dict)
    ctx.obj["root"] = root or find_project_root(os.getcwd())
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_cli_version.py::test_version_flag_exits_0 tests/test_cli_version.py::test_version_flag_contains_version_string -v
```

Expected: both PASS (the `--version` flag now works; the import errors from Task 2 symbols don't affect these two tests because they aren't imported yet — add `_fetch_latest_release` and `_parse_version` as stubs to unblock the import):

Add stubs at the bottom of `cli.py` (will be replaced in Task 2):

```python
def _fetch_latest_release() -> tuple[str, str] | None:
    return None  # stub — implemented in Task 2


def _parse_version(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except ValueError:
        return (0,)
```

Rerun:
```bash
pytest tests/test_cli_version.py -v
```

Expected: `test_version_flag_*` PASS, import tests may skip/fail — that's fine until Task 2.

- [ ] **Step 6: Run full test suite to check for regressions**

```bash
pytest --tb=short -q
```

Expected: all previously-passing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add codebase_context/__init__.py pyproject.toml codebase_context/cli.py tests/test_cli_version.py
git commit -m "feat: add _VERSION constant and --version flag; bump to 2.0.0"
```

---

## Task 2: GitHub API helper + `ccindex version` command

**Files:**
- Modify: `codebase_context/cli.py` (replace stubs, add `version` command)
- Modify: `tests/test_cli_version.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli_version.py`:

```python
# ── _fetch_latest_release ───────────────────────────────────────────────────

def _mock_github_response(tag: str, url: str = "https://github.com/joe8628/codebase-context/releases/tag/v2.0.0"):
    """Return a mock that urllib.request.urlopen will yield."""
    payload = json.dumps({"tag_name": tag, "html_url": url}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = payload
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


def test_fetch_latest_release_returns_tag_and_url():
    with patch("urllib.request.urlopen", return_value=_mock_github_response("v2.1.0")):
        result = _fetch_latest_release()
    assert result is not None
    tag, url = result
    assert tag == "2.1.0"          # leading 'v' stripped
    assert "github.com" in url


def test_fetch_latest_release_returns_none_on_network_error():
    with patch("urllib.request.urlopen", side_effect=OSError("timeout")):
        result = _fetch_latest_release()
    assert result is None


def test_fetch_latest_release_returns_none_on_missing_tag():
    payload = json.dumps({"html_url": "https://..."}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = payload
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = _fetch_latest_release()
    assert result is None


# ── _parse_version ──────────────────────────────────────────────────────────

def test_parse_version_basic():
    assert _parse_version("2.1.3") == (2, 1, 3)


def test_parse_version_strips_v_prefix():
    assert _parse_version("v2.1.3") == (2, 1, 3)


def test_parse_version_bad_input_returns_zero():
    assert _parse_version("not-a-version") == (0,)


# ── ccindex version command ─────────────────────────────────────────────────

def test_version_cmd_up_to_date(runner, monkeypatch):
    monkeypatch.setattr("codebase_context.cli._VERSION", "2.0.0")
    with patch("codebase_context.cli._fetch_latest_release", return_value=("2.0.0", "https://...")):
        result = runner.invoke(cli, ["version"])
    assert result.exit_code == 0
    assert "up to date" in result.output


def test_version_cmd_update_available(runner, monkeypatch):
    monkeypatch.setattr("codebase_context.cli._VERSION", "2.0.0")
    with patch("codebase_context.cli._fetch_latest_release", return_value=("2.1.0", "https://example.com")):
        result = runner.invoke(cli, ["version"])
    assert result.exit_code == 0
    assert "2.1.0" in result.output
    assert "update available" in result.output
    assert "https://example.com" in result.output


def test_version_cmd_no_network(runner, monkeypatch):
    monkeypatch.setattr("codebase_context.cli._VERSION", "2.0.0")
    with patch("codebase_context.cli._fetch_latest_release", return_value=None):
        result = runner.invoke(cli, ["version"])
    assert result.exit_code == 0
    assert "2.0.0" in result.output
    assert "could not check" in result.output
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_cli_version.py -k "fetch or parse or version_cmd" -v
```

Expected: most FAIL — `_fetch_latest_release` is a stub returning `None`, `_parse_version` stubs exist but tests for `ccindex version` command haven't been wired up yet.

- [ ] **Step 3: Replace stubs with real implementations in `cli.py`**

Replace the two stub functions with:

```python
def _fetch_latest_release() -> tuple[str, str] | None:
    """Return (version, html_url) of the latest GitHub release, or None on any error."""
    import urllib.request
    url = "https://api.github.com/repos/joe8628/codebase-context/releases/latest"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "ccindex"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        tag = data.get("tag_name", "").lstrip("v")
        html_url = data.get("html_url", "")
        return (tag, html_url) if tag else None
    except Exception:
        return None


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse a semver string into a comparable tuple. Returns (0,) on invalid input."""
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except ValueError:
        return (0,)
```

- [ ] **Step 4: Add `ccindex version` command in `cli.py`**

Add before `_setup_external_deps`:

```python
@cli.command("version")
def version_cmd() -> None:
    """Show installed version and check for updates."""
    click.echo(f"Installed:  {_VERSION}")
    release = _fetch_latest_release()
    if release is None:
        click.echo("Latest:     (could not check for updates)")
        return
    latest, url = release
    if _parse_version(latest) > _parse_version(_VERSION):
        click.echo(f"Latest:     {latest}  ← update available")
        click.echo(f"            {url}")
    else:
        click.echo(f"Latest:     {latest}  ✓ up to date")
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_cli_version.py -v
```

Expected: all tests in this file PASS.

- [ ] **Step 6: Run full suite**

```bash
pytest --tb=short -q
```

Expected: all previously-passing tests still pass.

- [ ] **Step 7: Commit**

```bash
git add codebase_context/cli.py tests/test_cli_version.py
git commit -m "feat: add _fetch_latest_release helper and ccindex version command"
```

---

## Task 3: `ccindex upgrade` version pre-check

**Files:**
- Modify: `codebase_context/cli.py` (upgrade command)
- Modify: `tests/test_cli_version.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli_version.py`:

```python
# ── ccindex upgrade pre-check ───────────────────────────────────────────────

def test_upgrade_skips_when_already_up_to_date(runner, monkeypatch):
    monkeypatch.setattr("codebase_context.cli._VERSION", "2.0.0")
    with patch("codebase_context.cli._fetch_latest_release", return_value=("2.0.0", "https://...")):
        result = runner.invoke(cli, ["upgrade"])
    assert result.exit_code == 0
    assert "Already up to date" in result.output


def test_upgrade_skips_when_installed_is_newer(runner, monkeypatch):
    monkeypatch.setattr("codebase_context.cli._VERSION", "2.1.0")
    with patch("codebase_context.cli._fetch_latest_release", return_value=("2.0.0", "https://...")):
        result = runner.invoke(cli, ["upgrade"])
    assert result.exit_code == 0
    assert "Already up to date" in result.output


def test_upgrade_proceeds_when_update_available(runner, monkeypatch):
    monkeypatch.setattr("codebase_context.cli._VERSION", "2.0.0")
    with patch("codebase_context.cli._fetch_latest_release", return_value=("2.1.0", "https://...")):
        # mock subprocess so we don't actually run pip/uv
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(cli, ["upgrade"])
    # should NOT print "Already up to date"
    assert "Already up to date" not in result.output


def test_upgrade_proceeds_when_network_unavailable(runner, monkeypatch):
    monkeypatch.setattr("codebase_context.cli._VERSION", "2.0.0")
    with patch("codebase_context.cli._fetch_latest_release", return_value=None):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(cli, ["upgrade"])
    # network failure should not block the upgrade
    assert "Already up to date" not in result.output
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_cli_version.py -k "upgrade" -v
```

Expected: `test_upgrade_skips_*` FAIL — the upgrade command doesn't check versions yet.

- [ ] **Step 3: Add pre-check to `upgrade` in `cli.py`**

At the top of the `upgrade()` function body, before the install-method detection, insert:

```python
    release = _fetch_latest_release()
    if release is not None:
        latest, _ = release
        if _parse_version(latest) <= _parse_version(_VERSION):
            click.echo(f"Already up to date ({_VERSION})")
            return
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_cli_version.py -k "upgrade" -v
```

Expected: all four upgrade tests PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest --tb=short -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add codebase_context/cli.py tests/test_cli_version.py
git commit -m "feat: skip upgrade when already at latest version"
```

---

## Task 4: `ccindex release` wizard

**Files:**
- Modify: `codebase_context/cli.py`
- Modify: `tests/test_cli_version.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli_version.py`:

```python
# ── ccindex release ─────────────────────────────────────────────────────────

def test_release_computes_patch_bump(runner, monkeypatch, tmp_path):
    _setup_release_files(tmp_path, "2.0.0")
    monkeypatch.setattr("codebase_context.cli._VERSION", "2.0.0")
    with patch("codebase_context.cli._release_project_root", return_value=tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(cli, ["release"], input="patch\ny\ny\nn\n")
    assert "2.0.1" in result.output
    assert (tmp_path / "pyproject.toml").read_text().count("2.0.1") == 1
    assert (tmp_path / "codebase_context" / "__init__.py").read_text().count("2.0.1") == 1


def test_release_computes_minor_bump(runner, monkeypatch, tmp_path):
    _setup_release_files(tmp_path, "2.0.0")
    monkeypatch.setattr("codebase_context.cli._VERSION", "2.0.0")
    with patch("codebase_context.cli._release_project_root", return_value=tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(cli, ["release"], input="minor\ny\ny\nn\n")
    assert "2.1.0" in result.output


def test_release_computes_major_bump(runner, monkeypatch, tmp_path):
    _setup_release_files(tmp_path, "2.0.0")
    monkeypatch.setattr("codebase_context.cli._VERSION", "2.0.0")
    with patch("codebase_context.cli._release_project_root", return_value=tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(cli, ["release"], input="major\ny\ny\nn\n")
    assert "3.0.0" in result.output


def test_release_aborts_on_n_at_commit(runner, monkeypatch, tmp_path):
    _setup_release_files(tmp_path, "2.0.0")
    monkeypatch.setattr("codebase_context.cli._VERSION", "2.0.0")
    with patch("codebase_context.cli._release_project_root", return_value=tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(cli, ["release"], input="patch\nn\n")
    assert "Aborted" in result.output
    # files should NOT be written when user says n to commit
    assert "2.0.0" in (tmp_path / "pyproject.toml").read_text()


def test_release_stops_at_tag_if_n(runner, monkeypatch, tmp_path):
    _setup_release_files(tmp_path, "2.0.0")
    monkeypatch.setattr("codebase_context.cli._VERSION", "2.0.0")
    with patch("codebase_context.cli._release_project_root", return_value=tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            # confirm commit, decline tag
            result = runner.invoke(cli, ["release"], input="patch\ny\nn\n")
    assert "git tag" in result.output   # shows the manual command


def _setup_release_files(tmp_path: Path, version: str) -> None:
    """Populate tmp_path with the two files ccindex release edits."""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(f'version     = "{version}"\n')
    init_dir = tmp_path / "codebase_context"
    init_dir.mkdir()
    (init_dir / "__init__.py").write_text(f'__version__ = "{version}"\n')
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/test_cli_version.py -k "release" -v
```

Expected: all FAIL — `ccindex release` command doesn't exist yet.

- [ ] **Step 3: Add `_release_project_root` helper and `release` command to `cli.py`**

Add before the `_setup_external_deps` function:

```python
def _release_project_root() -> Path:
    """Return the root of the codebase-context source tree.

    Looks for pyproject.toml containing our package name in the current working
    directory. Raises SystemExit with a helpful message if not found — ccindex
    release must be run from the checked-out source repo.
    """
    cwd = Path.cwd()
    pyproject = cwd / "pyproject.toml"
    if pyproject.exists() and "codebase-context" in pyproject.read_text():
        return cwd
    click.echo(
        "✗ Run ccindex release from the codebase-context source directory.\n"
        "  (pyproject.toml with name 'codebase-context' not found in cwd)",
        err=True,
    )
    sys.exit(1)


@cli.command("release")
def release_cmd() -> None:
    """Interactive wizard: bump version, commit, tag, push, create GitHub Release."""
    current = _VERSION
    click.echo(f"Current version: {current}")

    bump = click.prompt(
        "Bump type",
        type=click.Choice(["patch", "minor", "major"]),
    )

    major, minor, patch_num = (int(x) for x in current.split(".")[:3])
    if bump == "major":
        new_version = f"{major + 1}.0.0"
    elif bump == "minor":
        new_version = f"{major}.{minor + 1}.0"
    else:
        new_version = f"{major}.{minor}.{patch_num + 1}"

    click.echo(f"→ New version: {new_version}\n")

    root = _release_project_root()
    pyproject_path = root / "pyproject.toml"
    init_path = root / "codebase_context" / "__init__.py"

    pyproject_text = pyproject_path.read_text()
    new_pyproject = pyproject_text.replace(
        f'version     = "{current}"', f'version     = "{new_version}"'
    )
    if new_pyproject == pyproject_text:
        click.echo(f'  ✗ version string not found in pyproject.toml', err=True)
        sys.exit(1)

    init_text = init_path.read_text()
    new_init = init_text.replace(
        f'__version__ = "{current}"', f'__version__ = "{new_version}"'
    )
    if new_init == init_text:
        click.echo(f'  ✗ __version__ string not found in __init__.py', err=True)
        sys.exit(1)

    click.echo(f"  pyproject.toml : version {current!r} → {new_version!r}")
    click.echo(f"  __init__.py    : __version__ {current!r} → {new_version!r}")

    if not click.confirm("\nCommit version bump?", default=True):
        click.echo("Aborted.")
        return

    pyproject_path.write_text(new_pyproject)
    init_path.write_text(new_init)

    result = subprocess.run(
        ["git", "commit", "-am", f"chore: bump version to v{new_version}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        click.echo(f"  ✗ git commit failed: {result.stderr.strip()}", err=True)
        sys.exit(1)
    click.echo(f"  ✓ Committed")

    tag = f"v{new_version}"
    if not click.confirm(f"\nCreate tag {tag}?", default=True):
        click.echo(f"Skipped tagging. Run: git tag {tag}")
        return

    result = subprocess.run(["git", "tag", tag], capture_output=True, text=True)
    if result.returncode != 0:
        click.echo(f"  ✗ git tag failed: {result.stderr.strip()}", err=True)
        sys.exit(1)
    click.echo(f"  ✓ Tagged {tag}")

    if not click.confirm("\nPush commit and tag?", default=True):
        click.echo("Skipped push. Run: git push && git push --tags")
        return

    for push_cmd in [["git", "push"], ["git", "push", "--tags"]]:
        result = subprocess.run(push_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            click.echo(f"  ✗ {' '.join(push_cmd)} failed: {result.stderr.strip()}", err=True)
            sys.exit(1)
    click.echo("  ✓ Pushed")

    if not shutil.which("gh"):
        click.echo(f"\nTo create a GitHub Release manually:")
        click.echo(f"  https://github.com/joe8628/codebase-context/releases/new?tag={tag}")
        return

    if not click.confirm("\nCreate GitHub Release?", default=True):
        click.echo(f"Skipped. Run: gh release create {tag}")
        return

    title = click.prompt("Release title", default=tag)
    notes = click.prompt("Release notes (leave blank to auto-generate from commits)", default="")

    gh_cmd = ["gh", "release", "create", tag, "--title", title]
    gh_cmd += ["--notes", notes] if notes else ["--generate-notes"]

    result = subprocess.run(gh_cmd, capture_output=True, text=True)
    if result.returncode == 0:
        click.echo(f"\n  ✓ Released {tag}")
        if result.stdout.strip():
            click.echo(f"  {result.stdout.strip()}")
    else:
        click.echo(f"  ✗ gh release create failed: {result.stderr.strip()}", err=True)
        sys.exit(1)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_cli_version.py -k "release" -v
```

Expected: all release tests PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest --tb=short -q
```

Expected: all tests pass.

- [ ] **Step 6: Update CLI reference in README.md**

In the CLI Reference table, the `ccindex version` and `ccindex release` lines are not yet listed. Add them:

```
ccindex version         Show installed version and check for updates
ccindex release         Bump version, tag, push, create GitHub Release
```

Insert `ccindex version` after `ccindex upgrade` and `ccindex release` after `ccindex migrate`.

- [ ] **Step 7: Commit**

```bash
git add codebase_context/cli.py tests/test_cli_version.py README.md
git commit -m "feat: add ccindex release wizard and ccindex version command"
```
