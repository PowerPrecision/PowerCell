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


def test_sanitize_html_drops_script_contents():
    from utils.input_sanitization import (
        sanitize_html,
        sanitize_email_signature,
    )

    html = sanitize_html(
        'Olá<script>alert(1)</script><b>Mundo</b>',
        allow_basic_formatting=True,
    )
    assert "<script>" not in html.lower()
    assert "alert(1)" not in html
    assert "Mundo" in html

    signature = sanitize_email_signature(
        'Olá<script>alert(1)</script><b>Mundo</b>',
    )
    assert signature is not None
    assert "alert(1)" not in signature
    assert "<b>Mundo</b>" in signature or "Mundo" in signature
