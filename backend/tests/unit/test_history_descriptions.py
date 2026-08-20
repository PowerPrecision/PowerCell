"""PACOTE DS — descrições ricas do histórico de auditoria."""
from datetime import datetime, timezone

from services.history import (
    build_history_description,
    classify_history_event,
    enrich_history_entry,
)


def test_status_change_builds_phase_sentence():
    item = {
        "action": "Alterou estado",
        "field": "status",
        "old_value": "clientes_espera",
        "new_value": "fase_documental",
    }
    assert classify_history_event(item) == "status_change"
    assert build_history_description(item) == (
        "Fase alterada de clientes_espera para fase_documental"
    )


def test_kanban_move_is_status_change():
    item = {
        "action": "Moveu processo",
        "field": "status",
        "old_value": "fase_documental",
        "new_value": "fase_bancaria",
    }
    assert classify_history_event(item) == "status_change"
    assert "fase_documental" in build_history_description(item)
    assert "fase_bancaria" in build_history_description(item)


def test_field_edit_includes_old_and_new():
    item = {
        "action": "Alterou dados pessoais",
        "field": "nif",
        "old_value": "111",
        "new_value": "222",
    }
    assert classify_history_event(item) == "edit"
    assert build_history_description(item) == (
        "Alterou dados pessoais: nif alterado de 111 para 222"
    )


def test_document_and_email_and_task_types():
    assert classify_history_event({"action": "Carregou documento CC.pdf"}) == "document"
    assert classify_history_event({"action": "Enviou email"}) == "email"
    assert classify_history_event({"action": "Criou tarefa", "field": "tarefa"}) == "task"
    assert classify_history_event({"action": "Atribuiu consultor"}) == "assignment"
    assert classify_history_event({"action": "Adicionou comentário", "comment": "ok"}) == "comment"


def test_enrich_history_entry_adds_description_and_event_type():
    raw = {
        "id": "h1",
        "process_id": "p1",
        "user_id": "u1",
        "user_name": "Ana",
        "action": "Alterou estado",
        "field": "status",
        "old_value": "X",
        "new_value": "Y",
        "created_at": datetime(2026, 8, 20, 10, 30, tzinfo=timezone.utc),
    }
    out = enrich_history_entry(raw)
    assert out["event_type"] == "status_change"
    assert out["description"] == "Fase alterada de X para Y"
    assert out["created_at"].startswith("2026-08-20T10:30:00")
    assert out["user_name"] == "Ana"


def test_timeline_uses_rich_status_description():
    from services.process_timeline import build_summary_timeline

    events = build_summary_timeline(
        {"id": "p1"},
        [{
            "id": "h1",
            "action": "Alterou estado",
            "field": "status",
            "old_value": "A",
            "new_value": "B",
            "user_name": "Ana",
            "created_at": "2026-08-02T10:00:00+00:00",
        }],
    )
    status = next(e for e in events if e["kind"] == "status")
    assert status["description"] == "Fase alterada de A para B"
