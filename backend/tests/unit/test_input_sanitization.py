"""Unit tests for input sanitization helpers (Pacote FF — ReDoS)."""
import re

from utils.input_sanitization import escape_regex


def test_escape_regex_escapes_metacharacters():
    escaped = escape_regex("a.b+c*(d)")
    assert escaped == re.escape("a.b+c*(d)")
    assert re.search(escaped, "a.b+c*(d)")
    assert re.search(escaped, "axb+c*(d)") is None


def test_escape_regex_blocks_redos_payload():
    payload = "(a+)+$"
    escaped = escape_regex(payload)
    assert "(" not in escaped or "\\(" in escaped
    assert escaped == re.escape(payload)
    # Literal match only — the nested quantifiers are inert.
    assert re.fullmatch(escaped, payload)
    assert re.fullmatch(escaped, "aaaaaaaa") is None


def test_escape_regex_empty_and_none():
    assert escape_regex("") == ""
    assert escape_regex(None) == ""


def test_escape_regex_non_string():
    assert escape_regex(123) == "123"
    assert escape_regex(["a.b"]) == re.escape("['a.b']")
