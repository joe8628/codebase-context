# tests/test_cli_version.py
"""Tests for ccindex version control commands."""
from __future__ import annotations

import re

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
    assert re.search(r"\d+\.\d+\.\d+", result.output)


from unittest.mock import MagicMock, patch
import json


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
