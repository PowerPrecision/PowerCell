"""Unit tests for staff upload → portal REQUESTED fulfill."""
from __future__ import annotations

from services.document_portal_fulfill import (
    _category_variants,
    _norm,
    _score_pending_doc,
)


class TestPortalFulfillHelpers:
    def test_norm_accents(self):
        assert _norm("Cartão de Cidadão") == "cartao de cidadao"

    def test_category_variants_crm_folder(self):
        variants = _category_variants("Financeiros")
        assert "irs" in variants or "financeiros" in variants
        assert any("recibo" in v for v in variants) or "financeiros" in variants

    def test_category_variants_portal_key(self):
        variants = _category_variants("Cartao_Cidadao")
        assert "cartao cidadao" in variants or "cartao_cidadao" in variants

    def test_score_exact_category(self):
        doc = {"category": "IRS", "custom_label": "Declaração IRS"}
        score = _score_pending_doc(
            doc,
            category_variants=_category_variants("IRS"),
            filename="irs_2024.pdf",
        )
        assert score >= 10

    def test_score_label_in_filename(self):
        doc = {"category": "Outros", "custom_label": "Mapa de Créditos BPI"}
        score = _score_pending_doc(
            doc,
            category_variants=_category_variants("Outros"),
            filename="mapa_de_creditos_bpi.pdf",
        )
        assert score >= 3

    def test_score_no_match(self):
        doc = {"category": "Cartao_Cidadao", "custom_label": "CC"}
        score = _score_pending_doc(
            doc,
            category_variants=_category_variants("Plantas_Casa"),
            filename="planta.pdf",
        )
        assert score == 0
