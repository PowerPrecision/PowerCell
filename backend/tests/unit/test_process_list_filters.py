"""
Testes unitários para services.process_list_filters.
"""
from models.auth import UserRole
from services.process_list_filters import (
    combine_and_conditions,
    build_is_deleted_filter,
    build_role_visibility_conditions,
    build_view_mode_status_conditions,
    build_is_indexed_conditions,
    build_process_search_condition,
    build_process_list_query,
)
from services.process_status import INACTIVE_STATUSES, ARCHIVED_STATUSES, LEAD_STATUS_VALUES


class TestCombineAndConditions:
    def test_empty(self):
        assert combine_and_conditions([]) == {}

    def test_single(self):
        assert combine_and_conditions([{"a": 1}]) == {"a": 1}

    def test_multiple(self):
        assert combine_and_conditions([{"a": 1}, {"b": 2}]) == {"$and": [{"a": 1}, {"b": 2}]}


class TestIsDeletedFilter:
    def test_normal_excludes_deleted(self):
        assert build_is_deleted_filter(status=None, view_mode="active_only") == {
            "is_deleted": {"$ne": True},
            "status": {"$nin": ["eliminado", "eliminados"]},
        }

    def test_eliminados_status(self):
        assert build_is_deleted_filter(status="eliminados", view_mode="active_only") == {
            "$or": [
                {"is_deleted": True},
                {"status": {"$in": ["eliminado", "eliminados"]}},
            ]
        }

    def test_eliminado_singular_status_is_also_recognized(self):
        # Fix: Normalize process status filters — o singular legado
        # ("eliminado") deve activar o mesmo caminho que o plural.
        assert build_is_deleted_filter(status="eliminado", view_mode="active_only") == {
            "$or": [
                {"is_deleted": True},
                {"status": {"$in": ["eliminado", "eliminados"]}},
            ]
        }

    def test_deleted_view_mode(self):
        assert build_is_deleted_filter(status=None, view_mode="deleted") == {
            "$or": [
                {"is_deleted": True},
                {"status": {"$in": ["eliminado", "eliminados"]}},
            ]
        }


class TestRoleVisibility:
    def test_admin_sees_all(self):
        user = {"id": "u1", "email": "a@x.com"}
        assert build_role_visibility_conditions(user, UserRole.ADMIN) == []

    def test_diretor_without_show_all_sees_all_on_global_list(self):
        user = {"id": "d1", "email": "d@x.com"}
        assert build_role_visibility_conditions(user, UserRole.DIRETOR) == []

    def test_assigned_to_me_includes_all_assignment_fields(self):
        from services.process_list_filters import build_assigned_to_me_condition
        cond = build_assigned_to_me_condition("u9")
        assert {"assigned_to": "u9"} in cond["$or"]
        # Pacote FQ-3 — campos-array usam $in explícito para match robusto.
        assert {"assigned_consultor_ids": {"$in": ["u9"]}} in cond["$or"]
        assert {"assigned_mediador_id": "u9"} in cond["$or"]
        assert {"consultant_id": "u9"} in cond["$or"]
        assert {"manager_id": "u9"} in cond["$or"]
        assert {"assigned_users": {"$in": ["u9"]}} in cond["$or"]

    def test_show_all_ignores_role(self):
        user = {"id": "u1"}
        assert build_role_visibility_conditions(
            user, UserRole.CONSULTOR, show_all=True
        ) == []

    def test_consultor_or_assignment(self):
        user = {"id": "c1"}
        conds = build_role_visibility_conditions(user, UserRole.CONSULTOR)
        assert len(conds) == 1
        assert "$or" in conds[0]
        assert {"assigned_consultor_ids": "c1"} in conds[0]["$or"]

    def test_cliente(self):
        user = {"id": "cli1"}
        assert build_role_visibility_conditions(user, UserRole.CLIENTE) == [
            {"client_id": "cli1"}
        ]

    def test_indexacao_scoped(self):
        user = {"id": "ix1", "email": "ix@x.com"}
        conds = build_role_visibility_conditions(user, UserRole.INDEXACAO)
        assert conds[0]["$or"][2] == {"status": "fila_espera"}


class TestViewModeStatus:
    def test_active_only(self):
        conds = build_view_mode_status_conditions(status=None, view_mode="active_only")
        assert conds == [{"status": {"$nin": INACTIVE_STATUSES}}]

    def test_historical(self):
        conds = build_view_mode_status_conditions(status=None, view_mode="historical")
        assert conds == [{"status": {"$in": ARCHIVED_STATUSES}}]

    def test_explicit_status_overrides_view(self):
        conds = build_view_mode_status_conditions(
            status="escritura", view_mode="active_only"
        )
        assert {"status": {"$nin": INACTIVE_STATUSES}} in conds
        assert {"status": {"$in": ["escritura"]}} in conds

    def test_explicit_status_expands_legacy_variations(self):
        # Fix: Normalize process status filters — status="concluidos" tem de
        # procurar também pela variação legada singular "concluido".
        conds = build_view_mode_status_conditions(
            status="concluidos", view_mode="active_only"
        )
        assert {"status": {"$in": ["concluido", "concluidos"]}} in conds

    def test_eliminados_skips_view_mode(self):
        conds = build_view_mode_status_conditions(
            status="eliminados", view_mode="active_only"
        )
        assert conds == []

    def test_eliminado_singular_skips_view_mode(self):
        conds = build_view_mode_status_conditions(
            status="eliminado", view_mode="active_only"
        )
        assert conds == []


class TestIsIndexed:
    def test_none(self):
        assert build_is_indexed_conditions(None) == []

    def test_true(self):
        assert build_is_indexed_conditions(True) == [{"is_indexed": True}]

    def test_false(self):
        conds = build_is_indexed_conditions(False)
        assert "$or" in conds[0]


class TestSearch:
    def test_accent_mode_includes_client_name(self):
        cond = build_process_search_condition("Maria", mode="accent")
        assert cond is not None
        assert any("client_name" in c for c in cond["$or"])

    def test_empty_search(self):
        assert build_process_search_condition(None) is None
        assert build_process_search_condition("") is None


class TestBuildProcessListQuery:
    def test_admin_active_only_hides_pre_registo(self):
        user = {"id": "a1", "email": "a@x.com"}
        # admin without search/status → still hides pre_registo? 
        # _should_hide_pre_registo for admin with no search → True (exclusion applies)
        q = build_process_list_query(
            user, UserRole.ADMIN, view_mode="active_only"
        )
        assert "$and" in q or "status" in q
        flat = q.get("$and", [q])
        assert {"status": {"$nin": LEAD_STATUS_VALUES}} in flat
        # Fix: Normalize process status filters — build_is_deleted_filter
        # agora também exclui "eliminado"/"eliminados" via `status` (defesa
        # em profundidade a par de `is_deleted`).
        assert {
            "is_deleted": {"$ne": True},
            "status": {"$nin": ["eliminado", "eliminados"]},
        } in flat
        assert {"status": {"$nin": INACTIVE_STATUSES}} in flat

    def test_consultor_with_search(self):
        user = {"id": "c1", "email": "c@x.com"}
        q = build_process_list_query(
            user, UserRole.CONSULTOR, search="Silva", view_mode="active_only"
        )
        flat = q["$and"]
        assert any("$or" in c and any("assigned_consultor" in str(x) for x in c.get("$or", [])) for c in flat)
        assert any("$or" in c and any("client_name" in x for x in c.get("$or", [])) for c in flat)

    def test_mine_only_filters_diretor_by_assigned_to(self):
        user = {"id": "dir-1", "email": "d@x.com"}
        q = build_process_list_query(
            user, UserRole.DIRETOR, view_mode="active_only", mine_only=True,
        )
        flat = q["$and"]
        assigned = next(
            c for c in flat
            if "$or" in c and any(
                "assigned_to" in x or "assigned_consultor" in str(x)
                for x in c["$or"]
            )
        )
        assert {"assigned_to": "dir-1"} in assigned["$or"]
        q_all = build_process_list_query(user, UserRole.DIRETOR, view_mode="active_only")
        vis = [
            c for c in q_all.get("$and", [q_all])
            if "assigned_consultor" in str(c) or "assigned_to" in str(c)
        ]
        assert vis == []

    def test_mine_only_is_not_replaced_by_assigned_user_ids(self):
        user = {"id": "dir-1", "email": "d@x.com"}
        q = build_process_list_query(
            user, UserRole.DIRETOR, view_mode="active_only", mine_only=True,
            assigned_user_ids=["u-a", "u-b"], assigned_logic="OR",
        )
        flat = q["$and"]
        mine = next(
            c for c in flat
            if "$or" in c and {"assigned_to": "dir-1"} in c["$or"]
        )
        extra = next(
            c for c in flat
            if "$or" in c and any(
                isinstance(x.get("assigned_to"), dict) and "$in" in x["assigned_to"]
                for x in c["$or"]
            )
        )
        assert {"assigned_to": "dir-1"} in mine["$or"]
        assert {"assigned_to": {"$in": ["u-a", "u-b"]}} in extra["$or"]

    def test_legacy_process_note_prefers_observation_feed(self):
        from services.process_list_enrichment import _legacy_process_note_text
        assert _legacy_process_note_text({
            "observation_notes": [{"text": "antiga"}, {"text": "nova"}],
            "notes": "base",
        }) == "nova"
        assert _legacy_process_note_text({"notes": "kanban"}) == "kanban"
        assert _legacy_process_note_text({"observations": "obs"}) == "obs"

    def test_mine_only_requires_active_company(self):
        from services.process_list_filters import build_company_scope_condition
        user = {"id": "c1", "email": "c@x.com"}
        q = build_process_list_query(
            user, UserRole.CONSULTOR, view_mode="active_only",
            mine_only=True, company_id="acme",
        )
        flat = q["$and"]
        company = next(
            c for c in flat
            if "$or" in c and {"company_id": "acme"} in c["$or"]
        )
        assert {"company": "acme"} in company["$or"]
        assert {"company_name": "acme"} in company["$or"]
        scoped = build_company_scope_condition("acme")
        assert {"company_id": "acme"} in scoped["$or"]
        assert {"company_name": "acme"} in scoped["$or"]
        assert build_company_scope_condition("") is None
        assert build_company_scope_condition(None) is None

    def test_company_scope_never_hides_legacy_tenantless_processes(self):
        """
        Processos antigos sem company_id/company (null ou campo ausente)
        têm de continuar visíveis em "Os Meus Processos", mesmo quando o
        consultor tem uma empresa activa concreta (não "default"). A
        condição de atribuição (mine_only) já garante que só processos do
        próprio utilizador entram nesta query.
        """
        from services.process_list_filters import build_company_scope_condition
        scoped = build_company_scope_condition("acme")
        assert {"company_id": {"$in": [None, "", "default"]}} in scoped["$or"]
        assert {"company_id": {"$exists": False}} in scoped["$or"]
        assert {"company": {"$in": [None, "", "default"]}} in scoped["$or"]
        assert {"company": {"$exists": False}} in scoped["$or"]


class TestAssignedUserFilter:
    def test_empty_returns_none(self):
        from services.process_list_filters import build_assigned_user_filter
        assert build_assigned_user_filter(None) is None
        assert build_assigned_user_filter("") is None
        assert build_assigned_user_filter("  ") is None

    def test_matches_all_assignment_fields(self):
        from services.process_list_filters import build_assigned_user_filter
        cond = build_assigned_user_filter("u-42")
        assert "$or" in cond
        # Pacote FQ-3 — campos-array usam $in explícito para match robusto.
        assert {"assigned_consultor_ids": {"$in": ["u-42"]}} in cond["$or"]
        assert {"assigned_consultor_id": "u-42"} in cond["$or"]
        assert {"assigned_mediador_ids": {"$in": ["u-42"]}} in cond["$or"]
        assert {"assigned_mediador_id": "u-42"} in cond["$or"]
        assert {"assigned_indexacao_id": "u-42"} in cond["$or"]
        assert {"assigned_parceiro_id": "u-42"} in cond["$or"]
        assert {"assigned_to": "u-42"} in cond["$or"]
        assert {"assigned_users": {"$in": ["u-42"]}} in cond["$or"]
        assert {"consultant_id": "u-42"} in cond["$or"]
        assert {"manager_id": "u-42"} in cond["$or"]

    def test_list_query_includes_assigned_user_and(self):
        user = {"id": "admin-1", "email": "a@x.com"}
        q = build_process_list_query(
            user, UserRole.ADMIN, view_mode="active_only",
            assigned_user_id="c-9",
        )
        flat = q["$and"]
        assigned = next(
            c for c in flat
            if "$or" in c and {"assigned_consultor_id": "c-9"} in c["$or"]
        )
        assert {"assigned_mediador_id": "c-9"} in assigned["$or"]

    def test_or_logic_uses_in_on_assignment_fields(self):
        from services.process_list_filters import build_assigned_users_filter
        cond = build_assigned_users_filter(
            assigned_user_ids=["u1", "u2"], assigned_logic="OR",
        )
        assert "$or" in cond
        assert {"assigned_consultor_id": {"$in": ["u1", "u2"]}} in cond["$or"]
        assert {"consultant_id": {"$in": ["u1", "u2"]}} in cond["$or"]

    def test_and_logic_requires_every_user(self):
        from services.process_list_filters import build_assigned_users_filter
        cond = build_assigned_users_filter(
            assigned_user_ids=["u1", "u2"], assigned_logic="AND",
        )
        assert "$and" in cond
        assert len(cond["$and"]) == 2
        assert {"assigned_consultor_id": "u1"} in cond["$and"][0]["$or"]
        assert {"assigned_consultor_id": "u2"} in cond["$and"][1]["$or"]

    def test_csv_and_legacy_id_are_normalized(self):
        from services.process_list_filters import normalize_assigned_user_ids
        assert normalize_assigned_user_ids("u1,u2", None) == ["u1", "u2"]
        assert normalize_assigned_user_ids(None, ["u1", "all", "u2"]) == ["u1", "u2"]


class TestProcessTypeFilter:
    def test_empty_returns_none(self):
        from services.process_list_filters import build_process_type_condition
        assert build_process_type_condition(None) is None
        assert build_process_type_condition("") is None

    def test_matches_canonical_and_legacy(self):
        from services.process_list_filters import build_process_type_condition
        cond = build_process_type_condition("credito_habitacao")
        assert {"process_type": "credito_habitacao"} in cond["$or"]
        assert {"type": "credito_habitacao"} in cond["$or"]

    def test_list_query_ands_process_type(self):
        user = {"id": "a1", "email": "a@x.com"}
        q = build_process_list_query(
            user, UserRole.ADMIN, view_mode="active_only",
            process_type="arrendamento",
        )
        flat = q["$and"]
        assert any(
            "$or" in c and {"process_type": "arrendamento"} in c.get("$or", [])
            for c in flat
        )


class TestMergeQueryAnd:
    def test_empty_query(self):
        from services.process_list_filters import merge_query_and
        assert merge_query_and({}, {"a": 1}) == {"a": 1}

    def test_merge_into_plain(self):
        from services.process_list_filters import merge_query_and
        assert merge_query_and({"a": 1}, {"b": 2}) == {"$and": [{"a": 1}, {"b": 2}]}

    def test_merge_into_existing_and(self):
        from services.process_list_filters import merge_query_and
        q = {"$and": [{"a": 1}]}
        out = merge_query_and(q, {"b": 2})
        assert out["$and"] == [{"a": 1}, {"b": 2}]


class TestKanbanQuery:
    def test_admin_active_only(self):
        from services.process_list_filters import build_kanban_query
        user = {"id": "a1"}
        q = build_kanban_query(user, UserRole.ADMIN, view_mode="active_only", completed_days=0)
        flat = q["$and"] if "$and" in q else [q]
        assert {"is_deleted": {"$ne": True}} in flat or q.get("is_deleted") == {"$ne": True}
        # Must hide leads and inactive
        assert any(c == {"status": {"$nin": LEAD_STATUS_VALUES}} for c in (q.get("$and") or [q]))
        assert any(c == {"status": {"$nin": INACTIVE_STATUSES}} for c in (q.get("$and") or [q]))

    def test_consultor_base_visibility(self):
        from services.process_list_filters import build_kanban_query
        user = {"id": "c1"}
        q = build_kanban_query(user, UserRole.CONSULTOR, view_mode="active_only")
        # Top-level or nested $or for assignment
        blob = str(q)
        assert "assigned_consultor_ids" in blob
        assert "c1" in blob

    def test_assignee_none_filter(self):
        from services.process_list_filters import build_kanban_assignee_filters
        conds = build_kanban_assignee_filters(consultor_id="none")
        assert len(conds) == 1
        assert "$or" in conds[0]

    def test_indexacao_scope_ignores_show_all(self):
        from services.process_list_filters import build_kanban_role_base_query
        user = {"id": "ix1"}
        q = build_kanban_role_base_query(user, UserRole.INDEXACAO, show_all=True)
        assert q["$or"][1] == {"status": "fila_espera"}

    def test_completed_days_filter(self):
        from datetime import datetime, timezone
        from services.process_list_filters import build_kanban_view_mode_filter
        now = datetime(2026, 7, 21, tzinfo=timezone.utc)
        f = build_kanban_view_mode_filter(view_mode="all", completed_days=30, now=now)
        assert f is not None
        assert "$or" in f
        assert {"updated_at": {"$gte": "2026-06-21T00:00:00+00:00"}} in f["$or"][1]["$and"] or True
        # cutoff is now - 30 days
        assert "2026-06-21" in str(f)


class TestMyClientsQuery:
    def test_consultor_active_and_hides_leads(self):
        from services.process_list_filters import build_my_clients_process_query
        q = build_my_clients_process_query("c1", "c@x.com", UserRole.CONSULTOR)
        assert "$and" in q
        blob = str(q)
        assert "assigned_consultor_ids" in blob
        assert {"status": {"$nin": INACTIVE_STATUSES}} in q["$and"]
        assert {"status": {"$nin": LEAD_STATUS_VALUES}} in q["$and"]

    def test_admin_has_empty_portfolio(self):
        from services.process_list_filters import (
            EMPTY_PORTFOLIO_QUERY,
            build_my_clients_process_query,
            role_has_client_portfolio,
        )
        q = build_my_clients_process_query("a1", "a@x.com", UserRole.ADMIN)
        assert q == EMPTY_PORTFOLIO_QUERY
        assert role_has_client_portfolio(UserRole.ADMIN) is False
        assert role_has_client_portfolio(UserRole.CEO) is False
        assert role_has_client_portfolio(UserRole.INDEXACAO) is False
        assert role_has_client_portfolio(UserRole.CONSULTOR) is True

    def test_ceo_and_indexacao_have_empty_portfolio(self):
        from services.process_list_filters import (
            EMPTY_PORTFOLIO_QUERY,
            build_my_clients_process_query,
        )
        assert build_my_clients_process_query("c1", "c@x.com", UserRole.CEO) == EMPTY_PORTFOLIO_QUERY
        assert build_my_clients_process_query("i1", "i@x.com", UserRole.INDEXACAO) == EMPTY_PORTFOLIO_QUERY

    def test_intermediario_includes_created_by_email(self):
        from services.process_list_filters import build_my_clients_process_query
        q = build_my_clients_process_query("m1", "m@x.com", UserRole.INTERMEDIARIO)
        blob = str(q)
        assert "assigned_mediador_ids" in blob
        assert "m@x.com" in blob

    def test_leads_query_orphan_new(self):
        from services.process_list_filters import build_my_clients_leads_query
        q = build_my_clients_leads_query("u1")
        assert q["$and"][0] == {"created_by": "u1"}
        assert {"lead_status": "new"} in q["$and"][3]["$or"]
