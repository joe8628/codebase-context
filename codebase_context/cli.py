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


@click.group()
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

    _setup_engram(root)


@cli.command()
def doctor() -> None:
    """Check for required external binaries and offer to install missing ones."""
    _setup_external_deps()


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


_MCP_ENTRY = {"command": "ccindex", "args": ["serve"]}
_MCP_KEY = "codebase-context"
_ENGRAM_KEY = "engram"

# (binary, label, method, install_arg, fallback_url)
# method: "brew" | "npm" | "manual"
# install_arg: brew formula, npm package(s), or None
# fallback_url: shown when auto-install is unavailable, or None
_EXTERNAL_DEPS: list[tuple[str, str, str, str | None, str | None]] = [
    (
        "engram",
        "Engram memory MCP",
        "brew",
        "gentleman-programming/tap/engram",
        "https://github.com/Gentleman-Programming/engram/releases",
    ),
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


def _setup_engram(project_root: str) -> None:
    """Register engram memory MCP in .claude/settings.json if engram is on PATH."""
    if not shutil.which("engram"):
        return  # not installed — _setup_external_deps already offered installation

    settings_path = Path(project_root) / ".claude" / "settings.json"

    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        if _ENGRAM_KEY in data.get("mcpServers", {}):
            click.echo("  engram already configured.")
            return

    if click.confirm("\nRegister engram memory MCP for this project?", default=True):
        if settings_path.exists():
            try:
                data = json.loads(settings_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
        else:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            data = {}

        engram_data_dir = str(Path(project_root) / ".claude")
        data.setdefault("mcpServers", {})[_ENGRAM_KEY] = {
            "command": "engram",
            "args": ["mcp"],
            "env": {"ENGRAM_DATA_DIR": engram_data_dir},
        }
        settings_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        click.echo("  Added engram MCP to .claude/settings.json")


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
        ".claude/engram.db",
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
