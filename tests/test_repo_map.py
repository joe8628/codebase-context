import pytest
from codebase_context.parser import Symbol


def make_sym(name, sym_type, parent=None, sig="def foo()", filepath="src/utils.py", lang="python"):
    return Symbol(
        name=name, symbol_type=sym_type, start_line=0, end_line=5,
        source="def foo(): pass", signature=sig, docstring=None,
        calls=[], parent=parent, filepath=filepath, language=lang,
    )


def test_repo_map_includes_file_header():
    from codebase_context.repo_map import generate_repo_map
    symbols_by_file = {
        "src/utils.py": [make_sym("validate_email", "function", sig="def validate_email(email: str) -> str")],
    }
    result = generate_repo_map(".", symbols_by_file)
    assert "## src/utils.py" in result


def test_repo_map_function_has_plus_prefix():
    from codebase_context.repo_map import generate_repo_map
    symbols_by_file = {
        "src/utils.py": [make_sym("validate_email", "function", sig="def validate_email(email: str) -> str")],
    }
    result = generate_repo_map(".", symbols_by_file)
    assert "  + validate_email" in result


def test_repo_map_methods_indented_under_class():
    from codebase_context.repo_map import generate_repo_map
    symbols_by_file = {
        "src/service.py": [
            make_sym("UserService", "class", sig="class UserService (2 methods)"),
            make_sym("create", "method", parent="UserService", sig="def create(self, email: str) -> User"),
            make_sym("delete", "method", parent="UserService", sig="def delete(self, id: int) -> bool"),
        ],
    }
    result = generate_repo_map(".", symbols_by_file)
    assert "  class UserService:" in result
    assert "    + create" in result
    assert "    + delete" in result


def test_repo_map_header_contains_stats():
    from codebase_context.repo_map import generate_repo_map
    symbols_by_file = {
        "src/utils.py": [make_sym("foo", "function")],
        "src/other.py": [make_sym("bar", "function")],
    }
    result = generate_repo_map(".", symbols_by_file)
    assert "Files: 2" in result
    assert "Symbols: 2" in result


def test_repo_map_token_estimate_under_target():
    from codebase_context.repo_map import generate_repo_map, estimate_tokens
    symbols_by_file = {
        f"src/module_{i}.py": [make_sym(f"func_{i}", "function", sig=f"def func_{i}()")]
        for i in range(500)
    }
    result = generate_repo_map(".", symbols_by_file)
    tokens = estimate_tokens(result)
    assert tokens < 8000, f"Repo map too large: {tokens} tokens"


def test_files_sorted_by_depth_then_alpha():
    from codebase_context.repo_map import generate_repo_map
    symbols_by_file = {
        "src/api/auth.py": [make_sym("login", "function")],
        "src/utils.py": [make_sym("helper", "function")],
        "main.py": [make_sym("main", "function")],
    }
    result = generate_repo_map(".", symbols_by_file)
    pos_main = result.index("main.py")
    pos_utils = result.index("src/utils.py")
    pos_auth = result.index("src/api/auth.py")
    assert pos_main < pos_utils
    assert pos_utils < pos_auth
