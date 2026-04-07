"""Tests for codebase_context.cli — init command prompts."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import click
import pytest
from click.testing import CliRunner

from codebase_context.cli import cli, _setup_external_deps


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
            input="n\ny\nn\n",  # skip git hook, accept MCP, decline memgram
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
            input="n\ny\nn\n",
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
            input="n\nn\n",  # hook=n (MCP skips), memgram=n
            catch_exceptions=False,
        )
        # The MCP prompt should NOT appear
        assert "Add MCP server" not in result.output

    def test_confirmation_line_printed_on_accept(self, tmp_project):
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--root", str(tmp_project), "init"],
            input="n\ny\nn\n",
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
            input="n\ny\nn\n",
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
            input="n\nn\nn\nn\n",
            catch_exceptions=False,
        )
        assert "mcp.json" not in result.output


# ---------------------------------------------------------------------------
# _setup_memgram unit tests
# ---------------------------------------------------------------------------

class TestSetupMemgram:
    @pytest.fixture(autouse=True)
    def _no_ext_deps(self):
        with patch("codebase_context.cli._setup_external_deps"):
            yield

    def test_registers_ccindex_mem_serve(self, tmp_project):
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--root", str(tmp_project), "init"],
            input="n\nn\ny\n",  # hook=n, MCP=n, memgram=y
            catch_exceptions=False,
        )
        settings = tmp_project / ".claude" / "settings.json"
        data = json.loads(settings.read_text())
        entry = data["mcpServers"]["memgram"]
        assert entry["command"] == "ccindex"
        assert entry["args"] == ["mem-serve"]

    def test_sets_memgram_data_dir_to_claude_dir(self, tmp_project):
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--root", str(tmp_project), "init"],
            input="n\nn\ny\n",
            catch_exceptions=False,
        )
        settings = tmp_project / ".claude" / "settings.json"
        data = json.loads(settings.read_text())
        env = data["mcpServers"]["memgram"]["env"]
        assert env["MEMGRAM_DATA_DIR"] == str(tmp_project / ".claude")

    def test_skips_if_entry_already_present(self, tmp_project):
        # Pre-populate memgram — _setup_memgram must return early without prompting.
        # init flow: CLAUDE.md=n, hook=n, MCP=n  (memgram auto-skips, no prompt)
        claude_dir = tmp_project / ".claude"
        claude_dir.mkdir()
        existing = {"mcpServers": {"memgram": {"command": "ccindex", "args": ["mem-serve"]}}}
        (claude_dir / "settings.json").write_text(json.dumps(existing))

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--root", str(tmp_project), "init"],
            input="n\nn\n",  # hook=n, MCP=n (memgram skips)
            catch_exceptions=False,
        )
        assert "Register memgram" not in result.output
        data = json.loads((claude_dir / "settings.json").read_text())
        assert data["mcpServers"]["memgram"]["command"] == "ccindex"

    def test_skips_when_user_declines(self, tmp_project):
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--root", str(tmp_project), "init"],
            input="n\nn\nn\n",  # hook=n, MCP=n, memgram=n
            catch_exceptions=False,
        )
        settings = tmp_project / ".claude" / "settings.json"
        if settings.exists():
            data = json.loads(settings.read_text())
            assert "memgram" not in data.get("mcpServers", {})

    def test_init_does_not_register_separate_memgram_server(self, tmp_project):
        """After init, settings.json should NOT have a 'memgram' MCP entry."""
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--root", str(tmp_project), "init"],
            input="n\ny\nn\n",  # hook=n, MCP=y, memgram=n
            catch_exceptions=False,
        )
        settings_path = Path(tmp_project) / ".claude" / "settings.json"
        if settings_path.exists():
            data = json.loads(settings_path.read_text())
            assert "memgram" not in data.get("mcpServers", {})


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


# ---------------------------------------------------------------------------
# doctor command — memgram registration
# ---------------------------------------------------------------------------

class TestDoctorMemgram:
    def test_doctor_registers_mcp_server_when_missing(self, tmp_project):
        runner = CliRunner()
        with patch("codebase_context.cli._setup_external_deps"):
            result = runner.invoke(
                cli,
                ["--root", str(tmp_project), "doctor"],
                input="y\n",  # accept MCP registration
                catch_exceptions=False,
            )
        settings = tmp_project / ".claude" / "settings.json"
        assert settings.exists(), result.output
        data = json.loads(settings.read_text())
        assert data["mcpServers"]["codebase-context"]["command"] == "ccindex"
        assert data["mcpServers"]["codebase-context"]["args"] == ["serve"]

    def test_doctor_skips_mcp_server_when_already_present(self, tmp_project):
        claude_dir = tmp_project / ".claude"
        claude_dir.mkdir()
        existing = {"mcpServers": {"codebase-context": {"command": "ccindex", "args": ["serve"]}}}
        (claude_dir / "settings.json").write_text(json.dumps(existing))

        runner = CliRunner()
        with patch("codebase_context.cli._setup_external_deps"):
            result = runner.invoke(
                cli,
                ["--root", str(tmp_project), "doctor"],
                catch_exceptions=False,
            )
        assert "Add MCP server" not in result.output

    def test_doctor_skips_mcp_server_when_user_declines(self, tmp_project):
        runner = CliRunner()
        with patch("codebase_context.cli._setup_external_deps"):
            runner.invoke(
                cli,
                ["--root", str(tmp_project), "doctor"],
                input="n\n",
                catch_exceptions=False,
            )
        settings = tmp_project / ".claude" / "settings.json"
        if settings.exists():
            data = json.loads(settings.read_text())
            assert "codebase-context" not in data.get("mcpServers", {})


# ---------------------------------------------------------------------------
# _remove_stale_mcp_entries unit tests
# ---------------------------------------------------------------------------

class TestUpgradeSettingsCleanup:
    def test_upgrade_removes_stale_memgram_entry(self, tmp_project):
        """After upgrade, the stale 'memgram' MCP entry is removed from settings.json."""
        from codebase_context.cli import _remove_stale_mcp_entries
        settings_path = Path(tmp_project) / ".claude" / "settings.json"
        settings_path.parent.mkdir(exist_ok=True)
        settings_path.write_text(json.dumps({
            "mcpServers": {
                "codebase-context": {"command": "ccindex", "args": ["serve"]},
                "memgram": {"command": "ccindex", "args": ["mem-serve"]},
            }
        }), encoding="utf-8")

        _remove_stale_mcp_entries(str(tmp_project))

        data = json.loads(settings_path.read_text())
        assert "memgram" not in data["mcpServers"]
        assert "codebase-context" in data["mcpServers"]

    def test_upgrade_no_op_when_no_memgram_entry(self, tmp_project):
        """No error when memgram entry is already absent."""
        from codebase_context.cli import _remove_stale_mcp_entries
        settings_path = Path(tmp_project) / ".claude" / "settings.json"
        settings_path.parent.mkdir(exist_ok=True)
        settings_path.write_text(json.dumps({
            "mcpServers": {"codebase-context": {"command": "ccindex", "args": ["serve"]}}
        }), encoding="utf-8")

        _remove_stale_mcp_entries(str(tmp_project))  # Should not raise

        data = json.loads(settings_path.read_text())
        assert "codebase-context" in data["mcpServers"]

    def test_upgrade_no_op_when_no_settings_file(self, tmp_project):
        """No error when .claude/settings.json does not exist."""
        from codebase_context.cli import _remove_stale_mcp_entries
        _remove_stale_mcp_entries(str(tmp_project))  # Should not raise


# ---------------------------------------------------------------------------
# _write_session_protocol sentinel
# ---------------------------------------------------------------------------

def test_write_session_protocol_uses_narrative_context_sentinel(tmp_project):
    from codebase_context.cli import _write_session_protocol
    claude_md = Path(tmp_project) / "CLAUDE.md"
    _write_session_protocol(str(tmp_project))
    text = claude_md.read_text()
    assert "narrative_context" in text
    assert "mem_context" not in text
