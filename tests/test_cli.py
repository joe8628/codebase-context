"""Tests for codebase_context.cli — init command prompts."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import click
import pytest
from click.testing import CliRunner

from codebase_context.cli import cli, _setup_engram, _setup_external_deps


@click.command()
def _deps_cmd() -> None:
    """Thin Click wrapper for invoking _setup_external_deps in tests."""
    _setup_external_deps()

SAMPLE_PROJECT = Path(__file__).parent / "fixtures" / "sample_project"


@pytest.fixture()
def tmp_project(tmp_path):
    dest = tmp_path / "sample_project"
    shutil.copytree(SAMPLE_PROJECT, dest)
    (dest / ".git").mkdir()
    return dest


# ---------------------------------------------------------------------------
# _setup_mcp_server unit tests
# ---------------------------------------------------------------------------

class TestSetupMcpServer:
    @pytest.fixture(autouse=True)
    def _no_ext_deps(self):
        with patch("codebase_context.cli._setup_external_deps"):
            yield

    def test_creates_settings_json_when_absent(self, tmp_project):
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--root", str(tmp_project), "init"],
            input="n\nn\ny\n",  # skip CLAUDE.md, skip git hook, accept MCP
            catch_exceptions=False,
        )
        settings = tmp_project / ".claude" / "settings.json"
        assert settings.exists(), result.output
        data = json.loads(settings.read_text())
        assert data["mcpServers"]["codebase-context"]["command"] == "ccindex"
        assert data["mcpServers"]["codebase-context"]["args"] == ["serve"]
        assert data["mcpServers"]["codebase-context"]["type"] == "stdio"

    def test_merges_into_existing_settings_json(self, tmp_project):
        claude_dir = tmp_project / ".claude"
        claude_dir.mkdir()
        existing = {"theme": "dark", "otherKey": 42}
        (claude_dir / "settings.json").write_text(json.dumps(existing))

        runner = CliRunner()
        runner.invoke(
            cli,
            ["--root", str(tmp_project), "init"],
            input="n\nn\ny\n",
            catch_exceptions=False,
        )
        data = json.loads((claude_dir / "settings.json").read_text())
        # Original keys preserved
        assert data["theme"] == "dark"
        assert data["otherKey"] == 42
        # MCP entry added
        assert "codebase-context" in data["mcpServers"]

    def test_skips_if_entry_already_present(self, tmp_project):
        claude_dir = tmp_project / ".claude"
        claude_dir.mkdir()
        existing = {
            "mcpServers": {
                "codebase-context": {"command": "ccindex", "args": ["serve"], "type": "stdio"}
            }
        }
        (claude_dir / "settings.json").write_text(json.dumps(existing))

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--root", str(tmp_project), "init"],
            input="n\nn\n",  # only two prompts expected (CLAUDE.md + git hook)
            catch_exceptions=False,
        )
        # The MCP prompt should NOT appear
        assert "Add MCP server" not in result.output

    def test_confirmation_line_printed_on_accept(self, tmp_project):
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--root", str(tmp_project), "init"],
            input="n\nn\ny\n",
            catch_exceptions=False,
        )
        assert "Added MCP server to .claude/settings.json" in result.output

    def test_skipped_when_user_declines(self, tmp_project):
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--root", str(tmp_project), "init"],
            input="n\nn\nn\n",  # decline all three prompts
            catch_exceptions=False,
        )
        settings = tmp_project / ".claude" / "settings.json"
        assert not settings.exists()
        assert "Added MCP server" not in result.output

    def test_invalid_json_in_existing_settings_treated_as_empty(self, tmp_project):
        claude_dir = tmp_project / ".claude"
        claude_dir.mkdir()
        (claude_dir / "settings.json").write_text("not valid json")

        runner = CliRunner()
        runner.invoke(
            cli,
            ["--root", str(tmp_project), "init"],
            input="n\nn\ny\n",
            catch_exceptions=False,
        )
        data = json.loads((claude_dir / "settings.json").read_text())
        assert "codebase-context" in data["mcpServers"]

    def test_no_old_mcp_json_message(self, tmp_project):
        """The old .claude/mcp.json echo must not appear anywhere."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--root", str(tmp_project), "init"],
            input="n\nn\nn\n",
            catch_exceptions=False,
        )
        assert "mcp.json" not in result.output


# ---------------------------------------------------------------------------
# _setup_engram unit tests
# ---------------------------------------------------------------------------

class TestSetupEngram:
    @pytest.fixture(autouse=True)
    def _no_ext_deps(self):
        with patch("codebase_context.cli._setup_external_deps"):
            yield

    def test_skips_when_engram_not_on_path(self, tmp_project):
        with patch("codebase_context.cli.shutil.which", return_value=None):
            _setup_engram(str(tmp_project))
        settings = tmp_project / ".claude" / "settings.json"
        assert not settings.exists()

    def test_registers_entry_when_accepted(self, tmp_project):
        with patch("codebase_context.cli.shutil.which", return_value="/usr/local/bin/engram"):
            runner = CliRunner()
            runner.invoke(
                cli,
                ["--root", str(tmp_project), "init"],
                input="n\nn\nn\ny\n",  # skip CLAUDE.md, git hook, MCP; accept engram
                catch_exceptions=False,
            )
        settings = tmp_project / ".claude" / "settings.json"
        assert settings.exists()
        data = json.loads(settings.read_text())
        assert "engram" in data["mcpServers"]
        assert data["mcpServers"]["engram"]["command"] == "engram"
        assert data["mcpServers"]["engram"]["args"] == ["mcp"]

    def test_sets_engram_data_dir_to_claude_dir(self, tmp_project):
        with patch("codebase_context.cli.shutil.which", return_value="/usr/local/bin/engram"):
            runner = CliRunner()
            runner.invoke(
                cli,
                ["--root", str(tmp_project), "init"],
                input="n\nn\nn\ny\n",
                catch_exceptions=False,
            )
        settings = tmp_project / ".claude" / "settings.json"
        data = json.loads(settings.read_text())
        expected = str(tmp_project / ".claude")
        assert data["mcpServers"]["engram"]["env"]["ENGRAM_DATA_DIR"] == expected

    def test_skips_if_entry_already_present(self, tmp_project):
        claude_dir = tmp_project / ".claude"
        claude_dir.mkdir()
        existing = {"mcpServers": {"engram": {"command": "engram", "args": ["mcp"]}}}
        (claude_dir / "settings.json").write_text(json.dumps(existing))

        with patch("codebase_context.cli.shutil.which", return_value="/usr/local/bin/engram"):
            runner = CliRunner()
            result = runner.invoke(
                cli,
                ["--root", str(tmp_project), "init"],
                input="n\nn\nn\n",
                catch_exceptions=False,
            )
        assert "Register engram" not in result.output

    def test_skips_when_user_declines(self, tmp_project):
        with patch("codebase_context.cli.shutil.which", return_value="/usr/local/bin/engram"):
            runner = CliRunner()
            runner.invoke(
                cli,
                ["--root", str(tmp_project), "init"],
                input="n\nn\nn\nn\n",  # decline all prompts including engram
                catch_exceptions=False,
            )
        settings = tmp_project / ".claude" / "settings.json"
        # settings.json may not exist, or if it does, engram should not be in it
        if settings.exists():
            data = json.loads(settings.read_text())
            assert "engram" not in data.get("mcpServers", {})


# ---------------------------------------------------------------------------
# _setup_external_deps unit tests
# ---------------------------------------------------------------------------

class TestSetupExternalDeps:
    def _which_except(self, *missing_binaries):
        """Return a shutil.which side_effect that returns None for listed binaries."""
        def _which(binary):
            return None if binary in missing_binaries else f"/usr/bin/{binary}"
        return _which

    def test_no_output_when_all_present(self, tmp_project):
        runner = CliRunner()
        with patch("codebase_context.cli.shutil.which", return_value="/usr/bin/x"):
            result = runner.invoke(_deps_cmd, catch_exceptions=False)
        assert result.output == ""

    def test_shows_engram_brew_hint_when_brew_available(self, tmp_project):
        runner = CliRunner()
        with patch("codebase_context.cli.shutil.which", side_effect=self._which_except("engram")):
            result = runner.invoke(_deps_cmd, input="n\n", catch_exceptions=False)
        assert "gentleman-programming/tap/engram" in result.output

    def test_shows_engram_fallback_url_when_no_brew(self, tmp_project):
        runner = CliRunner()
        def no_brew_no_engram(binary):
            return None if binary in ("engram", "brew") else f"/usr/bin/{binary}"
        with patch("codebase_context.cli.shutil.which", side_effect=no_brew_no_engram):
            result = runner.invoke(_deps_cmd, catch_exceptions=False)
        assert "github.com/Gentleman-Programming/engram/releases" in result.output

    def test_installs_engram_via_brew_on_accept(self, tmp_project):
        def which_side(binary):
            return None if binary == "engram" else f"/usr/bin/{binary}"
        with patch("codebase_context.cli.shutil.which", side_effect=which_side), \
             patch("codebase_context.cli.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            runner = CliRunner()
            runner.invoke(_deps_cmd, input="y\nn\n", catch_exceptions=False)
        brew_calls = [c for c in mock_run.call_args_list if "brew" in c.args[0]]
        assert any("gentleman-programming/tap/engram" in str(c) for c in brew_calls)

    def test_skips_brew_install_on_decline(self, tmp_project):
        def which_side(binary):
            return None if binary == "engram" else f"/usr/bin/{binary}"
        with patch("codebase_context.cli.shutil.which", side_effect=which_side), \
             patch("codebase_context.cli.subprocess.run") as mock_run:
            runner = CliRunner()
            runner.invoke(_deps_cmd, input="n\nn\n", catch_exceptions=False)
        brew_calls = [c for c in mock_run.call_args_list if c.args and "brew" in c.args[0]]
        assert not brew_calls

    def test_installs_npm_lsp_on_accept(self, tmp_project):
        def which_side(binary):
            return None if binary == "pyright-langserver" else f"/usr/bin/{binary}"
        with patch("codebase_context.cli.shutil.which", side_effect=which_side), \
             patch("codebase_context.cli.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            runner = CliRunner()
            runner.invoke(_deps_cmd, input="y\n", catch_exceptions=False)
        npm_calls = [c for c in mock_run.call_args_list if c.args and "npm" in c.args[0]]
        assert npm_calls

    def test_shows_clangd_manual_instructions(self, tmp_project):
        def which_side(binary):
            return None if binary == "clangd" else f"/usr/bin/{binary}"
        with patch("codebase_context.cli.shutil.which", side_effect=which_side):
            runner = CliRunner()
            result = runner.invoke(_deps_cmd, catch_exceptions=False)
        assert "sudo apt install clangd" in result.output
