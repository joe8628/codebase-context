# tests/test_lsp_filters.py
from codebase_context.lsp.filters import is_project_file


def test_file_inside_project_is_included(tmp_path):
    f = tmp_path / "src" / "main.py"
    assert is_project_file(str(f), str(tmp_path)) is True


def test_file_outside_project_is_excluded(tmp_path):
    other = tmp_path.parent / "other" / "file.py"
    assert is_project_file(str(other), str(tmp_path)) is False


def test_node_modules_excluded(tmp_path):
    f = tmp_path / "node_modules" / "pkg" / "index.js"
    assert is_project_file(str(f), str(tmp_path)) is False


def test_venv_excluded(tmp_path):
    f = tmp_path / ".venv" / "lib" / "site.py"
    assert is_project_file(str(f), str(tmp_path)) is False


def test_pycache_excluded(tmp_path):
    f = tmp_path / "src" / "__pycache__" / "mod.pyc"
    assert is_project_file(str(f), str(tmp_path)) is False


def test_nested_src_is_included(tmp_path):
    f = tmp_path / "src" / "api" / "auth.py"
    assert is_project_file(str(f), str(tmp_path)) is True


def test_venv_without_dot_excluded(tmp_path):
    f = tmp_path / "venv" / "bin" / "python"
    assert is_project_file(str(f), str(tmp_path)) is False
