"""Tree-sitter abstraction: parses source files into Symbol data structures."""

from __future__ import annotations

import importlib
import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import tree_sitter
from tree_sitter import Language, Parser

from codebase_context.config import LANGUAGES

logger = logging.getLogger(__name__)


class UnsupportedLanguageError(ValueError):
    """Raised when a file extension is not in the LANGUAGES registry."""


@dataclass
class Symbol:
    name:        str
    symbol_type: str        # "function" | "class" | "method" | "interface" | "type"
    start_line:  int        # 0-indexed
    end_line:    int        # 0-indexed, inclusive
    source:      str        # full source text of this symbol
    signature:   str        # compact one-line signature for repo map
    docstring:   str | None
    calls:       list[str]  # names of functions/methods called within this symbol
    parent:      str | None # class name if this is a method
    filepath:    str
    language:    str


@lru_cache(maxsize=16)
def _load_language(extension: str) -> tuple[Language, dict]:
    """Load and cache a tree-sitter Language for the given file extension."""
    config = LANGUAGES[extension]
    module = importlib.import_module(config["tree_sitter_module"])
    if "tree_sitter_attr" in config:
        lang_fn = getattr(module, config["tree_sitter_attr"])
    else:
        lang_fn = module.language
    language = Language(lang_fn())
    return language, config


def _get_node_text(node, source_bytes: bytes) -> str:
    return source_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _extract_docstring(node, source_bytes: bytes, lang_name: str) -> str | None:
    """Extract docstring from a function/class body node."""
    if lang_name == "python":
        # Look for expression_statement containing a string as first statement in block
        body = None
        for child in node.children:
            if child.type == "block":
                body = child
                break
        if body is None:
            return None
        for child in body.children:
            if child.type == "expression_statement":
                for inner in child.children:
                    if inner.type in ("string", "concatenated_string"):
                        text = _get_node_text(inner, source_bytes)
                        # Strip quotes
                        if text.startswith('"""') and text.endswith('"""'):
                            return text[3:-3].strip()
                        if text.startswith("'''") and text.endswith("'''"):
                            return text[3:-3].strip()
                        if text.startswith('"') and text.endswith('"'):
                            return text[1:-1].strip()
                        if text.startswith("'") and text.endswith("'"):
                            return text[1:-1].strip()
                        return text.strip()
                break  # Only first statement
    return None


def extract_signature(
    node,
    source_bytes: bytes,
    config: dict,
    sym_type: str,
    name: str,
    parent_class: str | None,
) -> str:
    """Return a compact one-line signature for the symbol."""
    source = _get_node_text(node, source_bytes)
    first_line = source.split("\n")[0].rstrip()

    if sym_type == "class":
        # Count methods in the body
        method_count = 0
        for child in node.children:
            if child.type in ("block", "class_body", "field_declaration_list"):
                for sub in child.children:
                    if sub.type in ("function_definition", "method_definition"):
                        method_count += 1
        return f"class {name} ({method_count} methods)"

    if sym_type in ("interface", "type"):
        # Return first line stripped of trailing {
        return first_line.rstrip(" {").rstrip()

    # function / method: return the first line (declaration line)
    return first_line


def extract_calls(node, source_bytes: bytes) -> list[str]:
    """Walk subtree to find all call or call_expression nodes. Return sorted unique names."""
    calls: set[str] = set()

    def walk(n):
        if n.type in ("call", "call_expression"):
            # Python: first child is the function/attribute
            # TypeScript: function field or first child
            func_node = None
            # Try named field "function"
            for child in n.children:
                if child.type not in ("argument_list", "arguments", "(", ")", ","):
                    func_node = child
                    break

            if func_node is not None:
                name = _get_call_name(func_node, source_bytes)
                if name:
                    calls.add(name)

        for child in n.children:
            walk(child)

    walk(node)
    return sorted(calls)


def _extract_declarator_name(node, source_bytes: bytes) -> str | None:
    """Resolve a C/C++ declarator chain to find the function or method name.

    C/C++ function_definition nodes don't have a 'name' field; the name is
    nested inside: declarator → function_declarator → declarator → identifier.
    """
    declarator = node.child_by_field_name("declarator")
    while declarator is not None:
        if declarator.type in ("identifier", "field_identifier", "type_identifier"):
            return _get_node_text(declarator, source_bytes)
        declarator = declarator.child_by_field_name("declarator")
    return None


def _get_call_name(node, source_bytes: bytes) -> str | None:
    """Extract the function name from a call's function node."""
    if node.type == "identifier":
        return _get_node_text(node, source_bytes)
    if node.type == "attribute":
        # Get the attribute name (last identifier after the dot)
        for child in reversed(node.children):
            if child.type == "identifier":
                return _get_node_text(child, source_bytes)
    if node.type == "member_expression":
        # TypeScript member expression: obj.method
        prop = node.child_by_field_name("property")
        if prop:
            return _get_node_text(prop, source_bytes)
    return None


def _extract_class_methods(
    class_node,
    source_bytes: bytes,
    config: dict,
    filepath: str,
    language_name: str,
    class_name: str,
) -> list[Symbol]:
    """Recurse into a class body to extract method symbols."""
    methods: list[Symbol] = []
    method_types = config.get("method_types", config.get("node_types", []))

    body = None
    for child in class_node.children:
        if child.type in ("block", "class_body", "field_declaration_list"):
            body = child
            break

    if body is None:
        return methods

    for child in body.children:
        if child.type in ("function_definition", "method_definition"):
            name_node = child.child_by_field_name("name")
            if name_node is not None:
                name = _get_node_text(name_node, source_bytes)
            else:
                name = _extract_declarator_name(child, source_bytes)
            if name is None:
                continue
            sym_type = "method"
            source = _get_node_text(child, source_bytes)
            sig = extract_signature(child, source_bytes, config, sym_type, name, class_name)
            docstring = _extract_docstring(child, source_bytes, language_name)
            calls = extract_calls(child, source_bytes)
            methods.append(Symbol(
                name=name,
                symbol_type=sym_type,
                start_line=child.start_point[0],
                end_line=child.end_point[0],
                source=source,
                signature=sig,
                docstring=docstring,
                calls=calls,
                parent=class_name,
                filepath=filepath,
                language=language_name,
            ))

    return methods


def parse_file(filepath: str) -> list[Symbol]:
    """Parse a source file and return a list of Symbol objects.

    Raises UnsupportedLanguageError if the file extension is not in LANGUAGES.
    Returns [] on parse errors (logs a warning).
    """
    ext = Path(filepath).suffix.lower()
    if ext not in LANGUAGES:
        raise UnsupportedLanguageError(
            f"Unsupported file extension: {ext!r}. "
            f"Supported: {list(LANGUAGES.keys())}"
        )

    try:
        source_bytes = Path(filepath).read_bytes()
    except OSError as exc:
        logger.warning("Cannot read %s: %s", filepath, exc)
        return []

    try:
        language, config = _load_language(ext)
        parser = Parser(language)
        tree = parser.parse(source_bytes)
    except Exception as exc:
        logger.warning("Failed to create parser for %s: %s", filepath, exc)
        return []

    root = tree.root_node
    language_name = config["name"]
    node_types = config["node_types"]

    symbols: list[Symbol] = []

    def process_node(node, parent_class: str | None = None) -> None:
        if node.type not in node_types:
            return

        # --- arrow_function: only process when it is a direct child of variable_declarator ---
        if node.type == "arrow_function":
            parent = node.parent
            if parent is None or parent.type != "variable_declarator":
                return
            name_node = parent.child_by_field_name("name")
            if name_node is None:
                return
            name = _get_node_text(name_node, source_bytes)
            sym_type = "function"
            source = _get_node_text(node, source_bytes)
            sig = extract_signature(node, source_bytes, config, sym_type, name, None)
            docstring = None
            calls = extract_calls(node, source_bytes)
            symbols.append(Symbol(
                name=name,
                symbol_type=sym_type,
                start_line=node.start_point[0],
                end_line=node.end_point[0],
                source=source,
                signature=sig,
                docstring=docstring,
                calls=calls,
                parent=None,
                filepath=filepath,
                language=language_name,
            ))
            return

        # --- class ---
        if node.type in ("class_definition", "class_declaration", "class_specifier", "struct_specifier"):
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            name = _get_node_text(name_node, source_bytes)
            sym_type = "class"
            source = _get_node_text(node, source_bytes)
            sig = extract_signature(node, source_bytes, config, sym_type, name, None)
            docstring = _extract_docstring(node, source_bytes, language_name)
            calls = extract_calls(node, source_bytes)
            symbols.append(Symbol(
                name=name,
                symbol_type=sym_type,
                start_line=node.start_point[0],
                end_line=node.end_point[0],
                source=source,
                signature=sig,
                docstring=docstring,
                calls=calls,
                parent=None,
                filepath=filepath,
                language=language_name,
            ))
            # Recurse into class body to find methods
            methods = _extract_class_methods(
                node, source_bytes, config, filepath, language_name, name
            )
            symbols.extend(methods)
            return

        # --- interface ---
        if node.type == "interface_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            name = _get_node_text(name_node, source_bytes)
            sym_type = "interface"
            source = _get_node_text(node, source_bytes)
            sig = extract_signature(node, source_bytes, config, sym_type, name, None)
            symbols.append(Symbol(
                name=name,
                symbol_type=sym_type,
                start_line=node.start_point[0],
                end_line=node.end_point[0],
                source=source,
                signature=sig,
                docstring=None,
                calls=[],
                parent=None,
                filepath=filepath,
                language=language_name,
            ))
            return

        # --- type alias ---
        if node.type == "type_alias_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            name = _get_node_text(name_node, source_bytes)
            sym_type = "type"
            source = _get_node_text(node, source_bytes)
            sig = extract_signature(node, source_bytes, config, sym_type, name, None)
            symbols.append(Symbol(
                name=name,
                symbol_type=sym_type,
                start_line=node.start_point[0],
                end_line=node.end_point[0],
                source=source,
                signature=sig,
                docstring=None,
                calls=[],
                parent=None,
                filepath=filepath,
                language=language_name,
            ))
            return

        # --- function / method_definition ---
        if node.type in (
            "function_definition",
            "function_declaration",
            "method_definition",
        ):
            name_node = node.child_by_field_name("name")
            if name_node is not None:
                name = _get_node_text(name_node, source_bytes)
            else:
                name = _extract_declarator_name(node, source_bytes)
            if name is None:
                return
            # method_definition at top level (not inside class body) is still a function
            sym_type = "function"
            source = _get_node_text(node, source_bytes)
            sig = extract_signature(node, source_bytes, config, sym_type, name, None)
            docstring = _extract_docstring(node, source_bytes, language_name)
            calls = extract_calls(node, source_bytes)
            symbols.append(Symbol(
                name=name,
                symbol_type=sym_type,
                start_line=node.start_point[0],
                end_line=node.end_point[0],
                source=source,
                signature=sig,
                docstring=docstring,
                calls=calls,
                parent=None,
                filepath=filepath,
                language=language_name,
            ))
            return

    def walk_top_level(node) -> None:
        """Walk only top-level nodes (don't recurse into class bodies here)."""
        for child in node.children:
            process_node(child)
            # For lexical/variable declarations containing arrow functions
            if child.type in ("lexical_declaration", "variable_declaration"):
                for sub in child.children:
                    if sub.type == "variable_declarator":
                        for inner in sub.children:
                            if inner.type == "arrow_function":
                                process_node(inner)

    try:
        walk_top_level(root)
    except Exception as exc:
        logger.warning("Error walking AST for %s: %s", filepath, exc)
        return []

    return symbols
