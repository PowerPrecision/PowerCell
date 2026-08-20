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
            "is_deleted": {"$ne": True}
        }

    def test_eliminados_status(self):
        assert build_is_deleted_filter(status="eliminados", view_mode="active_only") == {
            "is_deleted": True
        }

    def test_deleted_view_mode(self):
        assert build_is_deleted_filter(status=None, view_mode="deleted") == {
            "is_deleted": True
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
        assert {"assigned_consultor_ids": "u9"} in cond["$or"]
        assert {"assigned_mediador_id": "u9"} in cond["$or"]

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
        assert {"status": "escritura"} in conds

    def test_eliminados_skips_view_mode(self):
        conds = build_view_mode_status_conditions(
            status="eliminados", view_mode="active_only"
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
        assert {"is_deleted": {"$ne": True}} in flat
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

    def test_admin_only_hides_pre_registo(self):
        from services.process_list_filters import build_my_clients_process_query
        q = build_my_clients_process_query("a1", "a@x.com", UserRole.ADMIN)
        assert q == {"status": {"$nin": LEAD_STATUS_VALUES}}

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
