"""Unit tests for Pacote DQ calendar helpers (role visibility + absence types)."""
from models.deadline import (
    DeadlineCreate,
    DeadlineUpdate,
    normalize_deadline_type,
)
from services.deadlines_api_helpers import (
    company_event_or_clauses,
    end_is_before_start,
    first_name,
    is_absence_type,
    parse_deadline_datetime,
    personal_deadline_or_clauses,
    pick_responsible,
    sees_team_calendar,
)


def test_normalize_deadline_type_aliases():
    assert normalize_deadline_type("Event") == "event"
    assert normalize_deadline_type("absence") == "absence"
    assert normalize_deadline_type("Férias") == "absence"
    assert normalize_deadline_type("ausencia") == "absence"
    assert normalize_deadline_type(None) == "deadline"
    assert normalize_deadline_type(None, allow_none=True) is None


def test_deadline_create_accepts_absence_without_process():
    created = DeadlineCreate(
        title="Férias de Agosto",
        due_date="2026-08-10",
        type="férias",
        all_day=True,
        end_date="2026-08-20",
    )
    assert created.type == "absence"
    assert created.process_id is None
    assert created.all_day is True
    assert created.end_date == "2026-08-20"


def test_deadline_update_accepts_all_day():
    upd = DeadlineUpdate(all_day=True, type="absence")
    assert upd.all_day is True
    assert upd.type == "absence"


def test_deadline_create_accepts_iso_datetimes():
    created = DeadlineCreate(
        title="Reunião banco",
        due_date="2026-08-21T09:00:00",
        end_date="2026-08-21T10:30:00",
        type="event",
        all_day=False,
    )
    assert created.due_date == "2026-08-21T09:00:00"
    assert created.end_date == "2026-08-21T10:30:00"
    assert created.all_day is False


def test_deadline_update_accepts_process_id_and_iso_times():
    upd = DeadlineUpdate(
        due_date="2026-08-21T11:00:00",
        end_date="2026-08-21T12:00:00",
        process_id="proc-1",
        all_day=False,
    )
    assert upd.process_id == "proc-1"
    assert upd.due_date == "2026-08-21T11:00:00"
    assert "process_id" in upd.model_fields_set


def test_sees_team_calendar_by_effective_role():
    admin = {"id": "a1", "role": "admin"}
    diretor = {"id": "d1", "role": "consultor", "additional_roles": ["diretor"]}
    consultor = {"id": "c1", "role": "consultor"}

    assert sees_team_calendar("diretor", diretor) is True
    assert sees_team_calendar("admin", admin) is True
    assert sees_team_calendar("ceo", admin) is True
    assert sees_team_calendar("consultor", consultor) is False
    assert sees_team_calendar("intermediario", consultor) is False
    assert sees_team_calendar("__all_roles__", {"role": "diretor"}) is True
    assert sees_team_calendar("__all_roles__", consultor) is False


def test_personal_deadline_or_clauses_include_assignments():
    clauses = personal_deadline_or_clauses("u1", ["p1", "p2"])
    assert {"assigned_user_ids": "u1"} in clauses
    assert {"created_by": "u1"} in clauses
    assert {"process_id": {"$in": ["p1", "p2"]}} in clauses
    empty = personal_deadline_or_clauses("u1", [])
    assert all("process_id" not in c for c in empty)


def test_company_event_or_clauses():
    clauses = company_event_or_clauses("acme", ["p1"])
    assert {"company_id": "acme"} in clauses
    assert {"company_id": {"$in": [None, "", "default"]}} in clauses
    assert {"process_id": {"$in": ["p1"]}} in clauses
    assert company_event_or_clauses("default", []) == []
    assert company_event_or_clauses(None, ["p1"]) == [
        {"process_id": {"$in": ["p1"]}}
    ]


def test_pick_responsible_and_first_name():
    rid, _ = pick_responsible({
        "assigned_user_ids": ["u-flavio"],
        "created_by": "u-other",
    })
    assert rid == "u-flavio"
    assert first_name("Flávio Silva") == "Flávio"
    assert first_name("") == ""
    assert is_absence_type("férias") is True
    assert is_absence_type("deadline") is False


def test_end_is_before_start_handles_date_and_datetime():
    assert end_is_before_start("2026-08-21T10:00:00", "2026-08-21T09:00:00") is True
    assert end_is_before_start("2026-08-21T09:00:00", "2026-08-21T10:30:00") is False
    assert end_is_before_start("2026-08-21", "2026-08-21") is False
    assert parse_deadline_datetime("2026-08-21T09:15:00").hour == 9


class _Cursor:
    def __init__(self, items):
        self.items = items

    async def to_list(self, _n):
        return self.items


def test_calendar_director_scopes_to_company_consultor_to_self():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from services.deadlines_api_calendar import run_get_calendar_deadlines

    company_processes = [{"id": "p-acme"}]
    all_deadlines = [
        {
            "id": "d1",
            "title": "Escritura Patrícia",
            "due_date": "2026-08-20",
            "process_id": "p-acme",
            "assigned_user_ids": ["u-flavio"],
            "type": "event",
            "company_id": "acme",
        },
        {
            "id": "d2",
            "title": "Férias",
            "due_date": "2026-08-10",
            "end_date": "2026-08-15",
            "process_id": None,
            "assigned_user_ids": ["u-ana"],
            "type": "absence",
            "all_day": True,
            "company_id": "acme",
        },
    ]

    captured = {"deadlines": []}

    def processes_find(query, projection=None):
        return _Cursor(company_processes)

    def deadlines_find(query, projection=None):
        captured["deadlines"].append(query)
        return _Cursor(all_deadlines)

    def users_find(query, projection=None):
        return _Cursor([
            {"id": "u-flavio", "name": "Flávio Silva"},
            {"id": "u-ana", "name": "Ana Costa"},
        ])

    mock_db = MagicMock()
    mock_db.processes.find = MagicMock(side_effect=processes_find)
    mock_db.deadlines.find = MagicMock(side_effect=deadlines_find)
    mock_db.users.find = MagicMock(side_effect=users_find)

    request = MagicMock()
    request.headers = {"X-Active-Role": "diretor", "X-Company-Id": "acme"}

    async def _run():
        with patch("services.deadlines_api_calendar.db", mock_db):
            with patch(
                "services.deadlines_api_calendar.get_effective_role",
                return_value="diretor",
            ):
                with patch(
                    "services.deadlines_api_calendar.get_active_company_id_async",
                    new_callable=AsyncMock,
                    return_value="acme",
                ):
                    director_events = await run_get_calendar_deadlines(
                        None, None,
                        {
                            "id": "u-dir",
                            "role": "consultor",
                            "additional_roles": ["diretor"],
                        },
                        request,
                    )
                    director_query = captured["deadlines"][-1]

        with patch("services.deadlines_api_calendar.db", mock_db):
            with patch(
                "services.deadlines_api_calendar.get_effective_role",
                return_value="consultor",
            ):
                with patch(
                    "services.deadlines_api_calendar.get_active_company_id_async",
                    new_callable=AsyncMock,
                    return_value="acme",
                ):
                    await run_get_calendar_deadlines(
                        None, None,
                        {"id": "u-flavio", "role": "consultor"},
                        request,
                    )
                    consultor_query = captured["deadlines"][-1]

        return director_events, director_query, consultor_query

    director_events, director_query, consultor_query = asyncio.run(_run())
    assert any(e.get("responsible_name") == "Flávio Silva" for e in director_events)
    assert "$or" in director_query
    assert {"company_id": "acme"} in director_query["$or"]
    assert consultor_query["$or"]
    assert {"assigned_user_ids": "u-flavio"} in consultor_query["$or"]
