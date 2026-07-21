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
