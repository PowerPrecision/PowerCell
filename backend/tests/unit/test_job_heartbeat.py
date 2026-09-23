"""
Monitor de Sinais Vitais do motor de background (Lote 4, ponto 14).

PORQUE É QUE NÃO SE PODE LER O ESTADO LOCAL
  O motor não é um agendador: são laços `asyncio` à mão, repartidos por
  DOIS processos do `render.yaml`. O processo web corre
  `background_job_monitor` (todos os workers uvicorn) e, só no worker
  PRIMÁRIO em produção, o backup, o CDC e o auto-sync de IMAP. O processo
  worker corre `scheduler_loop` — e o seu `last_runs` é um DICIONÁRIO
  LOCAL DE UMA FUNÇÃO: morre em cada reinício e a API nunca o vê.

  Um endpoint que fizesse introspecção do estado local responderia sobre
  o processo que calhou atender o pedido: com `UVICORN_WORKERS=2`, um
  pedido servido pelo worker secundário diria "IMAP em baixo" porque esse
  worker nunca o arranca, por desenho. Um monitor que mente com ar de
  autoridade é pior do que não ter monitor.

  Daí o batimento persistido: uma colecção partilhada é a única coisa que
  os dois processos conseguem ver.

DESACTIVADO NÃO É EM BAIXO
  Em dev quase tudo está desligado de propósito (kill switches por RAM).
  Um painel a gritar vermelho em dev ensina toda a gente a ignorá-lo.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest


AGORA = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)


def _iso(momento: datetime) -> str:
    return momento.isoformat()


def _declarado(**extra):
    base = {
        "chave": "email_auto_sync",
        "nome": "Sincronização IMAP",
        "interval_seconds": 60,
        "processo": "web",
    }
    base.update(extra)
    return base


class TestEstadoDerivado:
    def test_batimento_recente_e_saudavel(self):
        from services.job_heartbeat import estado_do_job

        registo = {"finished_at": _iso(AGORA - timedelta(seconds=30)), "status": "ok"}
        assert estado_do_job(_declarado(), registo, agora=AGORA) == "saudavel"

    def test_um_ciclo_perdido_ainda_e_saudavel(self):
        """Limiar de 2x: um ciclo perdido é ruído (concorrência, um micro
        bloqueio); dois é sinal."""
        from services.job_heartbeat import estado_do_job

        registo = {"finished_at": _iso(AGORA - timedelta(seconds=90)), "status": "ok"}
        assert estado_do_job(_declarado(), registo, agora=AGORA) == "saudavel"

    def test_dois_ciclos_perdidos_e_atraso(self):
        from services.job_heartbeat import estado_do_job

        registo = {"finished_at": _iso(AGORA - timedelta(seconds=150)), "status": "ok"}
        assert estado_do_job(_declarado(), registo, agora=AGORA) == "atrasado"

    def test_ultimo_ciclo_com_erro_e_falha(self):
        """A falha vence o atraso: um job que bate a horas mas rebenta em
        cada ciclo está pior do que um atrasado."""
        from services.job_heartbeat import estado_do_job

        registo = {
            "finished_at": _iso(AGORA - timedelta(seconds=10)),
            "status": "erro",
            "error": "IMAP recusou a ligação",
        }
        assert estado_do_job(_declarado(), registo, agora=AGORA) == "falhou"

    def test_sem_batimento_nenhum_e_nunca_correu(self):
        """Um job que nunca bateu tem de APARECER na lista. Se só
        listássemos o que está na colecção, o job mais avariado de todos —
        o que nunca arrancou — era o único invisível."""
        from services.job_heartbeat import estado_do_job

        assert estado_do_job(_declarado(), None, agora=AGORA) == "nunca_correu"

    def test_job_desactivado_nao_e_falha(self):
        from services.job_heartbeat import estado_do_job

        declarado = _declarado(activo=False)
        assert estado_do_job(declarado, None, agora=AGORA) == "desactivado"

    def test_desactivado_vence_um_batimento_antigo(self):
        """Desligar um job deixa o último batimento a envelhecer para
        sempre. Mostrá-lo como "atrasado" seria mentir sobre a causa."""
        from services.job_heartbeat import estado_do_job

        registo = {"finished_at": _iso(AGORA - timedelta(days=30)), "status": "ok"}
        assert estado_do_job(_declarado(activo=False), registo, agora=AGORA) == "desactivado"

    def test_um_ciclo_a_correr_agora_nao_conta_como_atraso(self):
        """Um ciclo longo (o sync de IMAP pode demorar minutos) não pode
        aparecer como atrasado enquanto está a trabalhar."""
        from services.job_heartbeat import estado_do_job

        registo = {
            "started_at": _iso(AGORA - timedelta(seconds=200)),
            "finished_at": None,
            "status": "a_correr",
        }
        assert estado_do_job(_declarado(), registo, agora=AGORA) == "a_correr"


class TestProximaExecucao:
    def test_soma_o_intervalo_ao_ultimo_fim(self):
        from services.job_heartbeat import proxima_execucao

        registo = {"finished_at": _iso(AGORA - timedelta(seconds=30))}
        assert proxima_execucao(_declarado(), registo) == _iso(
            AGORA + timedelta(seconds=30)
        )

    def test_sem_batimento_nao_inventa_data(self):
        """Uma próxima execução inventada dá uma falsa sensação de
        normalidade a um job que nunca arrancou."""
        from services.job_heartbeat import proxima_execucao

        assert proxima_execucao(_declarado(), None) is None

    def test_job_desactivado_nao_tem_proxima(self):
        from services.job_heartbeat import proxima_execucao

        registo = {"finished_at": _iso(AGORA)}
        assert proxima_execucao(_declarado(activo=False), registo) is None


class TestRegistoDeclarado:
    def test_os_jobs_reais_estao_todos_declarados(self):
        """O registo é a lista do que DEVIA estar a correr. Cada entrada
        aqui tem de ter um emissor no código — e o contrário também."""
        from services.job_heartbeat import JOBS_DECLARADOS

        chaves = {j["chave"] for j in JOBS_DECLARADOS}
        assert chaves == {
            "background_job_monitor",
            "email_auto_sync",
            "backup_diario",
            "cdc_audit",
            "scheduled_tasks",
            "lead_matching",
            "webmail_worker_sync",
        }

    def test_cada_job_diz_em_que_processo_corre(self):
        """Com dois processos, "está vivo?" sem dizer ONDE é meia resposta."""
        from services.job_heartbeat import JOBS_DECLARADOS

        for job in JOBS_DECLARADOS:
            assert job["processo"] in {"web", "worker"}
            assert job["interval_seconds"] > 0
            assert job["nome"]

    def test_cada_job_declarado_tem_emissor_no_codigo(self):
        """Contraprova do registo: sem isto, acrescentar uma linha à lista
        dava um job verde que nunca ninguém instrumentou."""
        from pathlib import Path

        from services.job_heartbeat import JOBS_DECLARADOS

        raiz = Path(__file__).resolve().parents[2]
        fontes = "\n".join(
            (raiz / nome).read_text("utf-8")
            for nome in ("server.py", "worker.py", "services/scheduled_tasks.py",
                         "services/backup.py", "services/audit_cdc.py")
        )
        for job in JOBS_DECLARADOS:
            assert f'"{job["chave"]}"' in fontes, (
                f"o job {job['chave']} está declarado mas ninguém o emite"
            )


class TestGravacaoDoBatimento:
    @pytest.mark.asyncio
    async def test_regista_inicio_e_fim(self, fake_async_db):
        import services.job_heartbeat as hb

        with patch.object(hb, "db", fake_async_db):
            async with hb.heartbeat("email_auto_sync", interval_seconds=60):
                pass

        registo = fake_async_db.job_heartbeats.docs[0]
        assert registo["chave"] == "email_auto_sync"
        assert registo["status"] == "ok"
        assert registo["started_at"] and registo["finished_at"]
        assert registo["run_count"] == 1
        assert registo["failure_count"] == 0

    @pytest.mark.asyncio
    async def test_conta_as_execucoes_acumuladas(self, fake_async_db):
        import services.job_heartbeat as hb

        with patch.object(hb, "db", fake_async_db):
            for _ in range(3):
                async with hb.heartbeat("email_auto_sync", interval_seconds=60):
                    pass

        assert len(fake_async_db.job_heartbeats.docs) == 1, "um documento por job"
        assert fake_async_db.job_heartbeats.docs[0]["run_count"] == 3

    @pytest.mark.asyncio
    async def test_regista_a_falha_e_DEIXA_a_excepcao_passar(self, fake_async_db):
        """O batimento observa, não intercepta. Engolir a excepção aqui
        mudava o comportamento do job para o poder monitorizar — que é o
        oposto de um monitor."""
        import services.job_heartbeat as hb

        with patch.object(hb, "db", fake_async_db):
            with pytest.raises(RuntimeError):
                async with hb.heartbeat("email_auto_sync", interval_seconds=60):
                    raise RuntimeError("IMAP recusou a ligação")

        registo = fake_async_db.job_heartbeats.docs[0]
        assert registo["status"] == "erro"
        assert "IMAP recusou" in registo["error"]
        assert registo["failure_count"] == 1

    @pytest.mark.asyncio
    async def test_falhar_a_gravar_o_batimento_nao_mata_o_job(self, fake_async_db):
        """Um monitor que derruba o que monitoriza é pior do que nenhum.
        Mesma regra do `publish_event` e da revogação do Portal."""
        import services.job_heartbeat as hb

        class BaseEmBaixo:
            def __getattr__(self, _nome):
                raise RuntimeError("Mongo em baixo")

        executou = False
        with patch.object(hb, "db", BaseEmBaixo()):
            async with hb.heartbeat("email_auto_sync", interval_seconds=60):
                executou = True

        assert executou is True

    @pytest.mark.asyncio
    async def test_guarda_quem_bateu(self, fake_async_db):
        """Com dois processos e dois workers uvicorn, saber QUEM bateu é
        metade do diagnóstico."""
        import services.job_heartbeat as hb

        with patch.object(hb, "db", fake_async_db):
            async with hb.heartbeat("email_auto_sync", interval_seconds=60):
                pass

        registo = fake_async_db.job_heartbeats.docs[0]
        assert registo["pid"] > 0
        assert registo["host"]


# ════════════════════════════════════════════════════════════════════
# CAMADA 2 — o endpoint
# ════════════════════════════════════════════════════════════════════
class TestEndpointDeTelemetria:
    @pytest.mark.asyncio
    async def test_lista_TODOS_os_jobs_declarados_mesmo_sem_batimento(self, fake_async_db):
        """A lista sai do registo declarado, não da colecção: se saísse da
        colecção, o job mais avariado de todos — o que nunca arrancou —
        era o único que não aparecia."""
        import services.job_heartbeat as hb
        from services.automation_api_engine import run_get_automations_status

        with patch.object(hb, "db", fake_async_db):
            resposta = await run_get_automations_status()

        assert len(resposta["jobs"]) == len(hb.JOBS_DECLARADOS)

    @pytest.mark.asyncio
    async def test_junta_o_batimento_ao_declarado(self, fake_async_db, monkeypatch):
        import services.job_heartbeat as hb
        from services.automation_api_engine import run_get_automations_status

        monkeypatch.setenv("ENVIRONMENT", "production")
        fake_async_db.job_heartbeats.docs.append({
            "chave": "email_auto_sync",
            "started_at": _iso(datetime.now(timezone.utc)),
            "finished_at": _iso(datetime.now(timezone.utc)),
            "status": "ok",
            "duration_ms": 1234,
            "run_count": 7,
            "failure_count": 1,
            "host": "worker-a",
            "pid": 42,
        })

        with patch.object(hb, "db", fake_async_db):
            resposta = await run_get_automations_status()

        linha = next(j for j in resposta["jobs"] if j["chave"] == "email_auto_sync")
        assert linha["estado"] == "saudavel"
        assert linha["duracao_ms"] == 1234
        assert linha["run_count"] == 7
        assert linha["host"] == "worker-a"
        assert linha["proxima_execucao"]

    @pytest.mark.asyncio
    async def test_em_dev_os_jobs_de_producao_aparecem_desactivados(
        self, fake_async_db, monkeypatch,
    ):
        """A distinção mais importante do painel. Em dev quase tudo está
        desligado de propósito; um monitor a gritar vermelho em dev ensina
        toda a gente a ignorá-lo."""
        import services.job_heartbeat as hb
        from services.automation_api_engine import run_get_automations_status

        monkeypatch.setenv("ENVIRONMENT", "dev")
        monkeypatch.delenv("EMAIL_SYNC_ENABLED", raising=False)

        with patch.object(hb, "db", fake_async_db):
            resposta = await run_get_automations_status()

        linha = next(j for j in resposta["jobs"] if j["chave"] == "email_auto_sync")
        assert linha["estado"] == "desactivado"
        # A asserção é sobre ESTE job, não sobre a contagem global: o
        # `background_job_monitor` está activo em dev e nunca correu, o
        # que é um problema LEGÍTIMO e conta para o resumo. Exigir zero
        # aqui media a coisa errada.
        assert resposta["resumo"]["desactivados"] >= 1
        assert linha["estado"] not in {"falhou", "atrasado", "nunca_correu"}, (
            "um job desligado de propósito não pode aparecer como avariado"
        )

    @pytest.mark.asyncio
    async def test_o_monitor_leve_corre_sempre_mesmo_em_dev(
        self, fake_async_db, monkeypatch,
    ):
        """Contraprova: se tudo aparecesse desactivado em dev, o teste
        acima passava sem provar a distinção."""
        import services.job_heartbeat as hb
        from services.automation_api_engine import run_get_automations_status

        monkeypatch.setenv("ENVIRONMENT", "dev")

        with patch.object(hb, "db", fake_async_db):
            resposta = await run_get_automations_status()

        linha = next(j for j in resposta["jobs"] if j["chave"] == "background_job_monitor")
        assert linha["estado"] == "nunca_correu"
        assert linha["activo"] is True

    @pytest.mark.asyncio
    async def test_a_base_em_baixo_nao_derruba_o_painel(self, fake_async_db):
        """Um monitor que rebenta quando há problemas é inútil
        precisamente quando faz falta."""
        import services.job_heartbeat as hb
        from services.automation_api_engine import run_get_automations_status

        class BaseEmBaixo:
            def __getitem__(self, _nome):
                raise RuntimeError("Mongo em baixo")

        with patch.object(hb, "db", BaseEmBaixo()):
            resposta = await run_get_automations_status()

        assert len(resposta["jobs"]) == len(hb.JOBS_DECLARADOS)
        assert all(j["estado"] in {"nunca_correu", "desactivado"} for j in resposta["jobs"])

    @pytest.mark.asyncio
    async def test_o_endpoint_e_de_LEITURA(self):
        """Read-only por desenho: o motor corre noutro processo e um
        disparo a partir da web nunca lá chegaria."""
        from pathlib import Path

        fonte = (
            Path(__file__).resolve().parents[2] / "routes" / "automation.py"
        ).read_text("utf-8")
        bloco = fonte[fonte.index("engine_router = APIRouter"):]
        bloco = bloco[: bloco.index("@router.") if "@router." in bloco else len(bloco)]
        for verbo in ("@engine_router.post", "@engine_router.put",
                      "@engine_router.delete", "@engine_router.patch"):
            assert verbo not in bloco, f"o painel do motor expõe {verbo}"
