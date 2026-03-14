import shutil
from pathlib import Path

import pytest

SAMPLE_PROJECT = Path(__file__).parent / "fixtures" / "sample_project"


@pytest.fixture(scope="module")
def indexed_project(tmp_path_factory):
    """Build a fully-indexed sample project once for all retriever tests."""
    tmp = tmp_path_factory.mktemp("retriever_project")
    dest = tmp / "sample_project"
    shutil.copytree(SAMPLE_PROJECT, dest)
    (dest / ".git").mkdir()

    from codebase_context.indexer import Indexer
    indexer = Indexer(str(dest))
    indexer.full_index(show_progress=False)
    return str(dest)


def test_search_returns_results(indexed_project):
    from codebase_context.retriever import Retriever
    retriever = Retriever(indexed_project)
    results = retriever.search("user authentication login")
    assert len(results) > 0


def test_search_results_have_required_fields(indexed_project):
    from codebase_context.retriever import Retriever
    retriever = Retriever(indexed_project)
    results = retriever.search("email validation")
    assert len(results) > 0
    r = results[0]
    assert r.filepath
    assert r.symbol_name
    assert r.symbol_type in ("function", "class", "method", "interface", "type")
    assert r.score >= 0.0


def test_search_language_filter(indexed_project):
    from codebase_context.retriever import Retriever
    retriever = Retriever(indexed_project)
    results = retriever.search("login", language="python")
    assert all(r.language == "python" for r in results)


def test_search_filepath_filter(indexed_project):
    from codebase_context.retriever import Retriever
    retriever = Retriever(indexed_project)
    results = retriever.search("auth", filepath_contains="auth")
    assert all("auth" in r.filepath for r in results)


def test_get_symbol_exact_match(indexed_project):
    from codebase_context.retriever import Retriever
    retriever = Retriever(indexed_project)
    results = retriever.get_symbol("validate_email")
    assert len(results) > 0
    assert all(r.symbol_name == "validate_email" for r in results)


def test_get_symbol_returns_empty_for_unknown(indexed_project):
    from codebase_context.retriever import Retriever
    retriever = Retriever(indexed_project)
    results = retriever.get_symbol("nonexistent_function_xyz_abc")
    assert results == []


def test_get_repo_map_returns_content(indexed_project):
    from codebase_context.retriever import Retriever
    retriever = Retriever(indexed_project)
    result = retriever.get_repo_map(indexed_project)
    assert "Repo Map" in result or "not indexed" in result


def test_get_repo_map_not_indexed_message(tmp_path):
    from codebase_context.retriever import Retriever
    (tmp_path / ".git").mkdir()
    retriever = Retriever(str(tmp_path))
    result = retriever.get_repo_map(str(tmp_path))
    assert "not indexed" in result.lower() or "run" in result.lower()
