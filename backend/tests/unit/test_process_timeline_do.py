"""Unit tests for PACOTE DO.1 timeline helper and PACOTE DO.2 portal calendar filter."""
from services.process_timeline import build_summary_timeline
from services.portal_events import build_portal_events_filter, serialize_portal_event


def test_build_summary_timeline_adds_created_when_missing():
    process = {"id": "p1", "created_at": "2026-08-01T10:00:00+00:00"}
    history = [
        {
            "id": "h1",
            "action": "Alterou estado",
            "field": "status",
            "old_value": "clientes_espera",
            "new_value": "fase_documental",
            "user_name": "Ana",
            "created_at": "2026-08-02T10:00:00+00:00",
        }
    ]
    events = build_summary_timeline(process, history, limit=10)
    assert events[0]["kind"] == "status"
    assert events[0]["title"] == "Alterou estado"
    assert any(e["kind"] == "created" for e in events)
    assert events[-1]["title"] == "Processo criado"


def test_build_summary_timeline_does_not_duplicate_created():
    process = {"id": "p1", "created_at": "2026-08-01T10:00:00+00:00"}
    history = [
        {
            "id": "h0",
            "action": "Criou processo",
            "user_name": "João",
            "created_at": "2026-08-01T10:00:00+00:00",
        }
    ]
    events = build_summary_timeline(process, history)
    created = [e for e in events if e["kind"] == "created"]
    assert len(created) == 1
    assert created[0]["title"] == "Criou processo"


def test_build_summary_timeline_respects_limit():
    history = [
        {"id": str(i), "action": f"Evento {i}", "created_at": f"2026-08-0{i}T00:00:00"}
        for i in range(1, 6)
    ]
    events = build_summary_timeline({"id": "p"}, history, limit=2)
    assert len(events) == 2


def test_portal_events_filter_upcoming_vs_all():
    upcoming = build_portal_events_filter("p1", "2026-08-18", include_past=False)
    assert upcoming["visible_to_client"] is True
    assert upcoming["due_date"] == {"$gte": "2026-08-18"}
    all_events = build_portal_events_filter("p1", "2026-08-18", include_past=True)
    assert "due_date" not in all_events
    assert all_events["completed"] == {"$ne": True}


def test_serialize_portal_event_strips_internals():
    raw = {
        "id": "e1",
        "title": "Escritura",
        "description": "Cartório",
        "due_date": "2026-09-01",
        "type": "event",
        "priority": "high",
        "_id": "mongo",
        "assigned_user_ids": ["u1"],
        "visible_to_client": True,
    }
    out = serialize_portal_event(raw)
    assert out["id"] == "e1"
    assert out["type"] == "event"
    assert "_id" not in out
    assert "assigned_user_ids" not in out
    assert "visible_to_client" not in out
