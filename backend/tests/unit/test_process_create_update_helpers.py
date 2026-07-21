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


class TestClientIdsRebuild:
    def test_primary_reassign_inserts_front(self):
        from services.process_update import rebuild_client_ids_on_primary_reassign
        assert rebuild_client_ids_on_primary_reassign(["a", "b"], "a", "c") == ["c", "b"]

    def test_primary_reassign_keeps_if_already_present(self):
        from services.process_update import rebuild_client_ids_on_primary_reassign
        assert rebuild_client_ids_on_primary_reassign(["c", "b"], "a", "c") == ["c", "b"]

    def test_second_titular_add_and_remove(self):
        from services.process_update import rebuild_client_ids_on_second_titular
        assert rebuild_client_ids_on_second_titular(["p"], None, "s") == ["p", "s"]
        assert rebuild_client_ids_on_second_titular(["p", "s"], "s", None) == ["p"]
        assert rebuild_client_ids_on_second_titular(["p", "s1"], "s1", "s2") == ["p", "s2"]

    def test_merge_field_metadata(self):
        from services.process_update import merge_field_metadata
        assert merge_field_metadata({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}
        assert merge_field_metadata(None, {"x": 1}) == {"x": 1}


class TestUpdateProcessLeftovers:
    def test_terminal_guard_blocks_staff(self):
        from fastapi import HTTPException
        from services.process_update import assert_process_editable_for_role
        try:
            assert_process_editable_for_role("concluidos", UserRole.CONSULTOR)
            assert False, "expected HTTPException"
        except HTTPException as e:
            assert e.status_code == 403

    def test_terminal_guard_allows_admin(self):
        from services.process_update import assert_process_editable_for_role
        assert_process_editable_for_role("concluidos", UserRole.ADMIN)

    def test_seed_update_data_contacts_and_reassign(self):
        from services.process_update import seed_update_data
        process = {
            "client_id": "c2",
            "client_name": "Nova",
            "client_email": "n@x.com",
            "client_phone": "900",
            "client_ids": ["c2"],
        }
        data = seed_update_data(
            process=process,
            client_id_before="c1",
            new_client_id="c2",
            raw_client_email="ignored-if-reassign",
            raw_client_phone=None,
        )
        assert data["client_id"] == "c2"
        assert data["client_name"] == "Nova"
        assert "updated_at" in data

    def test_maybe_copy_owner_to_vendedor(self):
        from services.process_update import maybe_copy_owner_to_vendedor
        out = maybe_copy_owner_to_vendedor(
            {"proprietario_nome": "João", "proprietario_contacto": "91"},
            {},
            vendedor_explicit=False,
        )
        assert out == {"nome": "João", "contacto": "91"}
        assert maybe_copy_owner_to_vendedor(
            {"proprietario_nome": "João"}, {"nome": "Já tem"}, vendedor_explicit=False,
        ) is None
        assert maybe_copy_owner_to_vendedor(
            {"proprietario_nome": "João"}, {}, vendedor_explicit=True,
        ) is None

    def test_apply_cpcv_and_metadata_fields(self):
        from types import SimpleNamespace
        from fastapi import HTTPException
        from services.process_update import apply_cpcv_and_metadata_fields
        update = {}
        data = SimpleNamespace(
            co_buyers=[{"nome": "A"}],
            co_applicants=None,
            vendedor=None,
            mediador=None,
            monitored_emails=["a@x.com"],
            notes="nota",
            prioridade="alta",
            labels=["x"],
        )
        apply_cpcv_and_metadata_fields(update, data)
        assert update["prioridade"] == "alta"
        assert update["notes"] == "nota"
        assert update["monitored_emails"] == ["a@x.com"]
        bad = SimpleNamespace(
            co_buyers=None, co_applicants=None, vendedor=None, mediador=None,
            monitored_emails=None, notes=None, prioridade="urgente", labels=None,
        )
        try:
            apply_cpcv_and_metadata_fields({}, bad)
            assert False
        except HTTPException as e:
            assert e.status_code == 400

    def test_attach_field_metadata(self):
        from services.process_update import attach_field_metadata_if_present
        update = {}
        attach_field_metadata_if_present(
            update, {"field_metadata": {"a": 1}}, {"field_metadata": {"b": 2}},
        )
        assert update["field_metadata"] == {"a": 1, "b": 2}


class TestKanbanEnrichment:
    def test_group_and_sort(self):
        from services.process_kanban_enrichment import (
            group_processes_by_status,
            sort_kanban_column_processes,
        )
        procs = [
            {"status": "a", "prioridade": "baixa", "updated_at": "2026-01-02"},
            {"status": "a", "prioridade": "alta", "updated_at": "2026-01-01"},
            {"status": "b", "prioridade": "media", "updated_at": "2026-01-03"},
        ]
        grouped = group_processes_by_status(procs)
        assert set(grouped) == {"a", "b"}
        sorted_a = sort_kanban_column_processes(list(grouped["a"]))
        assert sorted_a[0]["prioridade"] == "alta"
        # same priority → updated_at DESC
        same = [
            {"prioridade": "alta", "updated_at": "2026-01-01"},
            {"prioridade": "alta", "updated_at": "2026-01-03"},
        ]
        sort_kanban_column_processes(same)
        assert same[0]["updated_at"] == "2026-01-03"

    def test_enrich_card_and_columns(self):
        from services.process_kanban_enrichment import (
            enrich_kanban_process_card,
            build_kanban_columns,
            group_processes_by_status,
        )
        user_map = {
            "c1": {"id": "c1", "name": "Ana"},
            "m1": {"id": "m1", "name": "Bruno"},
        }
        p = {
            "id": "p1",
            "status": "fase_1",
            "assigned_consultor_id": "c1",
            "assigned_mediador_ids": ["m1"],
        }
        card = enrich_kanban_process_card(p, user_map, "c1")
        assert card["consultor_name"] == "Ana"
        assert card["mediador_name"] == "Bruno"
        assert card["is_assigned_to_me"] is True
        assert card["my_role_in_process"] == "consultor"

        cols = build_kanban_columns(
            [{"name": "fase_1", "label": "Fase 1", "color": "#111", "order": 1}],
            group_processes_by_status([p]),
            user_map,
            "c1",
        )
        assert cols[0]["count"] == 1
        assert cols[0]["processes"][0]["consultor_name"] == "Ana"


class TestListEnrichmentSort:
    def test_default_sort_priority_then_status(self):
        from services.process_list_enrichment import sort_process_list, get_priority_weight
        procs = [
            {"client_name": "B", "status": "z", "prioridade": "baixa"},
            {"client_name": "A", "status": "a", "prioridade": "alta"},
            {"client_name": "C", "status": "a", "prioridade": "alta"},
        ]
        sort_process_list(procs, status_order={"a": 1, "z": 2})
        assert procs[0]["prioridade"] == "alta"
        assert procs[0]["client_name"] == "A"
        assert get_priority_weight({"priority": "high"}) == 3

    def test_apply_assignee_names(self):
        from services.process_list_enrichment import (
            collect_assignee_user_ids,
            apply_assignee_names,
        )
        procs = [{
            "assigned_consultor_ids": ["c1"],
            "assigned_indexacao_id": "i1",
        }]
        assert collect_assignee_user_ids(procs) == {"c1", "i1"}
        apply_assignee_names(procs, {"c1": "Ana", "i1": "Inês"})
        assert procs[0]["consultor_name"] == "Ana"
        assert procs[0]["indexacao_name"] == "Inês"
