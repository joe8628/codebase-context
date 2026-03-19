"""Tests for codebase_context.cli — init command prompts."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from codebase_context.cli import cli

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
