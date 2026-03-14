"""File system watcher for real-time incremental reindexing and git hook management."""

from __future__ import annotations

import logging
import os
import signal
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from codebase_context.config import LANGUAGES
from codebase_context.utils import is_ignored, load_gitignore

logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS = set(LANGUAGES.keys())
_DEBOUNCE_SECONDS = 2.0


class _CodebaseEventHandler(FileSystemEventHandler):
    """Watchdog event handler with debounce and filtering."""

    def __init__(self, indexer, project_root: str):
        self._indexer = indexer
        self._root = project_root
        self._gitignore = load_gitignore(project_root)
        self._pending: dict[str, str] = {}  # filepath -> event type
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None

    def _should_handle(self, filepath: str) -> bool:
        ext = Path(filepath).suffix
        if ext not in _SUPPORTED_EXTENSIONS:
            return False
        if is_ignored(filepath, self._root, self._gitignore):
            return False
        return True

    def _schedule_flush(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._timer = threading.Timer(_DEBOUNCE_SECONDS, self._flush)
        self._timer.daemon = True
        self._timer.start()

    def _flush(self) -> None:
        with self._lock:
            pending = dict(self._pending)
            self._pending.clear()

        for filepath, event_type in pending.items():
            ts = time.strftime("%Y-%m-%dT%H:%M:%S")
            if event_type == "deleted":
                self._indexer.remove_file(filepath)
                print(f"[{ts}] deleted  {filepath}")
            else:
                chunks = self._indexer.index_file(filepath)
                print(f"[{ts}] {event_type:<8} {filepath}  ({chunks} chunks)")

        if pending:
            # Regenerate repo map after batch
            from codebase_context.indexer import discover_files
            from codebase_context.repo_map import generate_repo_map, write_repo_map
            from codebase_context.parser import parse_file

            files = discover_files(self._root)
            symbols_by_file: dict[str, list] = {}
            for f in files:
                syms = parse_file(f)
                if syms:
                    symbols_by_file[os.path.relpath(f, self._root)] = syms
            repo_map = generate_repo_map(self._root, symbols_by_file)
            write_repo_map(self._root, repo_map)

    def on_created(self, event):
        if event.is_directory:
            return
        if self._should_handle(event.src_path):
            with self._lock:
                self._pending[event.src_path] = "created"
            self._schedule_flush()

    def on_modified(self, event):
        if event.is_directory:
            return
        if self._should_handle(event.src_path):
            with self._lock:
                self._pending[event.src_path] = "modified"
            self._schedule_flush()

    def on_deleted(self, event):
        if event.is_directory:
            return
        if self._should_handle(event.src_path):
            with self._lock:
                self._pending[event.src_path] = "deleted"
            self._schedule_flush()

    def on_moved(self, event):
        if event.is_directory:
            return
        changed = False
        if self._should_handle(event.src_path):
            with self._lock:
                self._pending[event.src_path] = "deleted"
            changed = True
        if self._should_handle(event.dest_path):
            with self._lock:
                self._pending[event.dest_path] = "created"
            changed = True
        if changed:
            self._schedule_flush()


def watch(project_root: str) -> None:
    """
    Starts a watchdog FileSystemEventHandler on the project root.
    Runs until SIGINT/SIGTERM.
    """
    from codebase_context.indexer import Indexer

    indexer = Indexer(project_root)
    handler = _CodebaseEventHandler(indexer, project_root)
    observer = Observer()
    observer.schedule(handler, project_root, recursive=True)
    observer.start()

    print(f"[codebase-context] Watching {project_root}  (Ctrl+C to stop)")

    def _stop(signum, frame):
        observer.stop()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    observer.join()
    print("[codebase-context] Watcher stopped.")


def install_git_hook(project_root: str) -> None:
    """
    Writes a post-commit hook to .git/hooks/post-commit.
    Appends if hook already exists. Makes it executable (chmod 755).
    """
    hook_dir = Path(project_root) / ".git" / "hooks"
    hook_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hook_dir / "post-commit"

    ccindex_line = "ccindex update\n"

    if hook_path.exists():
        content = hook_path.read_text(encoding="utf-8")
        if "ccindex update" in content:
            print(f"Git hook already contains ccindex line: {hook_path}")
            return
        # Append to existing hook
        hook_path.write_text(content.rstrip("\n") + "\n" + ccindex_line, encoding="utf-8")
    else:
        hook_path.write_text(f"#!/bin/sh\n{ccindex_line}", encoding="utf-8")

    hook_path.chmod(0o755)
    print(f"Git hook installed: {hook_path}")


def uninstall_git_hook(project_root: str) -> None:
    """Removes the ccindex line from .git/hooks/post-commit."""
    hook_path = Path(project_root) / ".git" / "hooks" / "post-commit"
    if not hook_path.exists():
        print("No post-commit hook found.")
        return

    content = hook_path.read_text(encoding="utf-8")
    new_lines = [l for l in content.splitlines() if "ccindex update" not in l]

    # If only shebang remains (or empty), remove the file
    meaningful = [l for l in new_lines if l.strip() and l.strip() != "#!/bin/sh"]
    if not meaningful:
        hook_path.unlink()
        print(f"Git hook removed: {hook_path}")
    else:
        hook_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        print(f"ccindex line removed from: {hook_path}")
