"""Unit tests for process_indexing / process_create / process_update helpers."""
from models.auth import UserRole
from services.process_indexing import (
    compute_next_workflow_status,
    build_indexacao_update_set,
    collect_assigned_user_ids,
)
from services.process_create import (
    build_staff_process_doc,
    apply_creator_role_assignment,
)
from services.process_update import (
    merge_nested_process_section,
    build_role_update_permissions,
)


class TestComputeNextWorkflowStatus:
    def test_advances_to_next(self):
        assert compute_next_workflow_status("a", ["a", "b", "c"]) == "b"

    def test_last_returns_none(self):
        assert compute_next_workflow_status("c", ["a", "b", "c"]) is None

    def test_unknown_falls_back_to_first(self):
        assert compute_next_workflow_status("x", ["a", "b"]) == "a"

    def test_empty_pipeline(self):
        assert compute_next_workflow_status("a", []) is None


class TestIndexacaoUpdateSet:
    def test_clears_indexer_and_confirms_data(self):
        s = build_indexacao_update_set(
            {"id": "u1", "name": "Ana"}, "2026-01-01T00:00:00+00:00", "fase_2",
        )
        assert s["is_indexed"] is True
        assert s["assigned_indexacao_id"] is None
        assert s["is_data_confirmed"] is True
        assert s["status"] == "fase_2"

    def test_without_next_status(self):
        s = build_indexacao_update_set({"id": "u1"}, "t")
        assert "status" not in s


class TestCollectAssignedIds:
    def test_uniques_from_singular_and_lists(self):
        ids = collect_assigned_user_ids({
            "assigned_consultor_ids": ["c1", "c2"],
            "assigned_consultor_id": "c1",
            "assigned_mediador_id": "m1",
            "assigned_indexacao_id": "i1",
        })
        assert set(ids) == {"c1", "c2", "m1", "i1"}


class TestBuildStaffProcessDoc:
    def test_lead_source_and_status(self):
        doc = build_staff_process_doc(
            process_id="p1",
            process_number="PC-1",
            now="t",
            client_id="c1",
            client_name="Ana",
            client_email="a@x.com",
            client_phone="900",
            client_nif="123",
            process_type="credito",
            initial_status=None,
            is_lead=True,
        )
        assert doc["source"] == "lead"
        assert doc["status"] is None
        assert doc["client_ids"] == ["c1"]

    def test_consultor_assignment(self):
        doc = build_staff_process_doc(
            process_id="p1", process_number="1", now="t",
            client_id="c1", client_name="A", client_email="a@x.com",
            client_phone="", client_nif=None, process_type="credito",
            initial_status="fase_1", is_lead=False,
        )
        apply_creator_role_assignment(doc, {
            "id": "u1", "name": "João", "role": UserRole.CONSULTOR,
        })
        assert doc["assigned_consultor_id"] == "u1"
        assert doc["consultor_name"] == "João"


class TestMergeAndPermissions:
    def test_merge_drops_none_only(self):
        merged = merge_nested_process_section({"a": 1, "b": 2}, {"b": None, "c": 3})
        assert merged == {"a": 1, "c": 3}

    def test_merge_drops_empty_strings(self):
        merged = merge_nested_process_section(
            {"a": "x"}, {"a": "", "b": 1}, drop_empty_strings=True,
        )
        assert merged == {"b": 1}

    def test_indexacao_financial_only_flags(self):
        p = build_role_update_permissions(UserRole.INDEXACAO)
        assert p["can_update_financial"] is True
        assert p["can_update_personal"] is False
        assert p["can_update_status"] is False
        assert p["can_update_real_estate"] is False
