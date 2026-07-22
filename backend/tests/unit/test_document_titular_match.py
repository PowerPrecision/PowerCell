"""Unit tests for titular 1/2 AI match helpers."""
from services.document_titular_match import (
    build_titular_identity_snapshot,
    resolve_titular_match,
    score_extracted_against_titular,
)


def _t1():
    return build_titular_identity_snapshot(
        label="titular1",
        client_id="c1",
        name="Joao Silva",
        personal={"nif": "123456789", "documento_id": "12345678"},
    )


def _t2():
    return build_titular_identity_snapshot(
        label="titular2",
        client_id="c2",
        name="Maria Costa",
        personal={"nif": "987654321", "documento_id": "87654321"},
        titular2_data={"name": "Maria Costa"},
    )


class TestResolveTitularMatch:
    def test_single_titular_defaults_to_titular1(self):
        m = resolve_titular_match({"nif": "123456789"}, _t1(), None)
        assert m["match"] == "titular1"
        assert m["needs_user_choice"] is False

    def test_clear_nif_match_titular2(self):
        m = resolve_titular_match({"nif": "987654321"}, _t1(), _t2())
        assert m["match"] == "titular2"
        assert m["confidence"] == "high"
        assert m["needs_user_choice"] is False
        assert m["suggested_client_id"] == "c2"

    def test_clear_nif_match_titular1(self):
        m = resolve_titular_match({"nif": "123456789"}, _t1(), _t2())
        assert m["match"] == "titular1"
        assert m["needs_user_choice"] is False

    def test_no_identity_asks_user_when_two_titulares(self):
        m = resolve_titular_match({"monthly_income": 1500}, _t1(), _t2())
        assert m["match"] == "ambiguous"
        assert m["needs_user_choice"] is True

    def test_name_match_titular1(self):
        m = resolve_titular_match({"nome": "Joao Silva"}, _t1(), _t2())
        assert m["match"] == "titular1"
        assert m["score_titular1"] >= 2


class TestScoreExtracted:
    def test_nif_scores_three(self):
        assert score_extracted_against_titular({"nif": "123456789"}, _t1()) == 3
