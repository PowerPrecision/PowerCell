"""
A tarefa «Email de acesso ao Portal» nunca ficava presa em «retry agendado» (QA, Out 2026).

O envio directo falha → o retry vai para a fila → a tarefa fica em «Envio directo falhou — retry
agendado na fila» e quem a fecha é o consumidor da fila. Só que (1) o retry arrancava SEM a
tarefa que o originou (criava outra, sem utilizador, e nunca fechava a original) e (2) o
consumidor nem sempre corre. Resultado: a tarefa ficava «a tentar» PARA SEMPRE, e o toast do ecrã
(`duration: Infinity`) só saía quando alguém o fechava à mão.

Aqui afirma-se: o retry transporta e fecha a tarefa; um retry que falha é definitivo (sem ciclo);
e uma tarefa que ninguém processou fecha-se por prazo, como FALHADA — ou como concluída se o email
afinal foi entregue.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import client_portal_email as mod
from services import email_delivery_status as eds
from services import task_log_service as tls_mod
from services.email_delivery_status import (
    MINUTOS_ATE_O_RETRY_SER_DADO_POR_PERDIDO,
    MOTIVO_RETRY_NAO_PROCESSADO,
    TIPO_DA_TAREFA,
    fechar_envios_presos,
)


def _ha(minutos: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutos)).isoformat()


def _tarefa(task_id="task_1", *, user="u-1", status="processing", minutos=30,
            client_id="cli-1", kind=TIPO_DA_TAREFA):
    return {
        "task_id": task_id, "id": task_id, "user_id": user, "status": status,
        "task_type": "EMAIL_SEND", "title": "Email de acesso ao Portal",
        "created_at": _ha(minutos), "progress": 0,
        "progress_message": "Envio directo falhou — retry agendado na fila.",
        "metadata": {"client_id": client_id, "kind": kind},
    }


@pytest.fixture
def bd(fake_async_db):
    with patch.object(eds, "db", fake_async_db), patch.object(tls_mod, "db", fake_async_db), \
         patch.object(mod, "db", fake_async_db):
        yield fake_async_db


class TestFecharEnviosPresos:
    @pytest.mark.asyncio
    async def test_a_tarefa_antiga_em_retry_fecha_como_falhada_com_o_motivo(self, bd):
        await bd.clients.insert_one({"id": "cli-1", "portal_email_delivery": {"status": "retry_scheduled"}})
        await bd.task_logs.insert_one(_tarefa())

        assert await fechar_envios_presos() == 1

        tarefa = await bd.task_logs.find_one({"task_id": "task_1"})
        assert tarefa["status"] == "failed"
        assert tarefa["error_message"] == MOTIVO_RETRY_NAO_PROCESSADO
        cliente = await bd.clients.find_one({"id": "cli-1"})
        # O cliente passa a «failed»: é a fonte do alerta crítico e do indicador vermelho.
        assert cliente["portal_email_delivery"]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_a_tarefa_recente_nao_se_toca(self, bd):
        await bd.task_logs.insert_one(_tarefa(minutos=MINUTOS_ATE_O_RETRY_SER_DADO_POR_PERDIDO - 5))

        assert await fechar_envios_presos() == 0
        assert (await bd.task_logs.find_one({"task_id": "task_1"}))["status"] == "processing"

    @pytest.mark.asyncio
    async def test_pending_tambem_fecha(self, bd):
        await bd.task_logs.insert_one(_tarefa(status="pending"))
        assert await fechar_envios_presos() == 1

    @pytest.mark.asyncio
    async def test_outras_tarefas_nao_se_tocam(self, bd):
        await bd.task_logs.insert_many([
            _tarefa("t-outra", kind="voice_note"),
            _tarefa("t-concluida", status="completed"),
            _tarefa("t-falhada", status="failed"),
        ])

        assert await fechar_envios_presos() == 0
        estados = {t["task_id"]: t["status"] for t in await bd.task_logs.find({}).to_list(10)}
        assert estados == {"t-outra": "processing", "t-concluida": "completed", "t-falhada": "failed"}

    @pytest.mark.asyncio
    async def test_se_o_email_afinal_foi_entregue_fecha_como_concluida(self, bd):
        # O retry entregou mas não conseguiu fechar a tarefa: dizer «falhou» seria mentir.
        await bd.clients.insert_one({"id": "cli-1", "portal_email_delivery": {"status": "sent"}})
        await bd.task_logs.insert_one(_tarefa())

        await fechar_envios_presos()

        tarefa = await bd.task_logs.find_one({"task_id": "task_1"})
        assert tarefa["status"] == "completed"
        assert (await bd.clients.find_one({"id": "cli-1"}))["portal_email_delivery"]["status"] == "sent"

    @pytest.mark.asyncio
    async def test_restringe_ao_dono_quando_se_pede(self, bd):
        await bd.task_logs.insert_many([_tarefa("t-a", user="u-a"), _tarefa("t-b", user="u-b")])

        assert await fechar_envios_presos(user_id="u-a") == 1
        assert (await bd.task_logs.find_one({"task_id": "t-b"}))["status"] == "processing"

    @pytest.mark.asyncio
    async def test_nunca_levanta(self):
        bd_partida = MagicMock()
        bd_partida.__getitem__ = MagicMock(side_effect=RuntimeError("bd em baixo"))
        with patch.object(eds, "db", bd_partida):
            assert await fechar_envios_presos() == 0


class TestOMonitorEAListagemFechamAsPresas:
    @pytest.mark.asyncio
    async def test_a_listagem_de_tarefas_activas_ja_nao_devolve_a_tarefa_presa_como_activa(self, bd):
        from services.task_api_background import _merge_task_logs_into_tasks

        await bd.clients.insert_one({"id": "cli-1"})
        await bd.task_logs.insert_one(_tarefa())
        tasks: list = []
        contadores = {"active_count": 0, "completed_unacknowledged": 0}

        await _merge_task_logs_into_tasks({"id": "u-1"}, tasks, contadores)

        # Sai como FALHADA e por reconhecer — é isso que faz o ecrã trocar o toast de
        # «a carregar» pelo de erro.
        assert [t["status"] for t in tasks] == ["failed"]
        assert contadores["active_count"] == 0
        assert contadores["completed_unacknowledged"] == 1
        assert tasks[0]["error_message"] == MOTIVO_RETRY_NAO_PROCESSADO

    @pytest.mark.asyncio
    async def test_o_ciclo_do_monitor_tambem_as_fecha(self, bd):
        from services import background_job_sweep as sweep

        await bd.task_logs.insert_one(_tarefa())
        with patch.object(sweep, "db", bd):
            await sweep.varrer_jobs_bloqueados()

        assert (await bd.task_logs.find_one({"task_id": "task_1"}))["status"] == "failed"

    @pytest.mark.asyncio
    async def test_uma_falha_na_limpeza_nao_derruba_o_varrimento(self, bd):
        from services import background_job_sweep as sweep

        with patch.object(sweep, "db", bd), \
             patch.object(eds, "fechar_envios_presos", AsyncMock(side_effect=RuntimeError("x"))):
            assert await sweep.varrer_jobs_bloqueados() == 0


class TestORetryTransportaEFechaATarefa:
    def _tq(self, job_id="job-1"):
        tq = MagicMock()
        tq.send_registration_email = AsyncMock(return_value=job_id)
        return tq

    @pytest.mark.asyncio
    async def test_o_envio_directo_falhado_enfileira_com_o_id_da_tarefa_e_do_cliente(self, bd):
        await bd.clients.insert_one({"id": "cli-1", "created_by": "s@x.pt"})
        await bd.users.insert_one({"id": "u-1", "email": "s@x.pt"})
        tq = self._tq()
        with patch("services.email.send_registration_confirmation", AsyncMock(return_value=False)), \
             patch("services.task_queue.task_queue", tq):
            await mod.deliver_registration_email("c@x.pt", "Cli", client_id="cli-1", user_id="u-1")

        argumentos = tq.send_registration_email.await_args.kwargs
        tarefa = await bd.task_logs.find_one({"user_id": "u-1"})
        assert argumentos["client_id"] == "cli-1"
        assert argumentos["task_id"] == tarefa["task_id"]
        assert tarefa["status"] == "processing"  # ainda à espera do retry

    @pytest.mark.asyncio
    async def test_o_retry_que_entrega_fecha_a_tarefa_ORIGINAL_e_nao_cria_outra(self, bd):
        await bd.clients.insert_one({"id": "cli-1", "portal_email_delivery": {"status": "retry_scheduled"}})
        await bd.task_logs.insert_one(_tarefa(minutos=1))
        with patch("services.email.send_registration_confirmation", AsyncMock(return_value=True)):
            ok = await mod.deliver_registration_email(
                "c@x.pt", "Cli", client_id="cli-1", task_id="task_1", retry=True,
            )

        assert ok is True
        todas = await bd.task_logs.find({}).to_list(10)
        assert [t["task_id"] for t in todas] == ["task_1"]
        assert todas[0]["status"] == "completed"
        assert (await bd.clients.find_one({"id": "cli-1"}))["portal_email_delivery"]["status"] == "sent"

    @pytest.mark.asyncio
    async def test_o_retry_que_falha_e_DEFINITIVO_nao_volta_a_enfileirar(self, bd):
        await bd.clients.insert_one({"id": "cli-1", "portal_email_delivery": {"status": "retry_scheduled"}})
        await bd.task_logs.insert_one(_tarefa(minutos=1))
        tq = self._tq()
        with patch("services.email.send_registration_confirmation", AsyncMock(return_value=False)), \
             patch("services.task_queue.task_queue", tq):
            ok = await mod.deliver_registration_email(
                "c@x.pt", "Cli", client_id="cli-1", task_id="task_1", retry=True,
            )

        assert ok is False
        tq.send_registration_email.assert_not_awaited()
        assert (await bd.task_logs.find_one({"task_id": "task_1"}))["status"] == "failed"
        assert (await bd.clients.find_one({"id": "cli-1"}))["portal_email_delivery"]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_retry_depois_de_o_cliente_ja_ter_recebido_fecha_a_tarefa(self, bd):
        await bd.clients.insert_one({"id": "cli-1", "portal_email_delivery": {"status": "sent"}})
        await bd.task_logs.insert_one(_tarefa(minutos=1))
        enviar = AsyncMock(return_value=True)
        with patch("services.email.send_registration_confirmation", enviar):
            ok = await mod.deliver_registration_email(
                "c@x.pt", "Cli", client_id="cli-1", task_id="task_1", retry=True,
            )

        assert ok is True
        enviar.assert_not_awaited()  # idempotente: não duplica o email
        assert (await bd.task_logs.find_one({"task_id": "task_1"}))["status"] == "completed"

    @pytest.mark.asyncio
    async def test_o_handler_da_fila_passa_a_tarefa_e_o_cliente_e_marca_retry(self):
        from worker import tasks as tarefas_do_worker

        entregar = AsyncMock(return_value=True)
        with patch("services.client_portal_email.deliver_registration_email", entregar):
            resultado = await tarefas_do_worker.send_registration_email_task(
                {}, client_email="c@x.pt", client_name="Cli",
                client_id="cli-1", task_id="task_1", company_id="co-1",
            )

        assert resultado == {"sent": True}
        kw = entregar.await_args.kwargs
        assert (kw["client_id"], kw["task_id"], kw["retry"]) == ("cli-1", "task_1", True)

    @pytest.mark.asyncio
    async def test_a_fila_leva_o_id_da_tarefa_no_job(self):
        from services.task_queue import TaskQueueService

        fila = TaskQueueService()
        fila.enqueue = AsyncMock(return_value="job-1")
        await fila.send_registration_email(
            "c@x.pt", "Cli", client_id="cli-1", task_id="task_1",
        )
        assert fila.enqueue.await_args.kwargs["task_id"] == "task_1"
        assert fila.enqueue.await_args.kwargs["client_id"] == "cli-1"
