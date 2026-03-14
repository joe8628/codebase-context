import os
import pytest
from codebase_context.utils import (
    count_tokens, slugify, load_gitignore, is_ignored, find_project_root
)


def test_count_tokens_basic():
    assert count_tokens("hello world") == pytest.approx(2 * 1.3, abs=1)


def test_count_tokens_empty():
    assert count_tokens("") == 0


def test_slugify_basic():
    result = slugify("/home/user/my-project")
    assert "/" not in result
    assert " " not in result


def test_slugify_safe_for_chroma():
    result = slugify("/very/long/path/to/some/project/directory/that/is/deeply/nested")
    assert len(result) <= 63
    assert len(result) >= 3


def test_find_project_root_with_git(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    subdir = tmp_path / "src" / "api"
    subdir.mkdir(parents=True)
    result = find_project_root(str(subdir))
    assert result == str(tmp_path)


def test_find_project_root_no_git(tmp_path):
    result = find_project_root(str(tmp_path))
    assert result == str(tmp_path)


def test_load_gitignore_parses(tmp_path):
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("*.pyc\nnode_modules/\n")
    spec = load_gitignore(str(tmp_path))
    assert spec is not None


def test_is_ignored_gitignore(tmp_path):
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("*.pyc\n")
    spec = load_gitignore(str(tmp_path))
    ignored_file = str(tmp_path / "foo.pyc")
    not_ignored = str(tmp_path / "foo.py")
    assert is_ignored(ignored_file, str(tmp_path), spec)
    assert not is_ignored(not_ignored, str(tmp_path), spec)


def test_is_ignored_always_ignore(tmp_path):
    spec = load_gitignore(str(tmp_path))
    node_modules_file = str(tmp_path / "node_modules" / "lodash" / "index.js")
    assert is_ignored(node_modules_file, str(tmp_path), spec)
