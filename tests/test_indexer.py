import os
import shutil
import time
from pathlib import Path

import pytest

SAMPLE_PROJECT = Path(__file__).parent / "fixtures" / "sample_project"


@pytest.fixture
def tmp_project(tmp_path):
    """Copy sample project to a temp directory for isolation."""
    dest = tmp_path / "sample_project"
    shutil.copytree(SAMPLE_PROJECT, dest)
    # Create a fake .git dir so find_project_root works
    (dest / ".git").mkdir()
    return str(dest)


def test_discover_files_finds_py_and_ts(tmp_project):
    from codebase_context.indexer import discover_files
    files = discover_files(tmp_project)
    extensions = {Path(f).suffix for f in files}
    assert ".py" in extensions
    assert ".ts" in extensions


def test_discover_files_excludes_gitignore(tmp_project):
    from codebase_context.indexer import discover_files
    gitignore = Path(tmp_project) / ".gitignore"
    gitignore.write_text("**/validation.py\n")
    files = discover_files(tmp_project)
    assert not any("validation.py" in f for f in files)


def test_full_index_creates_chunks(tmp_project):
    from codebase_context.indexer import Indexer
    indexer = Indexer(tmp_project)
    stats = indexer.full_index(show_progress=False)
    assert stats.files_indexed > 0
    assert stats.chunks_created > 0
    assert stats.duration_seconds >= 0


def test_full_index_writes_repo_map(tmp_project):
    from codebase_context.indexer import Indexer
    from codebase_context.config import REPO_MAP_PATH
    indexer = Indexer(tmp_project)
    indexer.full_index(show_progress=False)
    repo_map_path = Path(tmp_project) / REPO_MAP_PATH
    assert repo_map_path.exists()
    content = repo_map_path.read_text()
    assert "AuthRouter" in content or "auth" in content.lower()


def test_incremental_index_skips_unchanged(tmp_project):
    from codebase_context.indexer import Indexer
    indexer = Indexer(tmp_project)
    indexer.full_index(show_progress=False)

    # Re-index without changes
    stats = indexer.incremental_index(show_progress=False)
    assert stats.files_indexed == 0


def test_incremental_index_processes_changed_file(tmp_project):
    from codebase_context.indexer import Indexer
    indexer = Indexer(tmp_project)
    indexer.full_index(show_progress=False)

    # Modify a file
    auth_path = Path(tmp_project) / "src" / "api" / "auth.py"
    content = auth_path.read_text()
    auth_path.write_text(content + "\n\ndef new_function(): pass\n")
    time.sleep(0.05)  # ensure mtime changes

    stats = indexer.incremental_index(show_progress=False)
    assert stats.files_indexed >= 1


def test_index_file_returns_chunk_count(tmp_project):
    from codebase_context.indexer import Indexer
    indexer = Indexer(tmp_project)
    auth_path = str(Path(tmp_project) / "src" / "api" / "auth.py")
    count = indexer.index_file(auth_path)
    assert count > 0


def test_remove_file_clears_chunks(tmp_project):
    from codebase_context.indexer import Indexer
    indexer = Indexer(tmp_project)
    auth_path = str(Path(tmp_project) / "src" / "api" / "auth.py")
    indexer.index_file(auth_path)
    before = indexer.store.count()
    indexer.remove_file(auth_path)
    after = indexer.store.count()
    assert after < before
