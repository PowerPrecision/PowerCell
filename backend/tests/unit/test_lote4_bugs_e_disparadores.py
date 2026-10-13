"""
Lote 4, ponto 7 (Out 2026) — bugs de UI/UX e disparadores.

  * RGPD: o toast «já existe um pedido» aparecia na PRIMEIRA vez que se pedia o consentimento.
    O servidor devolvia `status: pending` tanto para um pedido NOVO como para um REUTILIZADO, e o ecrã
    lia o estado. Hoje a resposta traz `existing` (e `email_sent`).
  * Convite do Portal: só o `POST /processes/create-client` o disparava; os outros dois escritores de
    processo (`create-process` da ficha do cliente e `assign` da Sala de Triagem) deixavam o cliente
    — criado com `skip_welcome_email` — sem convite.
  * Sincronização de email: o job nunca fica «a correr» depois de a tarefa acabar (o toast
    persistente do ecrã vive enquanto o job estiver activo).
  * `broadcast_push_notification` (código morto que escolhia por cargo sem rede) foi apagada.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios


# ════════════════════════════════════════════════════════════════════
#  RGPD: pedido novo vs pedido reutilizado
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestRGPDDizSeOPedidoJaExistia:
    @pytest.fixture(autouse=True)
    def _bd(self, fake_async_db):
        fake_async_db.processes.docs.append({"id": "p1", "client_name": "Ana"})
        self.bd = fake_async_db

    async def _pedir(self, resultado_do_pedido, email_sai=True):
        from models.rgpd import RGPDCreate
        from services import rgpd_request as mod

        dados = RGPDCreate(process_id="p1", client_name="Ana", client_email="ana@x.pt")
        pedido = SimpleNamespace(headers={}, base_url="http://x/")
        with patch.object(mod, "db", self.bd), \
             patch.object(mod, "create_rgpd_request", AsyncMock(return_value=resultado_do_pedido)), \
             patch.object(mod, "send_rgpd_email", AsyncMock(return_value=email_sai)), \
             patch.object(mod, "resolve_second_titular_for_rgpd", AsyncMock(return_value=None)), \
             patch.object(mod, "_add_process_activity", AsyncMock()), \
             patch.object(mod, "_frontend_base_url_from_request", lambda *a, **k: "http://x"):
            return await mod.run_request_rgpd(dados, pedido, {"id": "u", "email": "u@x.pt", "name": "U"})

    async def test_a_exploracao_o_primeiro_pedido_NAO_e_um_pedido_existente(self):
        resposta = await self._pedir({
            "success": True, "existing": False, "request_id": "r1", "token": "t",
            "expires_at": "2099-01-01T00:00:00+00:00",
        })
        assert resposta.status.value == "pending"      # verdade nos dois casos…
        assert resposta.existing is False              # …e é isto que o ecrã tem de ler
        assert resposta.email_sent is True

    async def test_um_pedido_pendente_reutilizado_diz_existing(self):
        resposta = await self._pedir({
            "success": True, "existing": True, "status": "pending", "request_id": "r1",
            "expires_at": "2099-01-01T00:00:00+00:00",
        })
        assert resposta.existing is True and resposta.status.value == "pending"

    async def test_um_pedido_ja_assinado_diz_existing(self):
        resposta = await self._pedir({
            "success": True, "existing": True, "status": "signed", "request_id": "r1",
            "signed_at": "2026-10-01T10:00:00+00:00",
        })
        assert resposta.existing is True and resposta.status.value == "signed"

    async def test_se_o_email_nao_saiu_o_ecra_fica_a_saber(self):
        resposta = await self._pedir({
            "success": True, "existing": False, "request_id": "r1", "token": "t",
            "expires_at": "2099-01-01T00:00:00+00:00",
        }, email_sai=False)
        assert resposta.existing is False and resposta.email_sent is False

    def test_o_ecra_decide_por_existing_e_nao_pelo_estado(self):
        from pathlib import Path

        fonte = (Path(__file__).resolve().parents[3] / "frontend" / "src" / "pages" / "ProcessDetails.js").read_text(encoding="utf-8")
        assert "data.existing && data.status === 'pending'" in fonte
        assert "} else if (data.status === 'pending') {" not in fonte, "o ecrã voltou a ler só o estado"


# ════════════════════════════════════════════════════════════════════
#  CONVITE DO PORTAL: todos os escritores de processo o agendam
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestOConviteDoPortalNasciComOProcesso:
    async def test_o_ponto_unico_agenda_com_os_dados_do_cliente_e_a_empresa(self):
        from services import client_portal_email as mod

        chamadas = []

        async def falso(**kw):
            chamadas.append(kw)

        with patch("services.process_create.send_portal_welcome_email_from_process", falso):
            assert mod.agendar_convite_do_portal(
                client_id="c1", client_email=" ana@x.pt ", client_name="Ana",
                process_id="p1", company_id="cmp-domus", user={"id": "u"},
            ) is True
            from services.background_tasks import aguardar_tarefas_pendentes

            await aguardar_tarefas_pendentes()
        assert chamadas and chamadas[0]["client_email"] == "ana@x.pt"
        assert chamadas[0]["company_id"] == "cmp-domus" and chamadas[0]["process_id"] == "p1"

    async def test_sem_email_nao_ha_convite(self):
        from services import client_portal_email as mod

        assert mod.agendar_convite_do_portal(client_id="c1", client_email="  ", client_name="Ana") is False
        assert mod.agendar_convite_do_portal(client_id="c1", client_email=None, client_name="Ana") is False

    @pytest.mark.parametrize("modulo,funcao", [
        ("services.client_assign", "run_assign_client_to_user"),
        ("services.client_process_ops", "run_create_process_for_client"),
        ("services.process_create", "assemble_and_persist_staff_create"),
    ])
    def test_todo_escritor_de_processo_do_staff_agenda_o_convite(self, modulo, funcao):
        import importlib

        mod = importlib.import_module(modulo)
        alvo = getattr(mod, funcao, None)
        if alvo is None:  # o nome do orquestrador do create-client não é público: lê-se o módulo todo
            fonte = open(mod.__file__, encoding="utf-8").read()
            assert "send_portal_welcome_email_from_process(" in fonte
            return
        fonte = codigo_da_funcao_sem_comentarios(alvo)
        assert "agendar_convite_do_portal(" in fonte or "send_portal_welcome_email_from_process(" in fonte, (
            f"{modulo}.{funcao} cria processos e não agenda o convite do Portal"
        )

    def test_inventario_quem_insere_processos_de_clientes_trata_do_convite(self):
        """Falha por OMISSÃO: um escritor novo de `db.processes.insert_one` com cliente do staff tem de
        agendar o convite ou ficar na lista de excepções, com motivo."""
        import re
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[2] / "services"
        escritores = {
            p.name for p in raiz.glob("*.py")
            if re.search(r"db\.processes\.insert_one\(", p.read_text(encoding="utf-8"))
        }
        com_convite = {
            p.name for p in raiz.glob("*.py")
            if re.search(r"agendar_convite_do_portal\(|send_portal_welcome_email_from_process\(|deliver_registration_email\(",
                         p.read_text(encoding="utf-8"))
        }
        EXCEPCOES = {
            # Escritores que não são «o staff cria um processo para um cliente»:
            "process_create.py",            # create-client dispara o convite (verificado acima)
            "onboarding_mandatory_config.py",  # o cliente do registo público já recebeu o convite no registo
            "process_sharing.py", "process_migration.py", "admin_dev_ops.py", "seed_data.py",
            "partner_drafts.py", "partner_leads.py", "public_registration.py",
        }
        em_falta = sorted(escritores - com_convite - EXCEPCOES)
        assert not em_falta, f"escritores de processos sem convite do Portal nem excepção: {em_falta}"
        # Contraprova: o leitor encontrou escritores e os dois novos estão no conjunto com convite.
        assert {"client_assign.py", "client_process_ops.py"} <= escritores & com_convite


# ════════════════════════════════════════════════════════════════════
#  SINCRONIZAÇÃO DE EMAIL: o job fecha sempre
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestOJobDeSyncNuncaFicaAberto:
    def _servico(self, estado):
        class Servico:
            def __init__(self):
                self.falhas = []

            async def get_job(self, job_id):
                return {"id": job_id, "status": estado}

            async def fail_job(self, job_id, erro):
                self.falhas.append((job_id, erro))

        return Servico()

    async def test_um_corpo_que_rebenta_deixa_o_job_falhado(self):
        from services.email_webmail import _correr_job_de_sync

        servico = self._servico("processing")

        async def corpo():
            raise RuntimeError("a BD caiu dentro do except")

        with pytest.raises(RuntimeError):
            await _correr_job_de_sync(servico, "j1", "webmail", corpo)
        assert servico.falhas and servico.falhas[0][0] == "j1"

    async def test_um_corpo_cancelado_tambem_fecha_o_job(self):
        import asyncio

        from services.email_webmail import _correr_job_de_sync

        servico = self._servico("processing")

        async def corpo():
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await _correr_job_de_sync(servico, "j1", "pessoal", corpo)
        assert len(servico.falhas) == 1

    async def test_um_job_que_o_corpo_ja_terminou_nao_e_tocado(self):
        from services.email_webmail import _correr_job_de_sync

        for estado in ("completed", "failed"):
            servico = self._servico(estado)

            async def corpo():
                return None

            await _correr_job_de_sync(servico, "j1", "partilhada", corpo)
            assert servico.falhas == [], f"fechou um job {estado}"

    async def test_falhar_a_fechar_nunca_propaga(self):
        from services.email_webmail import _fechar_job_se_ficou_aberto

        class Partido:
            async def get_job(self, job_id):
                raise RuntimeError("Mongo")

        await _fechar_job_se_ficou_aberto(Partido(), "j1", "webmail")  # não levanta

    def test_os_tres_jobs_de_sync_passam_pelo_envelope(self):
        from pathlib import Path

        fonte = (Path(__file__).resolve().parents[2] / "services" / "email_webmail.py").read_text(encoding="utf-8")
        assert fonte.count("_correr_job_de_sync(job_service, job_id,") == 3
        for cru in ("spawn_background_task(run_sync())", "spawn_background_task(run_shared_sync())",
                    "spawn_background_task(run_user_sync())"):
            assert cru not in fonte, f"{cru} voltou a correr sem o envelope"

    def test_o_email_sync_e_um_tipo_proprio_para_o_ecra(self):
        from pathlib import Path

        fonte = (Path(__file__).resolve().parents[2] / "services" / "task_api_background.py").read_text(encoding="utf-8")
        assert '"email_sync": "EMAIL_SYNC"' in fonte


# ════════════════════════════════════════════════════════════════════
#  CÓDIGO MORTO APAGADO
# ════════════════════════════════════════════════════════════════════
class TestBroadcastPushFoiApagado:
    def test_a_funcao_ja_nao_existe(self):
        from services import push_notifications

        assert not hasattr(push_notifications, "broadcast_push_notification")

    def test_o_resto_do_modulo_continua_la(self):
        from services import push_notifications

        assert hasattr(push_notifications, "send_push_notification")
        assert hasattr(push_notifications, "cleanup_expired_subscriptions")
