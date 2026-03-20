"""Tests for codebase_context.cli — LSP binary setup."""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from codebase_context.cli import cli


def _mock_indexer():
    idx = MagicMock()
    idx.full_index.return_value = MagicMock(
        files_indexed=0, chunks_created=0, duration_seconds=0.1
    )
    return idx


def _init_project(tmp_path):
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)


def test_init_reports_missing_lsp_binaries(tmp_path):
    _init_project(tmp_path)
    runner = CliRunner()
    with patch("codebase_context.indexer.Indexer", return_value=_mock_indexer()), \
         patch("codebase_context.cli.shutil.which", return_value=None):
        result = runner.invoke(cli, ["--root", str(tmp_path), "init"], input="n\nn\nn\nn\n")
    assert "pyright-langserver" in result.output
    assert "typescript-language-server" in result.output
    assert "clangd" in result.output


def test_init_skips_lsp_prompt_when_all_binaries_present(tmp_path):
    _init_project(tmp_path)
    runner = CliRunner()
    with patch("codebase_context.indexer.Indexer", return_value=_mock_indexer()), \
         patch("codebase_context.cli.shutil.which", return_value="/usr/bin/something"):
        result = runner.invoke(cli, ["--root", str(tmp_path), "init"], input="n\nn\nn\n")
    assert "Install npm-based LSP" not in result.output


def test_init_npm_install_runs_on_confirm(tmp_path):
    _init_project(tmp_path)
    runner = CliRunner()
    mock_run = MagicMock(return_value=MagicMock(returncode=0))
    with patch("codebase_context.indexer.Indexer", return_value=_mock_indexer()), \
         patch("codebase_context.cli.shutil.which", return_value=None), \
         patch("codebase_context.cli.subprocess.run", mock_run):
        runner.invoke(cli, ["--root", str(tmp_path), "init"], input="n\nn\nn\ny\n")
    npm_calls = [c for c in mock_run.call_args_list if "npm" in str(c)]
    assert len(npm_calls) > 0


def test_init_shows_clangd_manual_instructions_when_missing(tmp_path):
    _init_project(tmp_path)
    runner = CliRunner()
    def fake_which(cmd):
        return None if cmd == "clangd" else "/usr/bin/" + cmd
    with patch("codebase_context.indexer.Indexer", return_value=_mock_indexer()), \
         patch("codebase_context.cli.shutil.which", fake_which):
        result = runner.invoke(cli, ["--root", str(tmp_path), "init"], input="n\nn\nn\n")
    assert "apt install clangd" in result.output or "brew install llvm" in result.output
