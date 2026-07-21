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
    assert_can_create_staff_process,
    assert_client_id_required,
    build_create_broadcast_names,
)
from services.process_ai_conflict import (
    find_ai_suggestion,
    sanitize_ai_suggested_value,
    build_ai_accept_update_fields,
    apply_ai_conflict_choice,
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


class TestMarkIndexedPermissionAndResponse:
    def test_permission_blocks_consultor(self):
        from fastapi import HTTPException
        from services.process_indexing import assert_mark_indexed_permission
        try:
            assert_mark_indexed_permission("consultor", ["consultor"])
            assert False
        except HTTPException as e:
            assert e.status_code == 403

    def test_permission_allows_additional_role(self):
        from services.process_indexing import assert_mark_indexed_permission
        assert_mark_indexed_permission("consultor", ["consultor", "indexacao"])

    def test_build_response_with_transition(self):
        from services.process_indexing import build_mark_indexed_response
        resp = build_mark_indexed_response(
            process={"assigned_indexacao_id": "i1"},
            process_id="p1",
            process_ref="#42",
            current_status="a",
            next_status="b",
            assigned_ids=["u1", "u2"],
            consultant_result={"consultant_name": "Ana"},
            is_pre_registo_transition=False,
        )
        assert resp["is_indexed"] is True
        assert resp["notified_users"] == 2
        assert resp["status_transition"] == {"from": "a", "to": "b"}
        assert resp["indexer_cleared"] is True
        assert resp["dual_auto_assigned"] is False
        assert resp["assignment"] is None

    def test_build_response_pre_registo(self):
        from services.process_indexing import build_mark_indexed_response
        dual = {"consultant_name": "A", "mediador_name": "B"}
        resp = build_mark_indexed_response(
            process={},
            process_id="p1",
            process_ref="p1",
            current_status="pre_registo",
            next_status="fase_1",
            assigned_ids=[],
            consultant_result=dual,
            is_pre_registo_transition=True,
        )
        assert resp["dual_auto_assigned"] is True
        assert resp["assignment"] == dual


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


class TestCreateClientGuards:
    def test_role_blocks_indexacao(self):
        from fastapi import HTTPException
        try:
            assert_can_create_staff_process(UserRole.INDEXACAO)
            assert False
        except HTTPException as e:
            assert e.status_code == 403

    def test_role_allows_admin(self):
        assert_can_create_staff_process(UserRole.ADMIN)

    def test_client_id_required(self):
        from fastapi import HTTPException
        try:
            assert_client_id_required(None)
            assert False
        except HTTPException as e:
            assert e.status_code == 400
        assert_client_id_required("c1")

    def test_broadcast_names(self):
        c, m = build_create_broadcast_names({
            "name": "Ana", "role": UserRole.CONSULTOR,
        })
        assert c == ["Ana"] and m == []
        c, m = build_create_broadcast_names({
            "name": "Bruno", "role": UserRole.INTERMEDIARIO,
        })
        assert c == [] and m == ["Bruno"]


class TestAiConflictHelpers:
    def test_find_by_field_and_id(self):
        from fastapi import HTTPException
        suggestions = [
            {"id": "s1", "field": "nif", "suggested": "1"},
            {"id": "s2", "field": "nif", "suggested": "2"},
            {"id": "s3", "field": "email", "suggested": "a@x.com"},
        ]
        s, i = find_ai_suggestion(suggestions, "nif", "s2")
        assert s["suggested"] == "2" and i == 1
        try:
            find_ai_suggestion(suggestions, "telefone")
            assert False
        except HTTPException as e:
            assert e.status_code == 404

    def test_sanitize_and_accept_fields(self):
        assert sanitize_ai_suggested_value("nome", "  Ana  ") == "Ana"
        assert build_ai_accept_update_fields(
            "nif", "personal_data.nif", "123",
        ) == {"personal_data.nif": "123"}
        assert build_ai_accept_update_fields(
            "salario_bruto", "salario_bruto", 1000,
        ) == {"financial_data.salario_bruto": 1000}
        assert build_ai_accept_update_fields(
            "notes", "notes", "x",
        ) == {"notes": "x"}

    def test_apply_choice_ai_and_current(self):
        suggestions = [
            {
                "id": "s1",
                "field": "nome",
                "field_path": "personal_data.nome",
                "current": "Old",
                "suggested": "  Nova  ",
            },
            {
                "id": "s2",
                "field": "email",
                "suggested": "b@x.com",
                "current": "a@x.com",
            },
        ]
        update, sug, resolved = apply_ai_conflict_choice(
            ai_suggestions=suggestions,
            field="nome",
            choice="ai",
            suggestion_id="s1",
            now="t0",
        )
        assert resolved == "Nova"
        assert update["personal_data.nome"] == "Nova"
        assert len(update["ai_suggestions"]) == 1
        assert update["ai_suggestions"][0]["id"] == "s2"
        # original list untouched
        assert len(suggestions) == 2

        update2, sug2, resolved2 = apply_ai_conflict_choice(
            ai_suggestions=suggestions,
            field="email",
            choice="current",
            suggestion_id=None,
            now="t1",
        )
        assert resolved2 is None
        assert "email" not in update2
        assert len(update2["ai_suggestions"]) == 1
        assert sug2["field"] == "email"


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

    def test_apply_client_contacts_setdefault(self):
        from services.process_kanban_enrichment import (
            apply_client_contacts_to_processes,
            client_contact_summary,
            build_active_inactive_count_queries,
            build_kanban_board_payload,
            safe_build_kanban_columns,
        )
        assert client_contact_summary({
            "nome": "Ana",
            "contacto": {"email": "a@x.com", "telefone": "91"},
            "dados_pessoais": {"nif": "1"},
        })["email"] == "a@x.com"

        procs = [
            {"client_id": "c1", "client_name": "Keep"},
            {"client_id": "c1"},
            {"client_id": "missing"},
        ]
        apply_client_contacts_to_processes(procs, {
            "c1": {"nome": "Nova", "email": "n@x.com", "telefone": "9", "nif": "2"},
        })
        assert procs[0]["client_name"] == "Keep"
        assert procs[1]["client_name"] == "Nova"
        assert procs[1]["client_email"] == "n@x.com"
        assert "client_name" not in procs[2]

        active, inactive = build_active_inactive_count_queries({"is_deleted": {"$ne": True}})
        assert active["status"]["$nin"] == ["concluidos", "desistencias"]
        assert inactive["status"]["$in"] == ["concluidos", "desistencias"]

        payload = build_kanban_board_payload(
            columns=[],
            active_count=3,
            inactive_count=1,
            role="admin",
            user_id="u1",
            view_mode="all",
            completed_days=30,
        )
        assert payload["total_processes"] == 3
        assert payload["columns"] == []

        # failsafe: bad status entry that would break enrich still yields list
        cols = safe_build_kanban_columns(
            [{"name": "ok", "label": "OK", "color": "#000", "order": 1}],
            {"ok": [{"id": "p1", "status": "ok"}]},
            {},
            "u1",
        )
        assert isinstance(cols, list) and cols[0]["count"] == 1


class TestKanbanDiagnoseFinalize:
    def test_can_load_when_checks_ok(self):
        from services.process_kanban_diagnose import finalize_kanban_diagnose_report
        report = {
            "checks": {
                "workflow_statuses": {"count": 2},
                "processes": {"total": 1},
                "kanban_query": {"works": True},
            },
            "can_load": False,
            "blocking_issue": None,
        }
        out = finalize_kanban_diagnose_report(report)
        assert out["can_load"] is True

    def test_blocking_when_empty_statuses(self):
        from services.process_kanban_diagnose import finalize_kanban_diagnose_report
        report = {
            "checks": {
                "workflow_statuses": {"count": 0},
                "processes": {"total": 1},
                "kanban_query": {"works": True},
            },
            "can_load": False,
            "blocking_issue": None,
        }
        out = finalize_kanban_diagnose_report(report)
        assert out["can_load"] is False
        assert out["blocking_issue"]


class TestClientSelfCreate:
    def test_role_guard(self):
        from fastapi import HTTPException
        from services.process_create import assert_is_cliente_role, build_client_self_process_doc
        try:
            assert_is_cliente_role(UserRole.ADMIN)
            assert False
        except HTTPException as e:
            assert e.status_code == 403
        assert_is_cliente_role(UserRole.CLIENTE)
        doc = build_client_self_process_doc(
            process_id="p1", process_number=1, client_id="c1",
            process_type="credito", initial_status="fase_1", now="t",
        )
        assert doc["client_id"] == "c1"
        assert doc["assigned_consultor_id"] is None


class TestProcessClientsNm:
    def test_add_as_co_titular(self):
        from services.process_clients_nm import build_add_client_update
        process = {"client_ids": ["c1"], "co_buyers": []}
        client = {
            "nome": "B",
            "contacto": {"email": "b@x.com", "telefone": "91"},
            "dados_pessoais": {"nif": "2"},
        }
        update, ids = build_add_client_update(
            process, client, "c2", as_co_titular=True, now="t",
        )
        assert ids == ["c1", "c2"]
        assert update["co_buyers"][0]["client_id"] == "c2"
        assert update["titular2_data"]["name"] == "B"

    def test_add_duplicate_raises(self):
        from fastapi import HTTPException
        from services.process_clients_nm import build_add_client_update
        try:
            build_add_client_update(
                {"client_ids": ["c1"]}, {"nome": "A"}, "c1",
                as_co_titular=False, now="t",
            )
            assert False
        except HTTPException as e:
            assert e.status_code == 400

    def test_remove_clears_second_client(self):
        from services.process_clients_nm import build_remove_client_update
        process = {
            "client_id": "c1",
            "client_ids": ["c1", "c2"],
            "second_client_id": "c2",
            "second_client_name": "B",
            "co_buyers": [{"client_id": "c2", "name": "B"}],
        }
        update, ids = build_remove_client_update(process, "c2", now="t")
        assert ids == ["c1"]
        assert update["second_client_id"] is None
        assert update["titular2_data"] is None
        assert update["co_buyers"] is None

    def test_remove_primary_raises(self):
        from fastapi import HTTPException
        from services.process_clients_nm import build_remove_client_update
        try:
            build_remove_client_update(
                {"client_id": "c1", "client_ids": ["c1"]}, "c1", now="t",
            )
            assert False
        except HTTPException as e:
            assert e.status_code == 400


class TestPortalMessageHelpers:
    def test_validate_content(self):
        from fastapi import HTTPException
        from services.process_portal_messages import (
            validate_staff_portal_message_content,
            build_staff_portal_message_doc,
            staff_portal_message_response,
        )
        try:
            validate_staff_portal_message_content("   ")
            assert False
        except HTTPException as e:
            assert e.status_code == 400
        try:
            validate_staff_portal_message_content("x" * 5001)
            assert False
        except HTTPException as e:
            assert e.status_code == 400
        assert validate_staff_portal_message_content("  oi  ") == "oi"
        doc = build_staff_portal_message_doc(
            process_id="p1",
            user={"id": "u1", "name": "Ana"},
            content="olá",
            now="t0",
            message_id="m1",
        )
        assert doc["sender_type"] == "staff" and doc["id"] == "m1"
        resp = staff_portal_message_response(doc)
        assert resp["content"] == "olá" and "_id" not in resp


class TestUpdateProcessMetaHelpers:
    def test_parse_and_guards(self):
        from fastapi import HTTPException
        from services.process_update import (
            parse_update_request_meta,
            assert_can_reassign_primary_client,
            assert_cliente_owns_process,
        )
        body, reason, ai = parse_update_request_meta({
            "audit_reason": "fix", "ai_suggested": 1,
        })
        assert reason == "fix" and ai is True
        assert_can_reassign_primary_client(UserRole.ADMIN)
        try:
            assert_can_reassign_primary_client(UserRole.CONSULTOR)
            assert False
        except HTTPException as e:
            assert e.status_code == 403
        assert_cliente_owns_process(
            {"client_id": "c1"}, {"id": "c1", "role": UserRole.CLIENTE},
        )
        try:
            assert_cliente_owns_process(
                {"client_id": "c1"}, {"id": "other", "role": UserRole.CLIENTE},
            )
            assert False
        except HTTPException as e:
            assert e.status_code == 403


class TestListAndMyClientsOrchestration:
    def test_slice_page_and_responses(self):
        from services.process_list_enrichment import (
            slice_page,
            build_process_list_response,
            build_process_cursor_list_response,
        )
        items = list(range(25))
        page_items, total, pages = slice_page(items, 2, 10)
        assert total == 25 and pages == 3 and page_items == list(range(10, 20))
        resp = build_process_list_response(
            items=page_items, total=total, page=2, size=10, pages=pages,
            view_mode="active_only",
        )
        assert resp["page"] == 2 and len(resp["items"]) == 10
        cursor_resp = build_process_cursor_list_response(
            result={
                "items": [{"id": "p1"}],
                "next_cursor": "abc",
                "has_more": True,
                "limit": 20,
            },
            view_mode="all",
        )
        assert cursor_resp["processes"][0]["id"] == "p1"
        assert cursor_resp["has_more"] is True

    def test_assemble_my_clients_rows(self):
        from services.process_my_clients import (
            assemble_my_clients_rows,
            process_ids_from_my_clients_page,
            build_my_clients_response,
        )
        page = [
            {"id": "lead1", "is_lead": True, "client_name": "L"},
            {
                "id": "p1",
                "client_id": "c1",
                "client_name": "Ana",
                "status": "fase_1",
                "assigned_consultor_id": "u1",
            },
        ]
        assert process_ids_from_my_clients_page(page) == ["p1"]
        rows = assemble_my_clients_rows(
            page,
            status_map={"fase_1": {"label": "Fase 1", "color": "#111"}},
            tasks_by_process={"p1": [{"title": "T1", "priority": "high"}]},
            consultor_map={"u1": "João"},
            unread_map={"p1": True},
            new_docs_map={},
            notes_map={},
        )
        assert rows[0]["is_lead"] is True
        assert rows[0]["has_unread_messages"] is False
        assert rows[1]["consultor_name"] == "João"
        assert rows[1]["pending_count"] == 1
        assert rows[1]["has_unread_messages"] is True
        out = build_my_clients_response(
            clients=rows, total=2, page=1, size=50, pages=1,
            user_id="u1", user_role="consultor", leads_count=1,
        )
        assert out["leads_count"] == 1 and out["total"] == 2


class TestProcessDetailAndAssignEmail:
    def test_portal_access_payload(self):
        from services.process_detail import (
            build_portal_access_payload,
            ensure_client_id_default,
        )
        payload = build_portal_access_payload(
            portal_access_code="AB12",
            short_id="xyz",
            frontend_url="https://app.example.com/",
        )
        assert payload["magic_link"] == "https://app.example.com/portal/xyz"
        assert payload["has_active_token"] is True
        p = {}
        ensure_client_id_default(p)
        assert p["client_id"] == ""

    def test_assignment_email_bodies(self):
        from services.process_staff_assignment import build_assignment_email_bodies
        subject, text, html = build_assignment_email_bodies(
            user_name="Ana",
            role_label="Consultor",
            client_name="Cliente X",
            process_number="42",
            process_id="pid",
            process_link="https://app/processo/pid",
        )
        assert "Cliente X" in subject
        assert "Consultor" in text and "https://app/processo/pid" in text
        assert "Abrir Processo no CRM" in html
        subject2, text2, html2 = build_assignment_email_bodies(
            user_name="Ana", role_label="Consultor", client_name="C",
            process_number="", process_id="abcdefghij", process_link="",
        )
        assert "abcdefgh" in text2
        assert "Abrir Processo" not in html2



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
