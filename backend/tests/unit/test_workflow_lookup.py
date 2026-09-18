"""PACOTE 11 — Unit tests do workflow_lookup (resolução dinâmica de fases).

Eixo 1 (No-Hardcoding): as fases do workflow têm de ser resolvidas
SEMPRE da colecção ``workflow_statuses`` — nunca de listas cravadas.
"""
from services.workflow_lookup import (
    ensure_workflow_purpose_flags_backfill,
    get_first_workflow_status,
    get_flagged_workflow_status_names,
    get_inactive_workflow_status_names,
)


class TestGetFirstWorkflowStatus:
    async def test_primeira_fase_activa_por_order(self, fake_async_db, monkeypatch):
        import services.workflow_lookup as wl
        monkeypatch.setattr(wl, "db", fake_async_db)
        fake_async_db.workflow_statuses.docs.extend([
            {"id": "3", "name": "concluidos", "order": 13, "is_active": False},
            {"id": "1", "name": "clientes_espera", "order": 1, "is_active": True},
            {"id": "2", "name": "fase_documental", "order": 2, "is_active": True},
        ])
        assert await get_first_workflow_status() == "clientes_espera"

    async def test_fallback_para_primeira_existente(self, fake_async_db, monkeypatch):
        import services.workflow_lookup as wl
        monkeypatch.setattr(wl, "db", fake_async_db)
        fake_async_db.workflow_statuses.docs.extend([
            {"id": "1", "name": "fase_documental", "order": 2},
        ])
        assert await get_first_workflow_status() == "fase_documental"

    async def test_vazio_devolve_none(self, fake_async_db, monkeypatch):
        import services.workflow_lookup as wl
        monkeypatch.setattr(wl, "db", fake_async_db)
        assert await get_first_workflow_status() is None


class TestGetFlaggedWorkflowStatusNames:
    async def test_nomes_com_flag_true(self, fake_async_db, monkeypatch):
        import services.workflow_lookup as wl
        monkeypatch.setattr(wl, "db", fake_async_db)
        fake_async_db.workflow_statuses.docs.extend([
            {"name": "fase_bancaria", "trigger_countdown": True},
            {"name": "concluidos", "trigger_finance": True},
            {"name": "clientes_espera", "trigger_finance": False},
        ])
        assert await get_flagged_workflow_status_names("trigger_finance") == ["concluidos"]
        assert await get_flagged_workflow_status_names("trigger_countdown") == ["fase_bancaria"]

    async def test_flag_invalida_devolve_vazio(self, fake_async_db, monkeypatch):
        import services.workflow_lookup as wl
        monkeypatch.setattr(wl, "db", fake_async_db)
        assert await get_flagged_workflow_status_names("flag_inexistente") == []


class TestGetInactiveWorkflowStatusNames:
    async def test_apenas_is_active_false(self, fake_async_db, monkeypatch):
        import services.workflow_lookup as wl
        monkeypatch.setattr(wl, "db", fake_async_db)
        fake_async_db.workflow_statuses.docs.extend([
            {"name": "concluidos", "is_active": False},
            {"name": "desistencias", "is_active": False},
            {"name": "fase_documental", "is_active": True},
        ])
        names = await get_inactive_workflow_status_names()
        assert set(names) == {"concluidos", "desistencias"}


class TestEnsureWorkflowPurposeFlagsBackfill:
    async def test_semeia_flags_em_docs_sem_elas(self, fake_async_db, monkeypatch):
        import services.workflow_lookup as wl
        monkeypatch.setattr(wl, "db", fake_async_db)
        fake_async_db.workflow_statuses.docs.extend([
            {"id": "c1", "name": "concluidos", "order": 13},
            {"id": "c2", "name": "fase_bancaria", "order": 8},
            {"id": "c3", "name": "escritura_agendada", "order": 12},
        ])

        result = await ensure_workflow_purpose_flags_backfill()

        by_name = {d["name"]: d for d in fake_async_db.workflow_statuses.docs}
        assert by_name["concluidos"]["trigger_finance"] is True
        assert by_name["concluidos"]["is_active"] is False
        assert by_name["fase_bancaria"]["trigger_countdown"] is True
        assert by_name["escritura_agendada"]["trigger_property_check"] is True
        assert by_name["escritura_agendada"]["trigger_deed_reminder"] is True
        assert result["updated"] == 3

    async def test_idempotente_nao_toca_docs_com_flags(self, fake_async_db, monkeypatch):
        import services.workflow_lookup as wl
        monkeypatch.setattr(wl, "db", fake_async_db)
        fake_async_db.workflow_statuses.docs.extend([
            {"id": "c1", "name": "concluidos", "order": 13,
             "trigger_finance": False, "is_active": True},
        ])

        result = await ensure_workflow_purpose_flags_backfill()

        by_name = {d["name"]: d for d in fake_async_db.workflow_statuses.docs}
        # Flags EXISTENTES (mesmo False) nunca são sobrescritas.
        assert by_name["concluidos"]["trigger_finance"] is False
        assert by_name["concluidos"]["is_active"] is True
        assert result["updated"] == 0
        assert result["skipped"] == 1
