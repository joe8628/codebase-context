"""Click CLI — entry point: ccindex."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import click

from codebase_context.config import EMBED_MODEL
from codebase_context.utils import find_project_root

try:
    from importlib.metadata import version as _meta_version, PackageNotFoundError as _PkgNotFound
    _VERSION = _meta_version("codebase-context")
except _PkgNotFound:
    _VERSION = "0.0.0+dev"


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


@cli.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Full index of current project."""
    from codebase_context.indexer import Indexer

    root = ctx.obj["root"]
    click.echo(f"Indexing {root}...")

    indexer = Indexer(root)
    stats = indexer.full_index(show_progress=True)

    click.echo(
        f"\n✓ Indexed {stats.files_indexed} files, "
        f"{stats.chunks_created} chunks in {stats.duration_seconds:.1f}s"
    )

    _update_gitignore(root)

    # Prompt to add repo map to CLAUDE.md
    claude_md = Path(root) / "CLAUDE.md"
    ref_line = "@.codebase-context/repo_map.md"
    if claude_md.exists():
        has_ref = ref_line in claude_md.read_text(encoding="utf-8")
    else:
        has_ref = False

    if not has_ref:
        if click.confirm("\nAdd repo map reference to CLAUDE.md?", default=True):
            if claude_md.exists():
                claude_md.write_text(
                    claude_md.read_text(encoding="utf-8").rstrip("\n")
                    + f"\n\n{ref_line}\n",
                    encoding="utf-8",
                )
            else:
                claude_md.write_text(f"{ref_line}\n", encoding="utf-8")
            click.echo(f"  Added {ref_line} to CLAUDE.md")

    if click.confirm("\nInstall git post-commit hook for auto-reindexing?", default=True):
        from codebase_context.watcher import install_git_hook
        install_git_hook(root)

    _setup_external_deps()

    _setup_mcp_server(root)

    _setup_memgram(root)


@cli.command()
@click.pass_context
def doctor(ctx: click.Context) -> None:
    """Check binaries and MCP setup; registers memgram if missing."""
    _setup_external_deps()
    _setup_memgram(ctx.obj["root"])


@cli.command()
@click.pass_context
def update(ctx: click.Context) -> None:
    """Incremental index (changed files only)."""
    from codebase_context.indexer import Indexer

    root = ctx.obj["root"]
    indexer = Indexer(root)
    stats = indexer.incremental_index(show_progress=True)

    if stats.files_indexed == 0:
        click.echo("No changed files. Index is up to date.")
    else:
        click.echo(
            f"Updated {stats.files_indexed} files, "
            f"{stats.chunks_created} chunks in {stats.duration_seconds:.1f}s"
        )


@cli.command()
@click.pass_context
def watch(ctx: click.Context) -> None:
    """Real-time file watcher (Ctrl+C to stop)."""
    from codebase_context.watcher import watch as _watch
    _watch(ctx.obj["root"])


@cli.command()
@click.argument("query")
@click.option("--top-k", default=5, show_default=True, help="Number of results")
@click.option("--language", default=None, help="Filter: python or typescript")
@click.option("--json", "output_json", is_flag=True, help="Output raw JSON")
@click.pass_context
def search(
    ctx: click.Context,
    query: str,
    top_k: int,
    language: str | None,
    output_json: bool,
) -> None:
    """Semantic search from terminal."""
    from codebase_context.retriever import Retriever

    root = ctx.obj["root"]
    retriever = Retriever(root)
    results = retriever.search(query, top_k=top_k, language=language)

    if output_json:
        click.echo(json.dumps([
            {
                "filepath":     r.filepath,
                "symbol_name":  r.symbol_name,
                "symbol_type":  r.symbol_type,
                "signature":    r.signature,
                "score":        r.score,
                "start_line":   r.start_line,
                "end_line":     r.end_line,
                "parent_class": r.parent_class,
                "source":       r.source,
            }
            for r in results
        ], indent=2))
        return

    if not results:
        click.echo("No results found.")
        return

    for r in results:
        header = f"{r.filepath}:{r.start_line + 1}  [{r.symbol_type}]  score={r.score:.3f}"
        click.echo(click.style(header, bold=True))
        click.echo(f"  {r.signature}")
        click.echo("")


@cli.command("map")
@click.pass_context
def map_cmd(ctx: click.Context) -> None:
    """Print repo map to stdout."""
    from codebase_context.retriever import Retriever

    root = ctx.obj["root"]
    retriever = Retriever(root)
    click.echo(retriever.get_repo_map(root))


@cli.command()
@click.pass_context
def stats(ctx: click.Context) -> None:
    """Show index statistics."""
    from codebase_context.config import CHROMA_DIR
    from codebase_context.utils import load_index_meta

    root = ctx.obj["root"]
    meta = load_index_meta(root)

    chroma_path = Path(root) / CHROMA_DIR
    size_mb = 0.0
    if chroma_path.exists():
        total = sum(f.stat().st_size for f in chroma_path.rglob("*") if f.is_file())
        size_mb = total / (1024 * 1024)

    click.echo(f"Files indexed:   {meta.total_files}")
    click.echo(f"Total chunks:    {meta.total_chunks}")
    click.echo(f"Index size:      {size_mb:.1f} MB")
    click.echo(f"Last index:      {meta.last_full_index or 'never'}")
    click.echo(f"Embedding model: {EMBED_MODEL}")


@cli.command()
@click.pass_context
def migrate(ctx: click.Context) -> None:
    """Migrate HANDOFF.md and DECISIONS.md into the memgram memory layer."""
    from codebase_context.migrate import AlreadyMigratedError, run_migration

    root = ctx.obj["root"]
    try:
        handoff_count, decision_count = run_migration(root)
    except AlreadyMigratedError as exc:
        click.echo(f"Warning: {exc}", err=True)
        sys.exit(1)

    if handoff_count == 0 and decision_count == 0:
        click.echo("Nothing to migrate.")
        return

    click.echo(
        f"Migrated {handoff_count} handoff records and {decision_count} decision records."
    )


@cli.command()
@click.option("--confirm", is_flag=True, required=True, help="Required: confirm deletion")
@click.pass_context
def clear(ctx: click.Context, confirm: bool) -> None:
    """Delete index and repo map. Requires --confirm."""
    from codebase_context.config import REPO_MAP_PATH
    from codebase_context.store import VectorStore

    root = ctx.obj["root"]
    store = VectorStore(root)
    store.clear()

    repo_map = Path(root) / REPO_MAP_PATH
    if repo_map.exists():
        repo_map.unlink()

    click.echo("Index and repo map cleared.")


@cli.command()
@click.option("--debug", is_flag=True, help="Print install-method detection details.")
def upgrade(debug: bool) -> None:
    """Upgrade codebase-context to the latest version from GitHub."""
    github_url = "git+https://github.com/joe8628/codebase-context"
    exe = Path(sys.executable).resolve()
    uv_tools_dir = Path.home() / ".local" / "share" / "uv" / "tools"
    pipx_venvs_dir = Path.home() / ".local" / "share" / "pipx" / "venvs"
    in_venv = hasattr(sys, "real_prefix") or sys.prefix != sys.base_prefix

    if debug:
        click.echo(f"  sys.executable : {exe}")
        click.echo(f"  sys.prefix     : {sys.prefix}")
        click.echo(f"  sys.base_prefix: {sys.base_prefix}")
        click.echo(f"  in_venv        : {in_venv}")
        click.echo(f"  uv_tools_dir   : {uv_tools_dir}  (exists={uv_tools_dir.exists()})")
        click.echo(f"  pipx_venvs_dir : {pipx_venvs_dir}  (exists={pipx_venvs_dir.exists()})")
        click.echo(f"  which uv       : {shutil.which('uv')}")
        click.echo(f"  which pipx     : {shutil.which('pipx')}")
        click.echo(f"  which ccindex  : {shutil.which('ccindex')}")

    if uv_tools_dir.exists() and exe.is_relative_to(uv_tools_dir):
        cmd = ["uv", "tool", "upgrade", "codebase-context"]
        method = "uv tool upgrade"
    elif pipx_venvs_dir.exists() and exe.is_relative_to(pipx_venvs_dir):
        cmd = ["pipx", "upgrade", "codebase-context"]
        method = "pipx upgrade"
    elif in_venv:
        # Inside an explicit virtualenv — pip works without flags
        cmd = [sys.executable, "-m", "pip", "install", "--upgrade", github_url]
        method = "pip (venv)"
    elif shutil.which("uv"):
        # uv available but ccindex not in uv's tools dir — use uv tool install --force
        # This avoids PEP 668 entirely by creating an isolated uv-managed environment
        cmd = ["uv", "tool", "install", "--force", github_url]
        method = "uv tool install --force"
    elif shutil.which("pipx"):
        cmd = ["pipx", "install", "--force", github_url]
        method = "pipx install --force"
    else:
        # Last resort: bypass externally-managed restriction.
        # --user is also blocked on some Debian/Ubuntu images, so use --break-system-packages.
        cmd = [sys.executable, "-m", "pip", "install", "--break-system-packages", "--upgrade", github_url]
        method = "pip --break-system-packages"

    click.echo(f"Upgrading via {method}...")
    result = subprocess.run(cmd)
    if result.returncode == 0:
        click.echo("✓ codebase-context upgraded successfully")
    else:
        click.echo("✗ Upgrade failed. Run with --debug to see detection details.", err=True)
        click.echo("  Manual options:", err=True)
        click.echo(f"    uv tool install --force {github_url}", err=True)
        click.echo(f"    pipx install --force {github_url}", err=True)
        sys.exit(1)


@cli.command("install-hook")
@click.pass_context
def install_hook(ctx: click.Context) -> None:
    """Install git post-commit hook."""
    from codebase_context.watcher import install_git_hook
    install_git_hook(ctx.obj["root"])


@cli.command("uninstall-hook")
@click.pass_context
def uninstall_hook(ctx: click.Context) -> None:
    """Remove git post-commit hook."""
    from codebase_context.watcher import uninstall_git_hook
    uninstall_git_hook(ctx.obj["root"])


@cli.command()
@click.pass_context
def serve(ctx: click.Context) -> None:
    """Start MCP server (used by Claude Code)."""
    from codebase_context.mcp_server import run_server
    run_server()


@cli.command("mem-serve")
def mem_serve() -> None:
    """Start memgram memory MCP server (used by Claude Code)."""
    from codebase_context.memgram.mcp_server import run_server
    run_server()


_MCP_ENTRY = {"command": "ccindex", "args": ["serve"], "type": "stdio"}
_MCP_KEY = "codebase-context"
_MEMGRAM_KEY = "memgram"

# (binary, label, method, install_arg, fallback_url)
# method: "brew" | "npm" | "manual"
# install_arg: brew formula, npm package(s), or None
# fallback_url: shown when auto-install is unavailable, or None
_EXTERNAL_DEPS: list[tuple[str, str, str, str | None, str | None]] = [
    (
        "pyright-langserver",
        "Python LSP",
        "npm",
        "pyright",
        None,
    ),
    (
        "typescript-language-server",
        "TypeScript/JS LSP",
        "npm",
        "typescript typescript-language-server",
        None,
    ),
    (
        "clangd",
        "C/C++ LSP",
        "manual",
        None,
        None,
    ),
]


def _setup_external_deps() -> None:
    """Check for required external binaries and offer to install missing ones."""
    missing = [dep for dep in _EXTERNAL_DEPS if not shutil.which(dep[0])]
    if not missing:
        return

    click.echo("\nSome dependencies are missing:")
    has_brew = bool(shutil.which("brew"))
    for binary, label, method, install_arg, fallback_url in missing:
        if method == "brew":
            hint = f"brew install {install_arg}" if has_brew else (fallback_url or f"install {binary} manually")
        elif method == "npm":
            hint = f"npm install -g {install_arg}"
        else:
            hint = "sudo apt install clangd  OR  brew install llvm"
        click.echo(f"  {binary} ({label})  →  {hint}")

    brew_deps = [(b, a) for b, _l, m, a, _u in missing if m == "brew" and a]
    if has_brew and brew_deps and click.confirm("\nInstall brew dependencies now?", default=True):
        for binary, formula in brew_deps:
            click.echo(f"  Installing {binary}...")
            result = subprocess.run(
                ["brew", "install", formula], capture_output=True, text=True
            )
            if result.returncode == 0:
                click.echo(f"  ✓ {binary} installed")
            else:
                click.echo(f"  ✗ {binary} failed: {result.stderr.strip()}")
    elif not has_brew:
        for _b, _l, method, _a, fallback_url in missing:
            if method == "brew" and fallback_url:
                click.echo(f"\n  Download from: {fallback_url}")

    npm_deps = [(b, a) for b, _l, m, a, _u in missing if m == "npm" and a]
    if npm_deps and click.confirm("\nInstall npm-based LSP servers now?", default=True):
        for binary, packages in npm_deps:
            click.echo(f"  Installing {binary}...")
            result = subprocess.run(
                ["npm", "install", "-g", *packages.split()],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                click.echo(f"  ✓ {binary} installed")
            else:
                click.echo(f"  ✗ {binary} failed: {result.stderr.strip()}")

    if any(m == "manual" for _b, _l, m, _a, _u in missing):
        click.echo("\n  To install clangd manually:")
        click.echo("    Ubuntu/Debian:  sudo apt install clangd")
        click.echo("    macOS:          brew install llvm")


def _setup_mcp_server(project_root: str) -> None:
    """Prompt to add the MCP server entry to .claude/settings.json."""
    settings_path = Path(project_root) / ".claude" / "settings.json"

    # Check if already configured
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        if _MCP_KEY in data.get("mcpServers", {}):
            return  # Already present, nothing to do

    if click.confirm("\nAdd MCP server to .claude/settings.json?", default=True):
        if settings_path.exists():
            try:
                data = json.loads(settings_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
        else:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            data = {}

        data.setdefault("mcpServers", {})[_MCP_KEY] = _MCP_ENTRY
        settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        click.echo("  Added MCP server to .claude/settings.json")


def _setup_memgram(project_root: str) -> None:
    """Register memgram memory MCP in .claude/settings.json."""
    settings_path = Path(project_root) / ".claude" / "settings.json"

    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        if _MEMGRAM_KEY in data.get("mcpServers", {}):
            click.echo("  memgram already configured.")
            return

    if click.confirm("\nRegister memgram memory MCP for this project?", default=True):
        if settings_path.exists():
            try:
                data = json.loads(settings_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
        else:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            data = {}

        memgram_data_dir = str(Path(project_root) / ".claude")
        data.setdefault("mcpServers", {})[_MEMGRAM_KEY] = {
            "command": "ccindex",
            "args": ["mem-serve"],
            "env": {"MEMGRAM_DATA_DIR": memgram_data_dir},
        }
        settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        click.echo("  Added memgram MCP to .claude/settings.json")


def _update_gitignore(project_root: str) -> None:
    """Appends codebase-context entries to .gitignore if not already present."""
    gitignore_path = Path(project_root) / ".gitignore"

    additions = [
        "# codebase-context",
        ".codebase-context/chroma/",
        ".codebase-context/index_meta.json",
        ".codebase-context/mcp.log",
        "# optionally commit repo_map.md for team visibility:",
        "# .codebase-context/repo_map.md",
        ".claude/memgram.db",
    ]

    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
    else:
        content = ""

    if ".codebase-context/chroma/" in content:
        return  # Already present

    new_content = content.rstrip("\n") + "\n\n" + "\n".join(additions) + "\n"
    gitignore_path.write_text(new_content, encoding="utf-8")
    click.echo("  Updated .gitignore with .codebase-context/ entries")


def _fetch_latest_release() -> tuple[str, str] | None:
    return None  # stub — implemented in Task 2


def _parse_version(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except ValueError:
        return (0,)
