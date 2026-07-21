"""Unit tests for process_staff_assignment helpers."""
from models.auth import UserRole
from services.process_staff_assignment import (
    normalize_compat_assignment_params,
    is_clear_assignment_value,
    parse_assignment_ids_csv,
    build_clear_consultor_fields,
    build_set_consultor_fields,
    build_set_mediador_fields,
    detect_newly_assigned,
    build_assign_me_update,
    build_unassign_me_update,
)


class TestParseAndCompat:
    def test_compat_fallback(self):
        c, m = normalize_compat_assignment_params(None, None, "c1", "m1")
        assert c == "c1" and m == "m1"
        c, m = normalize_compat_assignment_params("c2", "m2", "c1", "m1")
        assert c == "c2" and m == "m2"

    def test_clear_and_parse(self):
        assert is_clear_assignment_value("")
        assert is_clear_assignment_value("null")
        assert not is_clear_assignment_value("abc")
        assert parse_assignment_ids_csv(" a, b , ,c ") == ["a", "b", "c"]


class TestFieldBuilders:
    def test_clear_and_set(self):
        cleared = build_clear_consultor_fields()
        assert cleared["assigned_consultor_ids"] == []
        assert cleared["assigned_consultor_id"] is None
        set_c = build_set_consultor_fields(["c1", "c2"], ["Ana", "Bruno"])
        assert set_c["assigned_consultor_id"] == "c1"
        assert set_c["consultor_name"] == "Ana"
        set_m = build_set_mediador_fields(["m1"], ["Mia"])
        assert set_m["mediador_name"] == "Mia"


class TestDetectNewlyAssigned:
    def test_detects_new_roles(self):
        newly = detect_newly_assigned(
            old_consultor_ids=["c1"],
            old_mediador_ids=[],
            old_indexacao=None,
            old_parceiro="p0",
            update_data={
                "assigned_consultor_ids": ["c1", "c2"],
                "assigned_mediador_ids": ["m1"],
                "assigned_indexacao_id": "i1",
                "assigned_parceiro_id": "p1",
            },
        )
        assert newly["consultores"] == ["c2"]
        assert newly["mediadores"] == ["m1"]
        assert newly["indexacao"] == ["i1"]
        assert newly["parceiro"] == ["p1"]


class TestAssignMeUnassignMe:
    def test_assign_me_as_consultor(self):
        process = {
            "assigned_consultor_ids": ["c0"],
            "consultor_names": ["Outro"],
            "assigned_mediador_ids": [],
            "mediador_names": [],
        }
        user = {"id": "u1", "name": "Eu", "role": UserRole.CONSULTOR}
        update, kind = build_assign_me_update(process, user)
        assert kind == "consultor"
        assert update["assigned_consultor_ids"] == ["c0", "u1"]

    def test_assign_me_already_assigned(self):
        from fastapi import HTTPException
        process = {
            "assigned_consultor_ids": ["u1"],
            "consultor_names": ["Eu"],
            "assigned_mediador_ids": [],
            "mediador_names": [],
        }
        user = {"id": "u1", "name": "Eu", "role": UserRole.CONSULTOR}
        try:
            build_assign_me_update(process, user)
            assert False
        except HTTPException as e:
            assert e.status_code == 400

    def test_unassign_me(self):
        process = {
            "assigned_consultor_ids": ["u1", "c2"],
            "consultor_names": ["Eu", "Outro"],
            "assigned_mediador_ids": [],
            "mediador_names": [],
        }
        user = {"id": "u1", "name": "Eu", "role": UserRole.CONSULTOR}
        update, removed = build_unassign_me_update(process, user)
        assert removed == ["consultor"]
        assert update["assigned_consultor_ids"] == ["c2"]
        assert update["assigned_consultor_id"] == "c2"
