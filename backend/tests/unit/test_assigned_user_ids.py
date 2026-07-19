"""Testes para get_all_assigned_user_ids (extraído de routes/portal.py)."""
from services.process_assignment import get_all_assigned_user_ids


class TestGetAllAssignedUserIds:
    def test_deduplicates_legacy_and_list_fields(self):
        process = {
            "assigned_consultor_ids": ["c1", "c2"],
            "assigned_consultor_id": "c1",
            "assigned_mediador_ids": ["m1"],
            "assigned_mediador_id": "m2",
            "assigned_indexacao_id": "i1",
            "assigned_parceiro_id": "p1",
        }
        ids = set(get_all_assigned_user_ids(process))
        assert ids == {"c1", "c2", "m1", "m2", "i1", "p1"}

    def test_empty_process(self):
        assert get_all_assigned_user_ids({}) == []
