from __future__ import annotations


def _utf16_len(char: str) -> int:
    """Return UTF-16 code unit count for a single Python character."""
    return 2 if ord(char) > 0xFFFF else 1


def offset_to_position(source: str, offset: int) -> dict[str, int]:
    """Convert a byte offset into an LSP {line, character} position.

    LSP character counts are UTF-16 code units, not Python character counts.
    """
    before = source[:offset]
    lines = before.split("\n")
    line = len(lines) - 1
    last_line = lines[-1]
    character = sum(_utf16_len(c) for c in last_line)
    return {"line": line, "character": character}


def position_to_offset(source: str, line: int, character: int) -> int:
    """Convert an LSP {line, character} position to a source byte offset.

    character is measured in UTF-16 code units.
    """
    lines = source.split("\n")
    if line >= len(lines):
        return len(source)
    base = sum(len(lines[i]) + 1 for i in range(line))  # +1 for \n
    target_line = lines[line]
    cu = 0
    for i, c in enumerate(target_line):
        if cu >= character:
            return base + i
        cu += _utf16_len(c)
    return base + len(target_line)
