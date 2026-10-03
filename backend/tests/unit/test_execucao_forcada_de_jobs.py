"""Botões «Forçar Execução» no painel «Estado do Motor» (Lote 2, ponto 1).

A OBJECÇÃO ORIGINAL ESTAVA CERTA
================================
O `automation_api_engine` era read-only e dizia porquê: «um disparo manual
a partir da web não chegaria ao processo worker (são processos distintos do
`render.yaml`), e um botão que não faz nada é pior do que não existir».

A fila persistente é a RESPOSTA a essa objecção, não a sua negação:

  · job do processo **web** → corre no processo que o alberga;
  · job do processo **worker** → fica um PEDIDO que o `scheduler_loop`
    reclama no ciclo seguinte.

E a resposta diz qual dos dois aconteceu, porque dar "pedido entregue" por
"a correr" seria exactamente o botão a mentir que a objecção queria evitar.

O QUE ESTES TESTES PROTEGEM
===========================
1. **Um registo único do que «correr» significa.** Se o endpoint tivesse a
   sua própria versão, o botão provava uma coisa e o horário fazia outra —
   e o diagnóstico passava a depender de qual dos dois correu. É a forma do
   defeito que este projecto já viu nos campos de atribuição, nos papéis e
   nas chaves de cache.
2. **Inventário nos dois sentidos** entre `JOBS_DECLARADOS` e
   `EXECUTORES`: um job declarado sem executor dá um botão que rebenta; um
   executor sem job declarado é código morto.
3. **Um job desactivado não se força.** Em dev quase tudo está desligado
   por kill switch, e o que se forçasse aí tocava em servidores de email
   REAIS.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services import automation_api_engine as motor  # noqa: E402
from services import job_executors as je  # noqa: E402
from services.job_heartbeat import JOBS_DECLARADOS, JOBS_POR_CHAVE  # noqa: E402
from tests.unit.helpers_fonte import codigo_sem_comentarios  # noqa: E402

ADMIN = {"id": "u1", "email": "admin@sistema.pt", "role": "admin"}


def _sem_aspas(texto: str) -> str:
    return texto.replace('"', "").replace("'", "")


def _modulo_do_worker():
    """Carrega `backend/worker.py` por CAMINHO.

    `import worker` resolve para o PACOTE `backend/worker/` (que tem
    `__init__.py`), não para o script `worker.py` — o pacote sombreia o
    módulo. Em produção não há conflito porque o Render corre
    `python worker.py`, que executa o ficheiro directamente; mas num teste
    o `import` traz a coisa errada, calado.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_worker_script", BACKEND / "worker.py"
    )
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


class TestOInventarioNosDoisSentidos:
    def test_todo_o_job_declarado_tem_executor(self):
        """Um botão sem executor rebenta no clique."""
        declarados = {j["chave"] for j in JOBS_DECLARADOS}
        assert declarados <= set(je.EXECUTORES), declarados - set(je.EXECUTORES)

    def test_todo_o_executor_tem_job_declarado(self):
        """O sentido contrário: um executor órfão é código morto, e um job
        que não está no registo declarado é invisível no painel."""
        declarados = {j["chave"] for j in JOBS_DECLARADOS}
        assert set(je.EXECUTORES) <= declarados, set(je.EXECUTORES) - declarados

    def test_ha_mesmo_jobs_a_verificar(self):
        """Contraprova de cobertura: com as duas listas vazias, os dois
        testes acima passavam."""
        assert len(JOBS_DECLARADOS) >= 5
        assert len(je.EXECUTORES) >= 5


class TestOQueNaoSeForca:
    def test_o_CDC_nao_se_forca_e_diz_porque(self):
        """É um listener contínuo de change streams — não tem ciclo para
        repetir. Um botão desactivado sem explicação manda o utilizador
        clicar outra vez."""
        assert je.pode_ser_forcado("cdc_audit") is False
        assert je.motivo_para_nao_forcar("cdc_audit")

    def test_os_restantes_forcam_se(self):
        """Contraprova: sem ela, "nada se força" passava o teste acima."""
        for chave in ("scheduled_tasks", "lead_matching", "background_job_monitor"):
            assert je.pode_ser_forcado(chave) is True

    @pytest.mark.asyncio
    async def test_um_job_DESACTIVADO_recusa(self, monkeypatch):
        """Em dev quase tudo está desligado de propósito, e o que se forçasse
        aí tocava em servidores de email reais."""
        monkeypatch.setattr(je, "EXECUTORES", dict(je.EXECUTORES))
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("EMAIL_SYNC_ENABLED", raising=False)
        with pytest.raises(PermissionError):
            await je.executar_job("email_auto_sync")

    @pytest.mark.asyncio
    async def test_um_job_desconhecido_recusa(self):
        with pytest.raises(KeyError):
            await je.executar_job("job_que_nao_existe")


class TestOEndpointDistingueOsDoisCaminhos:
    @pytest.mark.asyncio
    async def test_um_job_do_WORKER_deixa_pedido(self, monkeypatch):
        pedidos = []

        async def falso_pedir(chave):
            pedidos.append(chave)
            return "pedido-1"

        monkeypatch.setenv("ENVIRONMENT", "production")
        import services.task_queue_mongo as tqm
        monkeypatch.setattr(tqm, "pedir_execucao_de_job", falso_pedir)

        resposta = await motor.run_forcar_execucao_de_job("lead_matching", user=ADMIN)
        assert resposta["modo"] == "pedido_ao_worker"
        assert resposta["pedido_id"] == "pedido-1"
        assert pedidos == ["lead_matching"]

    @pytest.mark.asyncio
    async def test_a_mensagem_do_worker_DIZ_que_e_um_pedido(self, monkeypatch):
        """"Pedido entregue" e "a correr" são estados diferentes; dar o
        segundo pelo primeiro é o botão a mentir."""
        monkeypatch.setenv("ENVIRONMENT", "production")
        import services.task_queue_mongo as tqm

        async def falso_pedir(chave):
            return "p1"

        monkeypatch.setattr(tqm, "pedir_execucao_de_job", falso_pedir)
        resposta = await motor.run_forcar_execucao_de_job("scheduled_tasks", user=ADMIN)
        assert "Pedido entregue" in resposta["mensagem"]
        # E explica o valor de diagnóstico de um pedido que fica pendente.
        assert "não está a consumir" in resposta["mensagem"]

    @pytest.mark.asyncio
    async def test_um_job_do_WEB_corre_agora(self, monkeypatch):
        corridos = []

        async def falso_executar(chave):
            corridos.append(chave)

        monkeypatch.setattr(motor, "JOBS_POR_CHAVE", JOBS_POR_CHAVE)
        monkeypatch.setattr(je, "executar_job", falso_executar)

        resposta = await motor.run_forcar_execucao_de_job("background_job_monitor", user=ADMIN)
        assert resposta["modo"] == "executado_agora"
        assert corridos == ["background_job_monitor"]

    @pytest.mark.asyncio
    async def test_um_job_desconhecido_da_404(self):
        with pytest.raises(HTTPException) as erro:
            await motor.run_forcar_execucao_de_job("inexistente", user=ADMIN)
        assert erro.value.status_code == 404

    @pytest.mark.asyncio
    async def test_um_job_desactivado_da_409_e_nao_403(self, monkeypatch):
        """Não é falta de permissão — é o job estar desligado NESTE
        ambiente. Um 403 mandava o administrador procurar permissões."""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("EMAIL_SYNC_ENABLED", raising=False)
        with pytest.raises(HTTPException) as erro:
            await motor.run_forcar_execucao_de_job("email_auto_sync", user=ADMIN)
        assert erro.value.status_code == 409

    @pytest.mark.asyncio
    async def test_o_CDC_da_409_com_o_motivo(self, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        with pytest.raises(HTTPException) as erro:
            await motor.run_forcar_execucao_de_job("cdc_audit", user=ADMIN)
        assert erro.value.status_code == 409
        assert "listener" in str(erro.value.detail)

    @pytest.mark.asyncio
    async def test_uma_falha_do_job_chega_a_quem_carregou(self, monkeypatch):
        """O batimento registou `erro`; mas quem carregou no botão tem de
        saber, senão fica à espera de nada."""
        async def rebenta(chave):
            raise RuntimeError("o IMAP recusou")

        monkeypatch.setattr(je, "executar_job", rebenta)
        with pytest.raises(HTTPException) as erro:
            await motor.run_forcar_execucao_de_job("background_job_monitor", user=ADMIN)
        assert erro.value.status_code == 500
        assert "IMAP" in str(erro.value.detail)


class TestOLacoEOBotaoUsamOMESMOTrabalho:
    """Guardas de fonte com contraprova — o que importa é que não há duas
    definições de "correr este job"."""

    def test_o_laco_do_monitor_web_chama_o_executor(self):
        # Sem aspas: o `ast.unparse` do helper normaliza-as, logo comparar
        # com aspas duplas falha por um detalhe que não é o do teste.
        fonte = _sem_aspas(
            codigo_sem_comentarios((BACKEND / "server.py").read_text(encoding="utf-8"))
        )
        assert "executar_job(background_job_monitor)" in fonte
        # E já não tem o varrimento escrito em linha.
        assert "_tratar_jobs_bloqueados(stuck_jobs" not in fonte

    def test_o_laco_do_processador_chama_o_executor(self):
        fonte = codigo_sem_comentarios((BACKEND / "worker.py").read_text(encoding="utf-8"))
        assert "executar_job" in fonte
        # E já não chama o `add_task` que não existia.
        assert 'task_queue.add_task("match_leads"' not in fonte

    def test_as_cadencias_do_laco_DERIVAM_do_registo_declarado(self):
        """Os números estavam escritos à mão no worker (3600/1800/600) E no
        registo declarado — duas cópias da mesma cadência, que divergem na
        primeira vez que alguém afina uma delas, e aí o painel anuncia um
        horário que o laço não cumpre."""
        fonte = codigo_sem_comentarios((BACKEND / "worker.py").read_text(encoding="utf-8"))
        assert "JOBS_DECLARADOS" in fonte
        for numero in ("3600", "1800", "600"):
            assert f'interval_seconds={numero}' not in fonte

    def test_CONTRAPROVA_o_registo_declarado_tem_mesmo_as_cadencias(self):
        jobs = _modulo_do_worker()._jobs_do_processador()
        assert jobs == {
            "scheduled_tasks": 3600,
            "lead_matching": 1800,
            "webmail_worker_sync": 600,
        }

    def test_o_executor_do_backup_chama_o_MESMO_que_o_laco(self):
        """`scheduled_backup_job` e não `backup_service.create_backup`: o
        segundo saltava o que o job faz à volta dele."""
        fonte = codigo_sem_comentarios(
            (BACKEND / "services" / "job_executors.py").read_text(encoding="utf-8")
        )
        assert "scheduled_backup_job" in fonte
        laco = codigo_sem_comentarios(
            (BACKEND / "services" / "backup.py").read_text(encoding="utf-8")
        )
        assert "scheduled_backup_job()" in laco


class TestOBatimentoEmbrulhaOTrabalho:
    """A regra do Lote 4: o batimento embrulha o TRABALHO, não corre ao
    lado dele — senão registava `ok` para um ciclo que rebentou a seguir."""

    def test_o_executor_embrulha(self):
        fonte = codigo_sem_comentarios(
            (BACKEND / "services" / "job_executors.py").read_text(encoding="utf-8")
        )
        assert "async with heartbeat(" in fonte
        assert "await executor()" in fonte

    def test_o_sync_de_webmail_JA_NAO_bate_com_um_pass(self):
        """O `_bater_webmail_worker_sync` abria e fechava o batimento com um
        `pass` e o trabalho corria A SEGUIR, fora do envelope: o painel
        dizia `ok` a um ciclo em que todas as caixas podiam ter falhado, com
        duração de microssegundos."""
        fonte = (BACKEND / "worker.py").read_text(encoding="utf-8")
        assert "_bater_webmail_worker_sync" not in fonte

        servico = codigo_sem_comentarios(
            (BACKEND / "services" / "webmail_worker_sync.py").read_text(encoding="utf-8")
        )
        # O trabalho está DENTRO do envelope.
        assert servico.index("async with heartbeat(") < servico.index(
            "await run_webmail_worker_sync()"
        )
