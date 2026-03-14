"""Click CLI — entry point: ccindex."""

from __future__ import annotations

import json
import os
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

    click.echo(
        "\nSetup complete! To use the MCP server, add to .claude/mcp.json:\n"
        '  {"mcpServers": {"codebase-context": {"command": "ccindex", "args": ["serve"]}}}'
    )


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
