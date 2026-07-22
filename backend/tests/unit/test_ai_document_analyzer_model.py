"""Unit tests for admin AI model key normalization on the ai-analyze path."""
import pytest


class TestNormalizeAdminModelKey:
    def test_underscore_admin_keys(self):
        from services.ai_document_analyzer import normalize_admin_model_key

        assert normalize_admin_model_key("gpt4o_mini") == "gpt-4o-mini"
        assert normalize_admin_model_key("gpt4o") == "gpt-4o"
        assert normalize_admin_model_key("gemini_flash") == "gemini-2.0-flash"

    def test_canonical_ids_passthrough(self):
        from services.ai_document_analyzer import normalize_admin_model_key

        assert normalize_admin_model_key("gpt-4o-mini") == "gpt-4o-mini"
        assert normalize_admin_model_key("gpt-4o") == "gpt-4o"

    def test_empty_falls_back_to_default(self):
        from services.ai_document_analyzer import normalize_admin_model_key

        assert normalize_admin_model_key(None) == "gpt-4o-mini"
        assert normalize_admin_model_key("") == "gpt-4o-mini"
        assert normalize_admin_model_key("  ") == "gpt-4o-mini"
        assert normalize_admin_model_key(None, default="gpt-4o") == "gpt-4o"

    def test_unknown_key_returned_as_is(self):
        from services.ai_document_analyzer import normalize_admin_model_key

        assert normalize_admin_model_key("custom-model-xyz") == "custom-model-xyz"
