"""Unit tests for skip/mark helpers on the ai-analyze path."""
from services.document_ai_analyze import (
    resolve_ai_category_from_doc_type,
    should_skip_ai_analysis,
)


class TestShouldSkipAiAnalysis:
    def test_none_metadata_not_skipped(self):
        assert should_skip_ai_analysis(None) is False

    def test_empty_metadata_not_skipped(self):
        assert should_skip_ai_analysis({}) is False

    def test_categorized_only_not_skipped(self):
        # is_categorized alone does not skip form-data extraction
        assert should_skip_ai_analysis({"is_categorized": True}) is False

    def test_ai_analyzed_true_is_skipped(self):
        assert should_skip_ai_analysis({"ai_analyzed": True}) is True

    def test_ai_analyzed_false_not_skipped(self):
        assert should_skip_ai_analysis({"ai_analyzed": False}) is False


class TestResolveAiCategoryFromDocType:
    def test_known_type_maps_to_folder(self):
        cat, sub = resolve_ai_category_from_doc_type("recibo_vencimento")
        assert cat == "Financeiros"
        assert "Recibo" in sub or "Vencimento" in sub

    def test_cc_maps_to_identificacao(self):
        cat, sub = resolve_ai_category_from_doc_type("cc")
        assert cat == "Identificação"
        assert sub == "Cc"

    def test_unknown_falls_back_to_outros(self):
        cat, sub = resolve_ai_category_from_doc_type("tipo_desconhecido_xyz")
        assert cat == "Outros"
        assert sub

    def test_empty_falls_back(self):
        cat, sub = resolve_ai_category_from_doc_type(None)
        assert cat == "Outros"
        assert sub == "Documento"
