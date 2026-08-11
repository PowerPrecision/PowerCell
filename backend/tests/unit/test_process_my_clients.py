"""
Testes unitários para services.process_my_clients.
"""
from services.process_my_clients import (
    format_lead_as_my_client_row,
    finalize_lead_row,
    my_clients_sort_key,
    group_tasks_by_process,
    build_pending_actions,
    build_my_clients_process_row,
)


class TestFormatLead:
    def test_maps_contacto_and_flags(self):
        row = format_lead_as_my_client_row({
            "id": "L1",
            "nome": "Ana",
            "contacto": {"email": "a@x.com", "telefone": "900"},
            "created_at": "2026-01-01",
        })
        assert row["is_lead"] is True
        assert row["client_name"] == "Ana"
        assert row["client_email"] == "a@x.com"
        assert row["status"] == "lead"

    def test_finalize_lead_flags(self):
        row = finalize_lead_row(format_lead_as_my_client_row({"id": "L1", "nome": "X"}))
        assert row["has_unread_messages"] is False
        assert row["has_new_documents"] is False
        assert row["latest_activity_note"] is None


class TestSortAndGroup:
    def test_leads_first_then_phase_order(self):
        status_map = {
            "analise": {"order": 2},
            "documents": {"order": 1},
        }
        key = my_clients_sort_key(status_map)
        items = [
            {"is_lead": False, "status": "analise", "client_name": "B"},
            {"is_lead": True, "client_name": "Z"},
            {"is_lead": False, "status": "documents", "client_name": "A"},
        ]
        sorted_items = sorted(items, key=key)
        assert sorted_items[0]["is_lead"] is True
        assert sorted_items[1]["status"] == "documents"
        assert sorted_items[2]["status"] == "analise"

    def test_group_tasks(self):
        grouped = group_tasks_by_process([
            {"process_id": "p1", "title": "T1"},
            {"process_id": "p1", "title": "T2"},
            {"process_id": "p2", "title": "T3"},
            {"title": "orphan"},
        ])
        assert len(grouped["p1"]) == 2
        assert len(grouped["p2"]) == 1


class TestPendingActionsAndRow:
    def test_pending_actions_limit_and_doc_hint(self):
        tasks = [{"title": f"T{i}", "priority": "high"} for i in range(5)]
        actions = build_pending_actions(tasks, "fase_documental")
        assert len(actions) == 5  # 3 tasks + info + document
        assert actions[3]["type"] == "info"
        assert actions[4]["type"] == "document"

    def test_build_process_row(self):
        row = build_my_clients_process_row(
            {
                "id": "p1",
                "client_id": "c1",
                "process_number": "PC-1",
                "client_name": "Cliente",
                "status": "analise",
                "assigned_consultor_id": "u1",
                "property_id": "prop1",
            },
            status_map={"analise": {"label": "Análise", "color": "#111", "order": 1}},
            tasks_by_process={"p1": [{"title": "Rever docs", "priority": "high"}]},
            consultor_map={"u1": "João"},
            unread_map={"p1": True},
            new_docs_map={"p1": False},
            notes_map={"p1": {
                "latest_activity_note": "OK",
                "latest_activity_note_at": "t",
                "latest_activity_note_by": "João",
            }},
        )
        assert row["status_label"] == "Análise"
        assert row["consultor_name"] == "João"
        assert row["has_unread_messages"] is True
        assert row["has_property"] is True
        assert row["pending_count"] == 1
        assert row["latest_activity_note"] == "OK"
