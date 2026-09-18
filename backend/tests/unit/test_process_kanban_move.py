"""Unit tests for process_kanban_move helpers.

PACOTE 11 (Eixo 1 — No-Hardcoding): ``resolve_workflow_purpose_flags``
passou a resolver os fallbacks DINAMICAMENTE da colecção
``workflow_statuses`` (via services/workflow_lookup.py) — os testes de
fallback passam a semear o workflow_statuses fake (com as flags) em vez
de confiarem em listas hardcoded no código.
"""
import pytest

from services.process_kanban_move import (
    resolve_workflow_purpose_flags,
    build_kanban_move_update,
)


def _seed_workflow_statuses(fake_db, statuses):
    """Semeia workflow_statuses no fake (docs simples com flags)."""
    for doc in statuses:
        fake_db.workflow_statuses.docs.append(dict(doc))


class TestResolveWorkflowPurposeFlags:
    @pytest.mark.asyncio
    async def test_explicit_flags_win(self, fake_async_db):
        flags = await resolve_workflow_purpose_flags(
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

    @pytest.mark.asyncio
    async def test_fallback_dynamic_concluidos(self, fake_async_db, monkeypatch):
        import services.workflow_lookup as wl
        monkeypatch.setattr(wl, "db", fake_async_db)
        _seed_workflow_statuses(fake_async_db, [
            {"name": "fase_bancaria", "order": 8, "trigger_countdown": True},
            {"name": "concluidos", "order": 13, "trigger_finance": True,
             "is_active": False},
        ])
        flags = await resolve_workflow_purpose_flags({}, "concluidos")
        assert flags["trigger_finance"] is True
        assert flags["is_active"] is False

    @pytest.mark.asyncio
    async def test_fallback_dynamic_fase_bancaria(self, fake_async_db, monkeypatch):
        import services.workflow_lookup as wl
        monkeypatch.setattr(wl, "db", fake_async_db)
        _seed_workflow_statuses(fake_async_db, [
            {"name": "fase_bancaria", "order": 8, "trigger_countdown": True},
        ])
        flags = await resolve_workflow_purpose_flags({}, "fase_bancaria")
        assert flags["trigger_countdown"] is True
        assert flags["is_active"] is True

    @pytest.mark.asyncio
    async def test_fallback_dynamic_escritura_agendada(self, fake_async_db, monkeypatch):
        import services.workflow_lookup as wl
        monkeypatch.setattr(wl, "db", fake_async_db)
        _seed_workflow_statuses(fake_async_db, [
            {"name": "escritura_agendada", "order": 12,
             "trigger_property_check": True, "trigger_deed_reminder": True},
        ])
        flags = await resolve_workflow_purpose_flags({}, "escritura_agendada")
        assert flags["trigger_deed_reminder"] is True
        assert flags["trigger_property_check"] is True

    @pytest.mark.asyncio
    async def test_fallback_dynamic_ch_aprovado_property(self, fake_async_db, monkeypatch):
        import services.workflow_lookup as wl
        monkeypatch.setattr(wl, "db", fake_async_db)
        _seed_workflow_statuses(fake_async_db, [
            {"name": "ch_aprovado", "order": 10, "trigger_property_check": True},
        ])
        flags = await resolve_workflow_purpose_flags({}, "ch_aprovado")
        assert flags["trigger_property_check"] is True
        assert flags["trigger_deed_reminder"] is False

    @pytest.mark.asyncio
    async def test_fallback_sem_workflow_nao_dispara(self, fake_async_db, monkeypatch):
        """Workflow vazio → nenhum fallback dispara (sem hardcoding)."""
        import services.workflow_lookup as wl
        monkeypatch.setattr(wl, "db", fake_async_db)
        flags = await resolve_workflow_purpose_flags({}, "concluidos")
        assert flags["trigger_finance"] is False
        assert flags["is_active"] is True


class TestBuildKanbanMoveUpdate:
    def test_sets_status_and_active(self):
        data = build_kanban_move_update("fase_documental", True)
        assert data["status"] == "fase_documental"
        assert data["is_active"] is True
        assert "updated_at" in data
