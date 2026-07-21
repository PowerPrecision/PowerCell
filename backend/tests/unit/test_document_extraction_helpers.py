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
import pytest
from fastapi import HTTPException


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
