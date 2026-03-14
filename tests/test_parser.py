import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_python_class_and_methods():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_py.py"))
    names = [s.name for s in symbols]
    assert "UserService" in names
    assert "create" in names
    assert "find_by_email" in names


def test_parse_python_module_functions():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_py.py"))
    names = [s.name for s in symbols]
    assert "validate_email" in names
    assert "validate_password" in names


def test_parse_python_method_has_parent():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_py.py"))
    method = next(s for s in symbols if s.name == "create")
    assert method.parent == "UserService"
    assert method.symbol_type in ("method", "function")


def test_parse_python_function_no_parent():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_py.py"))
    fn = next(s for s in symbols if s.name == "validate_email")
    assert fn.parent is None


def test_parse_python_signature_format():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_py.py"))
    fn = next(s for s in symbols if s.name == "validate_email")
    assert fn.signature.startswith("def validate_email")
    assert "email" in fn.signature


def test_parse_typescript_class():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_ts.ts"))
    names = [s.name for s in symbols]
    assert "AuthService" in names


def test_parse_typescript_interface():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_ts.ts"))
    names = [s.name for s in symbols]
    assert "User" in names


def test_parse_typescript_type_alias():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_ts.ts"))
    names = [s.name for s in symbols]
    assert "UserId" in names


def test_parse_typescript_arrow_function():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_ts.ts"))
    names = [s.name for s in symbols]
    assert "hashPassword" in names


def test_parse_syntax_error_returns_empty_or_partial():
    from codebase_context.parser import parse_file
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
        f.write("def broken(:\n    pass\n")
        tmp = f.name
    try:
        result = parse_file(tmp)
        assert isinstance(result, list)
        # Should not raise — may return [] or partial results
    finally:
        os.unlink(tmp)


def test_parse_c_free_functions():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_c.c"))
    names = [s.name for s in symbols]
    assert "validate_email" in names
    assert "validate_password" in names


def test_parse_c_function_language():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_c.c"))
    fn = next(s for s in symbols if s.name == "validate_email")
    assert fn.symbol_type == "function"
    assert fn.language == "c"


def test_parse_c_struct():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_c.c"))
    structs = [s for s in symbols if s.symbol_type == "class"]
    assert any(s.name == "UserService" for s in structs)


def test_parse_cpp_free_functions():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_cpp.cpp"))
    names = [s.name for s in symbols]
    assert "validate_email" in names
    assert "hash_password" in names


def test_parse_cpp_class_and_methods():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_cpp.cpp"))
    cls = next(s for s in symbols if s.name == "AuthService")
    assert cls.symbol_type == "class"
    assert cls.language == "cpp"
    methods = [s for s in symbols if s.parent == "AuthService"]
    assert any(m.name == "login" for m in methods)
    assert any(m.name == "logout" for m in methods)


def test_parse_cpp_method_has_parent():
    from codebase_context.parser import parse_file
    symbols = parse_file(str(FIXTURES / "sample_cpp.cpp"))
    login = next(s for s in symbols if s.name == "login")
    assert login.parent == "AuthService"
    assert login.symbol_type == "method"


def test_unsupported_extension_raises():
    from codebase_context.parser import parse_file, UnsupportedLanguageError
    with pytest.raises(UnsupportedLanguageError):
        parse_file("file.rb")
