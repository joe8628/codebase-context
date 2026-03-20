from codebase_context.lsp.positions import offset_to_position, position_to_offset


def test_offset_to_position_first_line():
    src = "hello world"
    assert offset_to_position(src, 5) == {"line": 0, "character": 5}


def test_offset_to_position_second_line():
    src = "line1\nline2"
    assert offset_to_position(src, 6) == {"line": 1, "character": 0}


def test_offset_to_position_end_of_first_line():
    src = "abc\ndef"
    assert offset_to_position(src, 3) == {"line": 0, "character": 3}


def test_position_to_offset_first_line():
    src = "hello world"
    assert position_to_offset(src, 0, 5) == 5


def test_position_to_offset_second_line():
    src = "line1\nline2"
    assert position_to_offset(src, 1, 0) == 6


def test_roundtrip():
    src = "foo\nbar\nbaz"
    for offset in [0, 1, 4, 5, 8]:
        pos = offset_to_position(src, offset)
        assert position_to_offset(src, pos["line"], pos["character"]) == offset


def test_multibyte_emoji_counts_as_two_utf16_units():
    # U+1F600 is above U+FFFF → 2 UTF-16 code units
    # string: "x" + emoji + "y"  (3 Python chars, 4 UTF-16 code units)
    src = "x\U0001F600y"
    pos = offset_to_position(src, 2)  # position of "y"
    assert pos == {"line": 0, "character": 3}  # x=1, emoji=2 → y at character 3


def test_position_past_end_of_line():
    src = "abc"
    result = position_to_offset(src, 0, 100)
    assert result == 3
