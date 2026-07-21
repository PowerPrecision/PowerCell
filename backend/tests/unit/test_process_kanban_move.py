"""Unit tests for process_kanban_move helpers."""
from services.process_kanban_move import (
    resolve_workflow_purpose_flags,
    build_kanban_move_update,
)


class TestResolveWorkflowPurposeFlags:
    def test_explicit_flags_win(self):
        flags = resolve_workflow_purpose_flags(
            {
                "trigger_finance": True,
                "trigger_countdown": False,
                "trigger_property_check": True,
                "trigger_deed_reminder": False,
                "is_active": True,
            },
            "whatever",
        )
        assert flags["trigger_finance"] is True
        assert flags["trigger_countdown"] is False
        assert flags["is_active"] is True

    def test_fallback_concluidos(self):
        flags = resolve_workflow_purpose_flags({}, "concluidos")
        assert flags["trigger_finance"] is True
        assert flags["is_active"] is False

    def test_fallback_fase_bancaria(self):
        flags = resolve_workflow_purpose_flags({}, "fase_bancaria")
        assert flags["trigger_countdown"] is True
        assert flags["is_active"] is True

    def test_fallback_escritura_agendada(self):
        flags = resolve_workflow_purpose_flags({}, "escritura_agendada")
        assert flags["trigger_deed_reminder"] is True
        assert flags["trigger_property_check"] is True

    def test_fallback_ch_aprovado_property(self):
        flags = resolve_workflow_purpose_flags({}, "ch_aprovado")
        assert flags["trigger_property_check"] is True
        assert flags["trigger_deed_reminder"] is False


class TestBuildKanbanMoveUpdate:
    def test_sets_status_and_active(self):
        data = build_kanban_move_update("fase_documental", True)
        assert data["status"] == "fase_documental"
        assert data["is_active"] is True
        assert "updated_at" in data
