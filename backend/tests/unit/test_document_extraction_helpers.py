"""Unit tests for document_* extraction helpers (Batch 1)."""
from datetime import datetime, timezone, timedelta

from services.document_filenames import (
    sanitize_for_log,
    normalize_filename,
    is_image_file,
    generate_smart_filename,
)
from services.document_expiring_dashboard import (
    build_expiry_doc_query,
    build_expiring_processes_query,
    filter_docs_by_authorized_and_search,
    compute_expiry_stats,
    group_expiring_docs_by_client,
    sort_clients_by_urgency,
)
from services.document_constants import DOCUMENT_CATEGORY_MAP, ERROR_CLIENT_NOT_FOUND
from services.document_portal_request import (
    normalize_portal_category,
    coerce_optional_str,
    build_portal_duplicate_query,
    build_portal_document_record,
)
from services.document_process_resolve import (
    build_s3_valid_prefixes,
    assert_s3_file_belongs_to_process,
)
from services.document_auto_categorize import (
    should_run_ocr_for_category,
    build_auto_cat_metadata,
)
from services.document_portal_request import serialize_portal_document
from services.document_upload_conflict import suggest_alternate_filenames
import pytest
from fastapi import HTTPException
from unittest.mock import patch


class TestDocumentFilenames:
    def test_sanitize_for_log(self):
        assert sanitize_for_log("") == "[empty]"
        assert "\n" not in sanitize_for_log("a\nb\rc")
        assert len(sanitize_for_log("x" * 100, max_length=10)) == 10

    def test_normalize_filename_strips_dangerous(self):
        assert normalize_filename('foo/bar:baz.pdf') == "foobarbaz.pdf"
        assert normalize_filename("").endswith(".pdf")

    def test_is_image_file(self):
        assert is_image_file("a.JPG") is True
        assert is_image_file("a.pdf") is False
        assert is_image_file("x", "image/png") is True

    def test_generate_smart_filename(self):
        name = generate_smart_filename(
            "Identificação", "CC", "João Silva", "2028-03-15", "PDF",
        )
        assert name == "Identificacao_CC_JoaoSilva_2028-03-15.pdf"


class TestExpiringDashboardHelpers:
    def test_build_expiry_queries(self):
        today = datetime(2026, 7, 21, tzinfo=timezone.utc)
        q = build_expiry_doc_query(today, 60, "critical")
        assert q["expiry_date"]["$lt"] == "2026-07-28"
        pq = build_expiring_processes_query(
            ["p1"], is_management=False, user_id="u1",
        )
        assert any("assigned_consultor_id" in c for c in pq["$or"])

    def test_filter_and_stats(self):
        today = datetime(2026, 7, 21, tzinfo=timezone.utc)
        process_map = {"p1": {"id": "p1", "client_name": "Ana"}, "p2": {"id": "p2", "client_name": "Bob"}}
        docs = [
            {"process_id": "p1", "expiry_date": "2026-07-22"},
            {"process_id": "p2", "expiry_date": "2026-08-20"},
            {"process_id": "p9", "expiry_date": "2026-07-22"},
        ]
        filtered = filter_docs_by_authorized_and_search(docs, process_map, search="ana")
        assert len(filtered) == 1 and filtered[0]["process_id"] == "p1"
        stats = compute_expiry_stats(
            [
                {"expiry_date": "2026-07-22"},
                {"expiry_date": "2026-08-01"},
                {"expiry_date": "2026-09-01"},
            ],
            today,
        )
        assert stats["critical"] == 1
        assert stats["high"] == 1
        assert stats["medium"] == 1
        assert stats["total"] == 3

    def test_group_and_sort(self):
        today = datetime(2026, 7, 21, tzinfo=timezone.utc)
        process_map = {
            "p1": {"id": "p1", "client_name": "A", "assigned_consultor_id": "c1"},
            "p2": {"id": "p2", "client_name": "B", "consultor_id": "c2"},
        }
        docs = [
            {"process_id": "p1", "expiry_date": "2026-07-22", "filename": "a.pdf", "id": "d1"},
            {"process_id": "p2", "expiry_date": "2026-09-01", "filename": "b.pdf", "id": "d2"},
        ]
        clients = group_expiring_docs_by_client(
            docs, process_map, {"c1": "Ana", "c2": "Bob"}, today,
        )
        assert clients[0]["process_id"] == "p1"
        assert clients[0]["critical_count"] == 1
        assert clients[0]["consultor_name"] == "Ana"
        sorted_c = sort_clients_by_urgency([
            {"critical_count": 0, "high_count": 2, "medium_count": 0},
            {"critical_count": 1, "high_count": 0, "medium_count": 0},
        ])
        assert sorted_c[0]["critical_count"] == 1


class TestDocumentConstants:
    def test_category_map_and_errors(self):
        assert "Cartao_Cidadao" in DOCUMENT_CATEGORY_MAP
        assert ERROR_CLIENT_NOT_FOUND


class TestPortalRequestHelpers:
    def test_normalize_and_coerce(self):
        assert normalize_portal_category({"value": "IRS"}) == "IRS"
        assert normalize_portal_category("UnknownCat") == "Outros"
        assert coerce_optional_str({"label": "x"}) == "x"
        assert coerce_optional_str(None) is None

    def test_build_duplicate_query_and_record(self):
        q = build_portal_duplicate_query("p1", "IRS")
        assert q["process_id"] == "p1"
        assert "REQUESTED" in q["status"]["$in"]
        doc = build_portal_document_record(
            process_id="p1",
            category="IRS",
            notes="n",
            custom_label=None,
            user={"id": "u1", "name": "Ana"},
        )
        assert doc["status"] == "REQUESTED"
        assert doc["source"] == "admin_request"
        assert doc["requested_by"] == "u1"


class TestS3AccessHelpers:
    def test_build_prefixes_with_s3_folder(self):
        prefixes = build_s3_valid_prefixes({"s3_folder": "Documentação Clientes/Foo/"})
        assert prefixes == ["Documentação Clientes/Foo/"]

    def test_assert_belongs_ok_and_denied(self):
        process = {"s3_folder": "Documentação Clientes/Foo"}
        assert_s3_file_belongs_to_process(
            "Documentação Clientes/Foo/a.pdf", process
        )
        with pytest.raises(HTTPException) as exc:
            assert_s3_file_belongs_to_process("other/a.pdf", process)
        assert exc.value.status_code == 403


class TestAutoCategorizeHelpers:
    def test_should_run_ocr(self):
        assert should_run_ocr_for_category("Identificação") is True
        assert should_run_ocr_for_category("Outros") is False
        assert should_run_ocr_for_category("doc_cc_scan") is True

    def test_build_auto_cat_metadata(self):
        meta = build_auto_cat_metadata(
            doc_id="d1",
            process_id="p1",
            client_name="Ana",
            s3_path="a/b.pdf",
            filename="b.pdf",
            result={"category": "Fiscal", "confidence": 0.9, "tags": [], "summary": "x"},
            extracted_text="hello",
            extracted_data={"nif": "123"},
            file_content=b"%PDF",
            now="2026-01-01T00:00:00+00:00",
        )
        assert meta["is_categorized"] is True
        assert meta["ai_category"] == "Fiscal"
        assert meta["extracted_data"]["nif"] == "123"


class TestPortalSerializeAndConflictSuggest:
    def test_serialize_portal_document(self):
        row = serialize_portal_document(
            {
                "id": "d1",
                "process_id": "p1",
                "category": {"value": "IRS"},
                "status": "REQUESTED",
                "created_at": "2026-01-01",
            }
        )
        assert row["category"] == "IRS"
        assert row["category_label"]

    def test_suggest_alternate_filenames(self):
        with patch(
            "services.document_upload_conflict.s3_service.file_exists",
            side_effect=lambda p: p.endswith("_2.pdf"),
        ):
            suggested = suggest_alternate_filenames(
                base_path="base",
                safe_category="Outros",
                normalized="doc.pdf",
            )
        assert suggested
        assert suggested[0]["filename"] == "doc_3.pdf"


class TestMoveHelpers:
    def test_build_move_target_path(self):
        from services.document_move import build_move_target_path

        path, cat, name = build_move_target_path(
            base_path="base",
            source_path="base/Old/a.pdf",
            target_category="Financeiros",
            target_filename=None,
        )
        assert path == "base/Financeiros/a.pdf"
        assert cat == "Financeiros"
        assert name == "a.pdf"


class TestAiAnalyzeHelpers:
    def test_build_existing_data_for_ai_compare(self):
        from services.document_ai_analyze import build_existing_data_for_ai_compare

        data = build_existing_data_for_ai_compare(
            {
                "client_name": "Ana",
                "personal_data": {"nif": "123456789"},
                "financial_data": {"rendimento_mensal": 1000},
                "real_estate_data": {"valor_imovel": 200000},
            }
        )
        assert data["nif"] == "123456789"
        assert data["rendimento_mensal"] == 1000
        assert data["valor_imovel"] == 200000

    def test_process_ai_analyze_results(self):
        from services.document_ai_analyze import process_ai_analyze_results

        extracted, conflicts, types = process_ai_analyze_results(
            {
                "auto_fill_suggestions": {
                    "nif": {
                        "value": "111",
                        "type": "override",
                        "current_value": "222",
                        "source": "cc",
                    }
                },
                "comparison": {"empty_fields": [{"field": "email", "suggested_value": "a@b.c"}]},
                "documents_analyzed": [
                    {"tipo_documento": "cc", "file_name": "x.pdf", "confianca": 0.9}
                ],
            },
            [{"name": "x.pdf", "source_path": "s3/x.pdf"}],
        )
        assert extracted["nif"] == "111"
        assert extracted["email"] == "a@b.c"
        assert conflicts[0]["field"] == "nif"
        assert types[0]["type"] == "cc"
        assert types[0]["source_path"] == "s3/x.pdf"

    def test_document_type_folders_defaults(self):
        from services.document_ai_analyze import DOCUMENT_TYPE_FOLDERS

        assert DOCUMENT_TYPE_FOLDERS["irs"] == "Financeiros"
        assert DOCUMENT_TYPE_FOLDERS["default"] == "Outros"
