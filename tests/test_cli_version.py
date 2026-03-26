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
    import re
    assert re.search(r"\d+\.\d+\.\d+", result.output)
