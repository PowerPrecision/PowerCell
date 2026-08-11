"""Testes unitários para utils/search_filters (helpers de pesquisa partilhados)."""
import re

from utils.search_filters import (
    create_accent_insensitive_regex,
    build_multiword_search_filter,
)


def _matches(term: str, text: str) -> bool:
    """Ajuda: o regex gerado (case/acentos) faz match no texto?"""
    pattern = create_accent_insensitive_regex(term)["$regex"]
    return re.search(pattern, text) is not None


class TestCreateAccentInsensitiveRegex:
    def test_empty_returns_case_insensitive_empty(self):
        assert create_accent_insensitive_regex("") == {"$regex": "", "$options": "i"}

    def test_matches_accented_and_case_variants(self):
        assert _matches("jose", "José")
        assert _matches("jose", "JOSE")
        assert _matches("JOSE", "josé")

    def test_cedilla_and_tilde(self):
        assert _matches("caca", "caça")
        assert _matches("joao", "João")

    def test_special_chars_are_escaped(self):
        # Um ponto no termo deve ser tratado literalmente, não como "qualquer char".
        pattern = create_accent_insensitive_regex("a.b")["$regex"]
        assert re.search(pattern, "a.b") is not None
        assert re.search(pattern, "axb") is None

    def test_digits_preserved(self):
        assert _matches("a1", "A1")


class TestBuildMultiwordSearchFilter:
    def test_empty_returns_empty_filter(self):
        assert build_multiword_search_filter("", "nome") == {}

    def test_single_word_maps_to_field_regex(self):
        f = build_multiword_search_filter("ana", "nome")
        assert "nome" in f and "$regex" in f["nome"]

    def test_multiword_uses_and(self):
        f = build_multiword_search_filter("vera teixeira", "client_name")
        assert "$and" in f
        assert len(f["$and"]) == 2
        assert all("client_name" in cond for cond in f["$and"])

    def test_multiword_regex_matches_reordered_name(self):
        f = build_multiword_search_filter("vera teixeira", "client_name")
        name = "Vera Lucia Da Costa Teixeira"
        assert all(re.search(cond["client_name"]["$regex"], name) for cond in f["$and"])
