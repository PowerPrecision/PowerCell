"""O worker, ligado pela primeira vez em produção, mostrou três defeitos (18 Out 2026).

Nenhum era visível enquanto o serviço não existia (o painel do Motor mostrava
«Nunca correu» e a hipótese era «o worker está em baixo»). O log do primeiro
arranque trouxe-os:

1. `TaskQueueService.get_next_task() got an unexpected keyword argument
   'excluir_tipos'` — a cada 5 s. O `worker_loop` passa o filtro, a fila Mongo
   aceita-o, e o invólucro `TaskQueueService` pelo meio não. Os testes da fila
   chamavam a fila directamente: testavam as duas pontas e nunca a junção.
2. `can't subtract offset-naive and offset-aware datetimes` nos countdowns de
   pré-aprovação — e como as tarefas agendadas corriam seguidas num só `try`,
   essa ficha parava as nove tarefas seguintes (limpezas e relatórios).
3. `match_leads_to_clients` nunca existiu: o job `lead_matching` falhava a cada 30 min com
   ImportError. Decisão do dono do produto: o job foi RETIRADO (ver `TestOJobLeadMatchingFoiRetirado`).
"""
from __future__ import annotations

import ast
import inspect
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from services import scheduled_tasks
from services.scheduled_tasks import ScheduledTasksService, _data_iso_com_fuso
from services.task_queue import TaskQueueService

BACKEND = Path(__file__).resolve().parents[2]


class TestOInvolucroDaFilaDeixaPassarOsFiltros:
    @pytest.mark.asyncio
    async def test_excluir_tipos_chega_a_fila(self):
        # Um nível ABAIXO: o que sai para a fila Mongo são os PARÂMETROS.
        with patch("services.task_queue_mongo.get_next_task", new=AsyncMock(return_value=None)) as fila:
            await TaskQueueService().get_next_task(excluir_tipos=["forcar_job"])
        fila.assert_awaited_once_with(tipos=None, excluir_tipos=["forcar_job"])

    @pytest.mark.asyncio
    async def test_tipos_chega_a_fila(self):
        with patch("services.task_queue_mongo.get_next_task", new=AsyncMock(return_value=None)) as fila:
            await TaskQueueService().get_next_task(tipos=["forcar_job"])
        fila.assert_awaited_once_with(tipos=["forcar_job"], excluir_tipos=None)

    def test_tudo_o_que_o_worker_passa_o_involucro_aceita(self):
        # Inventário por AST: cada keyword de `task_queue.get_next_task(...)` em
        # worker.py tem de existir na assinatura do invólucro.
        arvore = ast.parse((BACKEND / "worker.py").read_text(encoding="utf-8"))
        usadas = {
            kw.arg
            for no in ast.walk(arvore)
            if isinstance(no, ast.Call)
            and isinstance(no.func, ast.Attribute)
            and no.func.attr == "get_next_task"
            and isinstance(no.func.value, ast.Name)
            and no.func.value.id == "task_queue"
            for kw in no.keywords
        }
        assert usadas, "o leitor não encontrou a chamada — a guarda ficou cega"
        aceites = set(inspect.signature(TaskQueueService.get_next_task).parameters)
        assert usadas <= aceites, f"o worker passa {usadas - aceites}, que o invólucro não aceita"


class TestDatasComFuso:
    @pytest.mark.parametrize(
        "texto",
        ["2026-09-01", "2026-09-01T10:00:00", "2026-09-01T10:00:00Z", "2026-09-01T10:00:00+00:00",
         "2026-09-01T11:00:00+01:00"],
    )
    def test_devolve_sempre_com_fuso(self, texto):
        assert _data_iso_com_fuso(texto).tzinfo is not None

    def test_sem_fuso_assume_utc(self):
        assert _data_iso_com_fuso("2026-09-01T10:00:00") == datetime(2026, 9, 1, 10, tzinfo=timezone.utc)

    @pytest.mark.parametrize("lixo", ["", "ontem", None])
    def test_entrada_ilegivel_levanta_o_que_os_chamadores_tratam(self, lixo):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            _data_iso_com_fuso(lixo)


class TestCountdownDePreAprovacao:
    @pytest.mark.asyncio
    async def test_data_sem_fuso_nao_rebenta_e_avisa(self, fake_async_db):
        # Aprovada há 59 dias, sem fuso (a forma de um `date` do formulário):
        # faltam 30 dias (e uma fracção), que é um dos limiares de aviso.
        aprovada = (datetime.now(timezone.utc) - timedelta(days=59)).date().isoformat()
        await fake_async_db.processes.insert_one({
            "id": "p1", "client_name": "Ana", "consultor_id": "u1",
            "credit_data": {"bank_approval_date": aprovada},
        })
        servico = ScheduledTasksService()
        servico.db = fake_async_db

        criadas = await servico.check_pre_approval_countdown()

        assert criadas == 1
        aviso = await fake_async_db.notifications.find_one({"user_id": "u1"})
        assert aviso["type"] == "pre_approval_countdown"

    @pytest.mark.asyncio
    async def test_data_com_fuso_continua_a_funcionar(self, fake_async_db):
        aprovada = (datetime.now(timezone.utc) - timedelta(days=59)).isoformat().replace("+00:00", "Z")
        await fake_async_db.processes.insert_one({
            "id": "p1", "consultor_id": "u1", "credit_data": {"bank_approval_date": aprovada},
        })
        servico = ScheduledTasksService()
        servico.db = fake_async_db
        assert await servico.check_pre_approval_countdown() == 1


class TestUmaTarefaQueFalhaNaoParaAsOutras:
    @pytest.mark.asyncio
    async def test_as_seguintes_correm_e_o_ciclo_falha_no_fim(self):
        servico = ScheduledTasksService()
        chamadas: list[str] = []

        def _ok(nome):
            async def _f():
                chamadas.append(nome)
                return 0
            return _f

        async def _rebenta():
            chamadas.append("countdown")
            raise TypeError("ficha com dados fora do esperado")

        nomes = [
            "check_expiring_documents", "check_upcoming_deadlines", "check_tasks_due_soon",
            "check_clients_waiting_too_long", "expire_stale_partner_leads",
            "check_document_expirations_watchdog", "send_monthly_document_reminder",
            "check_stale_processes", "cleanup_old_notifications", "cleanup_temp_files",
            "cleanup_scraper_cache", "send_weekly_ai_report", "send_weekly_ceo_report", "run_index_sla",
        ]
        for nome in nomes:
            setattr(servico, nome, _ok(nome))
        servico.check_pre_approval_countdown = _rebenta
        servico.connect = AsyncMock()
        servico.disconnect = AsyncMock()

        with pytest.raises(RuntimeError, match="countdown de pré-aprovação"):
            await servico.run_all_tasks()

        # as 14 restantes correram, incluindo as que vêm DEPOIS da que falhou
        assert set(nomes) <= set(chamadas)
        assert "send_weekly_ceo_report" in chamadas

    @pytest.mark.asyncio
    async def test_sem_falhas_o_ciclo_termina_normalmente(self):
        servico = ScheduledTasksService()
        for nome in [
            "check_expiring_documents", "check_upcoming_deadlines", "check_tasks_due_soon",
            "check_pre_approval_countdown", "check_clients_waiting_too_long",
            "expire_stale_partner_leads", "check_document_expirations_watchdog",
            "send_monthly_document_reminder", "check_stale_processes", "cleanup_old_notifications",
            "cleanup_temp_files", "cleanup_scraper_cache", "send_weekly_ai_report",
            "send_weekly_ceo_report", "run_index_sla", "consolidate_partner_lead_files",
        ]:
            setattr(servico, nome, AsyncMock(return_value=0))
        servico.connect = AsyncMock()
        servico.disconnect = AsyncMock()
        await servico.run_all_tasks()
        servico.disconnect.assert_awaited_once()


def test_o_modulo_nao_tem_fromisoformat_cru_comparado_com_utc():
    # Guarda de fonte: as datas lidas do Mongo passam pelo ponto único.
    fonte = Path(scheduled_tasks.__file__).read_text(encoding="utf-8")
    assert "datetime.fromisoformat(approval_date_str" not in fonte
    assert "datetime.fromisoformat(last_update" not in fonte


class TestOJobLeadMatchingFoiRetirado:
    """Apagado, não desligado: um job adormecido é um convite a religá-lo."""

    def test_nao_esta_declarado_nem_tem_executor(self):
        from services.job_executors import EXECUTORES
        from services.job_heartbeat import JOBS_DECLARADOS

        assert "lead_matching" not in {j["chave"] for j in JOBS_DECLARADOS}
        assert "lead_matching" not in EXECUTORES

    def test_o_codigo_do_worker_ja_nao_chama_a_funcao_que_nunca_existiu(self):
        for ficheiro in ("worker.py", "services/job_executors.py"):
            fonte = (BACKEND / ficheiro).read_text(encoding="utf-8")
            assert "match_leads_to_clients" not in fonte.replace("`match_leads_to_clients`", ""), ficheiro
            assert "_executar_matching_de_leads" not in fonte, ficheiro

    def test_todos_os_jobs_declarados_tem_executor_e_vice_versa(self):
        """Contraprova da retirada: declarar sem executor (ou o contrário) é como o job fantasma nasceu."""
        from services.job_executors import EXECUTORES
        from services.job_heartbeat import JOBS_DECLARADOS

        assert set(EXECUTORES) == {j["chave"] for j in JOBS_DECLARADOS}


class TestOWatchdogDeValidadeNaoEngoleOErro:
    """`strptime` devolve uma data sem fuso e `today` tem-no: a subtracção levantava TypeError, o
    `except` por documento engolia-o e NENHUM documento a expirar gerava alerta (visto nos logs
    do Render de 2026-10-18: «[WATCHDOG] Erro ao processar documento … offset-naive»)."""

    @pytest.mark.asyncio
    async def test_documento_a_expirar_gera_a_notificacao(self, fake_async_db):
        expira = (datetime.now(timezone.utc) + timedelta(days=10)).strftime("%Y-%m-%d")
        await fake_async_db.processes.insert_one({
            "id": "p1", "client_name": "Ana", "assigned_consultor_id": "u1",
        })
        await fake_async_db.document_metadata.insert_one({
            "id": "d1", "process_id": "p1", "expiry_date": expira, "ai_category": "Cartão de Cidadão",
        })
        servico = ScheduledTasksService()
        servico.db = fake_async_db

        criadas = await servico.check_document_expirations_watchdog()

        assert criadas == 1
        aviso = await fake_async_db.notifications.find_one({"user_id": "u1"})
        assert aviso["type"] == "document_expiry_watchdog"
        assert "Ana" in aviso["message"]
        marcado = await fake_async_db.document_metadata.find_one({"id": "d1"})
        assert marcado["expiry_alert_sent"] is True
