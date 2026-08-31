"""Unit tests for staff upload → portal REQUESTED fulfill."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.document_portal_fulfill import (
    _category_variants,
    _norm,
    _score_pending_doc,
)
from services.document_upload import _auto_fulfill_portal_request


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


class TestAutoFulfillPortalRequest:
    """
    Testes de integração (com mocks à camada de DB) para
    `_auto_fulfill_portal_request` (services/document_upload.py), que expõe
    `fulfill_portal_requests_on_staff_upload` ao pipeline de upload.
    """

    @pytest.mark.asyncio
    async def test_success_flow_updates_status_and_document_id(self):
        """
        Fluxo de sucesso: quando o upload indica directamente o `document_id`
        do pedido portal a satisfazer, o pedido deve passar a `RECEIVED` e
        ficar associado ao `document_id` do ficheiro carregado.
        """
        mock_update_result = MagicMock(modified_count=1)
        mock_db = MagicMock()
        mock_db.documents.update_one = AsyncMock(return_value=mock_update_result)

        with patch("services.document_portal_fulfill.db", mock_db):
            result = await _auto_fulfill_portal_request(
                "proc-1",
                {
                    "category": "IRS",
                    "filename": "irs_2024.pdf",
                    "s3_path": "s3://bucket/proc-1/irs_2024.pdf",
                    "content_type": "application/pdf",
                    "file_size": 4096,
                    "document_id": "doc-req-42",
                },
                user={"id": "user-1", "name": "Equipa"},
            )

        assert result == {"fulfilled": 1, "document_ids": ["doc-req-42"]}

        mock_db.documents.update_one.assert_awaited_once()
        call_args = mock_db.documents.update_one.call_args
        query_filter, update = call_args.args
        assert query_filter["id"] == "doc-req-42"
        assert query_filter["process_id"] == "proc-1"
        assert update["$set"]["status"] == "RECEIVED"
        assert update["$set"]["document_id"] == "doc-req-42"

    @pytest.mark.asyncio
    async def test_filename_normalization_fallback_matches_pending_request(self):
        """
        Fallback de matching por nome de ficheiro: um upload sem categoria
        directa deve ainda casar com um pedido pendente através da
        normalização do alias no nome do ficheiro (regressão do bug em que
        "cartao_cidadao_joao.pdf" nunca batia com a chave "cartao_cidadao"
        por causa de acentos/underscores não normalizados).
        """
        pending_doc = {
            "id": "doc-req-99",
            "process_id": "proc-2",
            "status": "REQUESTED",
            "category": "Cartao_Cidadao",
            "custom_label": None,
        }

        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[pending_doc])
        mock_update_result = MagicMock(modified_count=1)

        mock_db = MagicMock()
        mock_db.documents.find = MagicMock(return_value=mock_cursor)
        mock_db.documents.update_one = AsyncMock(return_value=mock_update_result)
        mock_db.processes.find_one = AsyncMock(return_value=None)

        with patch("services.document_portal_fulfill.db", mock_db):
            result = await _auto_fulfill_portal_request(
                "proc-2",
                {
                    "category": None,
                    "filename": "cartao_cidadao_joao.pdf",
                    "s3_path": "s3://bucket/proc-2/cartao_cidadao_joao.pdf",
                    "content_type": "application/pdf",
                    "file_size": 2048,
                },
                user={"id": "user-1", "name": "Equipa"},
            )

        assert result == {"fulfilled": 1, "document_ids": ["doc-req-99"]}

        mock_db.documents.update_one.assert_awaited_once()
        call_args = mock_db.documents.update_one.call_args
        query_filter, update = call_args.args
        assert query_filter["id"] == "doc-req-99"
        assert update["$set"]["status"] == "RECEIVED"
        assert update["$set"]["document_id"] == "doc-req-99"
        assert update["$set"]["filename"] == "cartao_cidadao_joao.pdf"

    @pytest.mark.asyncio
    async def test_no_pending_requests_returns_zero_fulfilled(self):
        """Sem pedidos pendentes no processo, nada deve ser actualizado."""
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])

        mock_db = MagicMock()
        mock_db.documents.find = MagicMock(return_value=mock_cursor)
        mock_db.documents.update_one = AsyncMock()

        with patch("services.document_portal_fulfill.db", mock_db):
            result = await _auto_fulfill_portal_request(
                "proc-3",
                {
                    "category": "Outros",
                    "filename": "documento_qualquer.pdf",
                },
                user={"id": "user-1", "name": "Equipa"},
            )

        assert result == {"fulfilled": 0, "document_ids": []}
        mock_db.documents.update_one.assert_not_awaited()
