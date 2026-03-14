import hashlib
from pathlib import Path
from codebase_context.parser import Symbol


def make_symbol(name="my_func", sym_type="function", start=0, end=5,
                source="def my_func(): pass", parent=None):
    return Symbol(
        name=name,
        symbol_type=sym_type,
        start_line=start,
        end_line=end,
        source=source,
        signature=f"def {name}()",
        docstring=None,
        calls=[],
        parent=parent,
        filepath="src/utils.py",
        language="python",
    )


def test_chunk_has_context_prefix():
    from codebase_context.chunker import build_chunks
    sym = make_symbol()
    chunks = build_chunks([sym], "src/utils.py")
    assert len(chunks) == 1
    assert "# filepath: src/utils.py" in chunks[0].text
    assert "def my_func()" in chunks[0].text


def test_chunk_id_is_deterministic():
    from codebase_context.chunker import chunk_id
    id1 = chunk_id("src/utils.py", "my_func", 10)
    id2 = chunk_id("src/utils.py", "my_func", 10)
    assert id1 == id2


def test_chunk_id_differs_for_different_inputs():
    from codebase_context.chunker import chunk_id
    id1 = chunk_id("src/utils.py", "my_func", 10)
    id2 = chunk_id("src/utils.py", "other_func", 10)
    assert id1 != id2


def test_chunk_metadata_contains_required_fields():
    from codebase_context.chunker import build_chunks
    sym = make_symbol(name="create", sym_type="method", start=10, end=20, parent="UserService")
    chunks = build_chunks([sym], "src/api.py")
    meta = chunks[0].metadata
    assert meta["filepath"] == "src/api.py"
    assert meta["symbol_name"] == "create"
    assert meta["symbol_type"] == "method"
    assert meta["start_line"] == 10
    assert meta["end_line"] == 20
    assert meta["language"] == "python"
    assert meta["parent_class"] == "UserService"


def test_long_chunk_truncated():
    from codebase_context.chunker import build_chunks
    from codebase_context.config import MAX_CHUNK_TOKENS
    from codebase_context.utils import count_tokens
    long_source = "\n".join([f"    x_{i} = {i}" for i in range(1000)])
    sym = make_symbol(source=f"def big():\n{long_source}")
    chunks = build_chunks([sym], "src/big.py")
    assert count_tokens(chunks[0].text) <= MAX_CHUNK_TOKENS + 20  # small tolerance


def test_chunk_prefix_includes_parent_class():
    from codebase_context.chunker import build_chunks
    sym = make_symbol(name="save", sym_type="method", parent="UserService")
    chunks = build_chunks([sym], "src/service.py")
    assert "class: UserService" in chunks[0].text
