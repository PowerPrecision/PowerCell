"""A fila do Processador e a execução forçada (Lote 2, ponto 1).

O DEFEITO, QUE NÃO ERA O QUE O SINTOMA DIZIA
============================================
O painel mostrava as tarefas do «Processador» como **Nunca correu** e a
hipótese natural era "o worker está em baixo". Não estava.

`worker.py` chamava QUATRO métodos que não existem em `TaskQueueService`
(que é ARQ/Redis e não tem `__getattr__`):

    get_next_task()   complete_task()   fail_task()   add_task()

Consequências exactas:

  1. `worker_loop` rebentava com `AttributeError` a cada **5 segundos**,
     desde sempre. O despachante `process_task` — scrape de imóveis,
     matching, email — nunca correu uma única vez.

  2. No `scheduler_loop`, o `add_task` do matching estava DENTRO do
     `async with heartbeat("lead_matching")`. A excepção subia e saltava
     o resto do ciclo; o bloco de sincronização de webmail vinha DEPOIS,
     logo **nunca era alcançado**. É essa a origem do «Nunca correu» —
     uma linha inalcançável por uma excepção lançada três linhas acima,
     não um processo morto.

  3. `last_runs[...]` era escrito DEPOIS do trabalho: um job que falhasse
     não registava a passagem e voltava a tentar dentro de 60s, para
     sempre, em vez de esperar o seu intervalo.

A IRONIA
========
A docstring do `client_portal_email.py` afirma, a explicar outro bugfix,
que «o worker de produção arranca com `python worker.py` (loop próprio
que processa a fila Mongo por `task_type`)». Essa fila Mongo nunca foi
escrita. A crença estava registada em dois sítios e era falsa nos dois.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services import task_queue_mongo as tqm  # noqa: E402
from tests.unit.helpers_fonte import codigo_sem_comentarios  # noqa: E402


@pytest.fixture
def fila(fake_async_db, monkeypatch):
    monkeypatch.setattr(tqm, "db", fake_async_db)
    return fake_async_db


class TestOsMetodosQueOWorkerChamaEXISTEM:
    """O defeito, afirmado directamente. Sem isto, nada o apanhava — nem o
    eslint, nem o build, nem os 4000 testes: só o runtime, a cada 5s, num
    log que ninguém lia."""

    @pytest.mark.parametrize("nome", ["add_task", "get_next_task", "complete_task", "fail_task"])
    def test_o_TaskQueueService_tem_o_metodo(self, nome):
        from services.task_queue import TaskQueueService
        assert hasattr(TaskQueueService, nome), f"worker.py chama {nome}()"

    def test_o_worker_chama_exactamente_estes(self):
        """Contraprova de cobertura: se o worker passar a chamar um quinto
        método, este teste obriga a acrescentá-lo acima."""
        from services.task_queue import TaskQueueService
        fonte = codigo_sem_comentarios((BACKEND / "worker.py").read_text(encoding="utf-8"))
        for nome in ("add_task", "get_next_task", "complete_task", "fail_task"):
            if f"task_queue.{nome}" in fonte:
                assert hasattr(TaskQueueService, nome)


class TestOCicloDeVidaDeUmaTarefa:
    @pytest.mark.asyncio
    async def test_enfileirar_e_reclamar(self, fila):
        task_id = await tqm.add_task("match_leads", {"x": 1})
        assert task_id

        tarefa = await tqm.get_next_task()
        assert tarefa["id"] == task_id
        assert tarefa["type"] == "match_leads"
        assert tarefa["payload"] == {"x": 1}
        assert tarefa["status"] == tqm.ESTADO_A_PROCESSAR

    @pytest.mark.asyncio
    async def test_uma_tarefa_reclamada_NAO_e_reclamada_outra_vez(self, fila):
        """Reclamar muda o estado, logo a segunda passagem não a encontra."""
        await tqm.add_task("match_leads")
        assert await tqm.get_next_task() is not None
        assert await tqm.get_next_task() is None

    @pytest.mark.asyncio
    async def test_a_reclamacao_e_UMA_operacao_e_nao_duas(self, monkeypatch):
        """UM NÍVEL ABAIXO, sobre os parâmetros que saem.

        O teste acima **não prova atomicidade**: o duplo é single-thread e
        reimplementa o escolhe-e-actualiza num passo, pelo que passaria
        também com um `find_one` seguido de `update_one` — e aí dois
        consumidores apanhavam a mesma tarefa. É a lição de Set 2026: um
        duplo que reimplementa a lógica valida o duplo. O que se afirma é
        que a operação enviada é `find_one_and_update`, com o filtro do
        estado DENTRO dela.
        """
        chamadas = []

        class ColeccaoEspia:
            async def update_many(self, *a, **k):
                class R:
                    modified_count = 0
                return R()

            async def find_one_and_update(self, filtro, update, **kwargs):
                chamadas.append(("find_one_and_update", filtro, update, kwargs))
                return None

            async def find_one(self, *a, **k):
                chamadas.append(("find_one",))
                return None

        class DbEspia:
            def __getitem__(self, _):
                return ColeccaoEspia()

        monkeypatch.setattr(tqm, "db", DbEspia())
        await tqm.get_next_task()

        operacoes = [c[0] for c in chamadas]
        assert "find_one_and_update" in operacoes
        assert "find_one" not in operacoes

        _, filtro, update, kwargs = next(c for c in chamadas if c[0] == "find_one_and_update")
        # O estado entra no FILTRO (senão a reclamação não é exclusiva)...
        assert filtro["status"] == tqm.ESTADO_PENDENTE
        # ...e sai no UPDATE, na mesma operação.
        assert update["$set"]["status"] == tqm.ESTADO_A_PROCESSAR
        # FIFO pelo `sort`, e sem `_id` (que não é serializável em JSON).
        assert kwargs["sort"] == [("created_at", 1)]
        assert kwargs["projection"] == {"_id": 0}

    @pytest.mark.asyncio
    async def test_concluir(self, fila):
        task_id = await tqm.add_task("send_email")
        await tqm.get_next_task()
        assert await tqm.complete_task(task_id, result={"ok": True}) is True

        doc = await fila.task_queue.find_one({"id": task_id})
        assert doc["status"] == tqm.ESTADO_CONCLUIDA
        assert doc["result"] == {"ok": True}

    @pytest.mark.asyncio
    async def test_o_campo_do_TTL_e_um_datetime_NATIVO(self, fila):
        """O TTL do Mongo não funciona sobre uma string ISO — foi o que
        inutilizou o `idx_ttl` descontinuado. Uma fila sem purga cresce
        para sempre (D-13)."""
        task_id = await tqm.add_task("send_email")
        await tqm.complete_task(task_id)
        doc = await fila.task_queue.find_one({"id": task_id})
        assert isinstance(doc["finished_at_dt"], datetime)

    @pytest.mark.asyncio
    async def test_a_fila_e_FIFO(self, fila):
        primeiro = await tqm.add_task("a")
        await tqm.add_task("b")
        tarefa = await tqm.get_next_task()
        assert tarefa["id"] == primeiro

    @pytest.mark.asyncio
    async def test_uma_fila_em_baixo_nao_derruba_quem_a_usa(self, monkeypatch):
        """Quem enfileira está, por norma, a tratar de outra coisa."""
        class DbQueRebenta:
            def __getitem__(self, _):
                raise RuntimeError("Mongo em baixo")

        monkeypatch.setattr(tqm, "db", DbQueRebenta())
        assert await tqm.add_task("match_leads") is None
        assert await tqm.get_next_task() is None


class TestOBackoffNaoEUmLuxO:
    """O `worker_loop` só dorme quando NÃO há tarefa. Uma tarefa que falhe
    sempre e volte logo a `pendente` punha o laço a girar a 100% de CPU — a
    correcção teria trocado um worker parado por um worker a arder."""

    @pytest.mark.asyncio
    async def test_falhar_devolve_a_tarefa_a_fila_MAS_ADIADA(self, fila):
        task_id = await tqm.add_task("match_leads")
        await tqm.get_next_task()
        await tqm.fail_task(task_id, error="rebentou")

        doc = await fila.task_queue.find_one({"id": task_id})
        assert doc["status"] == tqm.ESTADO_PENDENTE
        assert doc["tentativas"] == 1
        # E não está disponível agora: é isto que impede o giro.
        assert await tqm.get_next_task() is None

    @pytest.mark.asyncio
    async def test_passada_a_espera_a_tarefa_volta(self, fila):
        task_id = await tqm.add_task("match_leads")
        await tqm.get_next_task()
        await tqm.fail_task(task_id, error="rebentou")

        # Viajar no tempo para trás no campo de disponibilidade.
        passado = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        await fila.task_queue.update_one({"id": task_id}, {"$set": {"disponivel_em": passado}})
        assert (await tqm.get_next_task())["id"] == task_id

    @pytest.mark.asyncio
    async def test_a_espera_cresce_com_as_tentativas(self):
        esperas = [tqm.espera_da_tentativa(n) for n in (1, 2, 3)]
        assert esperas == sorted(esperas)
        assert esperas[0] < esperas[-1]

    @pytest.mark.asyncio
    async def test_uma_tarefa_envenenada_acaba_FALHADA_e_nao_volta(self, fila):
        """Repetir para sempre é o outro extremo: a tarefa fica visível em
        `falhada` em vez de ocupar o worker sem fim."""
        task_id = await tqm.add_task("match_leads", max_tentativas=2)
        for _ in range(2):
            doc = await fila.task_queue.find_one({"id": task_id})
            await fila.task_queue.update_one(
                {"id": task_id},
                {"$set": {"disponivel_em": "2000-01-01T00:00:00+00:00"}},
            )
            await tqm.get_next_task()
            await tqm.fail_task(task_id, error="sempre a mesma")

        doc = await fila.task_queue.find_one({"id": task_id})
        assert doc["status"] == tqm.ESTADO_FALHADA
        assert doc["error"] == "sempre a mesma"


class TestUmaTarefaSemConsumidorVoltaAFila:
    """Um deploy a meio de uma tarefa deixa-a `a_processar` para sempre; sem
    a recuperação ficava perdida sem erro nenhum."""

    @pytest.mark.asyncio
    async def test_uma_tarefa_reclamada_ha_muito_tempo_e_recuperada(self, fila):
        task_id = await tqm.add_task("match_leads")
        await tqm.get_next_task()
        antigo = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        await fila.task_queue.update_one({"id": task_id}, {"$set": {"started_at": antigo}})

        assert (await tqm.get_next_task())["id"] == task_id

    @pytest.mark.asyncio
    async def test_uma_tarefa_reclamada_AGORA_nao_e_roubada(self, fila):
        """Contraprova: sem ela, "recuperar tudo" passava o teste acima e
        duas passagens corriam a mesma tarefa em paralelo."""
        await tqm.add_task("match_leads")
        await tqm.get_next_task()
        assert await tqm.get_next_task() is None


class TestOsDoisConsumidoresNaoSePisam:
    """Há DOIS laços a consumir a mesma fila no processo worker: o
    `worker_loop` (scrape/matching/email) e o `scheduler_loop` (pedidos de
    execução forçada). Sem filtro por tipo, cada um reclamava tarefas que
    não sabe tratar e gastava-lhes as tentativas — a tarefa morria
    `falhada` sem nunca ter chegado a quem a sabia correr."""

    @pytest.mark.asyncio
    async def test_o_scheduler_so_reclama_pedidos_de_execucao(self, fila):
        await tqm.add_task("match_leads")
        await tqm.pedir_execucao_de_job("scheduled_tasks")

        tarefa = await tqm.get_next_task(tipos=[tqm.TIPO_FORCAR_JOB])
        assert tarefa["type"] == tqm.TIPO_FORCAR_JOB

    @pytest.mark.asyncio
    async def test_o_worker_loop_nao_reclama_os_pedidos(self, fila):
        await tqm.pedir_execucao_de_job("scheduled_tasks")
        assert await tqm.get_next_task(excluir_tipos=[tqm.TIPO_FORCAR_JOB]) is None

    @pytest.mark.asyncio
    async def test_e_reclama_o_resto(self, fila):
        await tqm.add_task("match_leads")
        tarefa = await tqm.get_next_task(excluir_tipos=[tqm.TIPO_FORCAR_JOB])
        assert tarefa["type"] == "match_leads"

    def test_os_dois_lacos_usam_filtros_COMPLEMENTARES(self):
        """A propriedade que importa: juntos cobrem tudo e não se sobrepõem.
        Afirmado sobre a fonte, porque é a combinação que falha, nunca cada
        lado por si (a forma do placebo do Lote 4).

        A CHAMADA INTEIRA, com o nome da função: `tipos=[…]` é SUBCADEIA de
        `excluir_tipos=[…]`, logo um guarda que procure só o primeiro é
        satisfeito pela linha do OUTRO laço. Foi medido — a mutação que tirou
        o `tipos=` do `scheduler_loop` (que o punha a roubar trabalho ao
        `worker_loop`) sobreviveu à primeira versão deste teste.
        """
        fonte = codigo_sem_comentarios(
            (BACKEND / "worker.py").read_text(encoding="utf-8")
        ).replace(" ", "").replace("\n", "")
        assert "get_next_task(excluir_tipos=[TIPO_FORCAR_JOB])" in fonte
        assert "get_next_task(tipos=[TIPO_FORCAR_JOB])" in fonte
        # E nenhum dos dois reclama SEM filtro — é isso que os faz
        # complementares em vez de concorrentes.
        assert "get_next_task()" not in fonte


class TestOPedidoDeExecucaoForcada:
    @pytest.mark.asyncio
    async def test_pedir_cria_o_pedido(self, fila):
        pedido_id = await tqm.pedir_execucao_de_job("lead_matching")
        assert pedido_id
        doc = await fila.task_queue.find_one({"id": pedido_id})
        assert doc["type"] == tqm.TIPO_FORCAR_JOB
        assert doc["payload"] == {"chave": "lead_matching"}

    @pytest.mark.asyncio
    async def test_carregar_duas_vezes_no_botao_nao_enfileira_dois_ciclos(self, fila):
        primeiro = await tqm.pedir_execucao_de_job("lead_matching")
        segundo = await tqm.pedir_execucao_de_job("lead_matching")
        assert primeiro == segundo

    @pytest.mark.asyncio
    async def test_um_pedido_manual_NAO_se_repete_sozinho(self, fila):
        """Uma tentativa só: um pedido manual que falhe tem de o DIZER, não
        voltar às escondidas meia hora depois."""
        pedido_id = await tqm.pedir_execucao_de_job("lead_matching")
        doc = await fila.task_queue.find_one({"id": pedido_id})
        assert doc["max_tentativas"] == 1

    @pytest.mark.asyncio
    async def test_jobs_DIFERENTES_tem_pedidos_diferentes(self, fila):
        a = await tqm.pedir_execucao_de_job("lead_matching")
        b = await tqm.pedir_execucao_de_job("scheduled_tasks")
        assert a != b

    @pytest.mark.asyncio
    async def test_o_pedido_PENDENTE_e_visivel_ao_painel(self, fila):
        """É isto que transforma «Nunca correu» num diagnóstico: um pedido
        que ninguém reclama PROVA que o Processador não está a ouvir."""
        await tqm.pedir_execucao_de_job("lead_matching")
        por_job = await tqm.pedidos_de_execucao_por_job()
        assert por_job["lead_matching"]["status"] == tqm.ESTADO_PENDENTE

    @pytest.mark.asyncio
    async def test_depois_de_atendido_o_painel_ve_concluido(self, fila):
        pedido_id = await tqm.pedir_execucao_de_job("lead_matching")
        await tqm.get_next_task(tipos=[tqm.TIPO_FORCAR_JOB])
        await tqm.complete_task(pedido_id)
        por_job = await tqm.pedidos_de_execucao_por_job()
        assert por_job["lead_matching"]["status"] == tqm.ESTADO_CONCLUIDA
