"""
Lote 3 (Out 2026) — os emissores AGENDADOS não atravessam redes.

O PEDIDO
  «Garante que qualquer cron job ou tarefa de e-mail agendado respeita
  estritamente o isolamento de rede/empresa e não envia dados cruzados para
  gestores da rede errada.»

O QUE A AUDITORIA ENCONTROU (cada classe abaixo prova uma)
  1. `send_weekly_ai_report` somava as extracções de TODAS as redes e enviava-as
     a «admins» (todos os Admin/CEO — perfis locais), «all_staff» (toda a gente)
     ou a ids escolhidos, de qualquer rede.
  2. `check_stale_processes`: a partir de 21 dias, notificava os diretores/CEO
     de TODAS as redes, com o nome do cliente.
  3. `send_to_admins` (aviso de «novo processo») ia a todos os Admin/CEO/Master.
  4. `send_stuck_job_email` ia aos Admin de qualquer rede — e chamava o
     `send_email` com argumentos que não existem na assinatura: `TypeError`, que
     nenhum `except` apanhava, e o erro rebentava o varrimento inteiro.
  5. `send_monthly_reminder_email` saía pela conta SMTP de ambiente e com o nome
     da empresa do branding GLOBAL, para clientes de qualquer rede.
  6. (achado lateral) o processo criado pelo próprio cliente nascia sem carimbo.

COMO SE PROVA
  Corre-se o código real com um `send_email` falso (com a assinatura REAL, para
  um argumento inventado dar `TypeError` aqui como em produção) e afirma-se,
  email a email, QUEM recebeu QUE.
"""
from __future__ import annotations

import ast
import inspect
import smtplib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import alert_audience, relatorio_semanal_agenda as agenda
from services import relatorio_semanal_destinos as destinos
from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios, codigo_sem_comentarios
from tests.unit.helpers_tenant import REDE_DOMUS, REDE_INCUMBENTE, tenant_db

RAIZ = Path(__file__).resolve().parents[2]

EMPRESAS = [
    {"id": "cmp-power", "name": "Power Real Estate", "network_id": REDE_INCUMBENTE},
    {"id": "cmp-precision", "name": "Precision Crédito", "network_id": REDE_INCUMBENTE},
    {"id": "cmp-domus", "name": "Domus", "network_id": REDE_DOMUS},
]

UTILIZADORES = [
    {"id": "u-ceo-power", "name": "CEO Power", "email": "ceo@power.pt", "role": "ceo"},
    {"id": "u-dir-power", "name": "Dir Power", "email": "dir@power.pt", "role": "diretor"},
    {"id": "u-cons-power", "name": "Cons Power", "email": "cons@power.pt", "role": "consultor"},
    {"id": "u-adm-prec", "name": "Admin Precision", "email": "adm@precision.pt", "role": "admin"},
    {"id": "u-ceo-domus", "name": "CEO Domus", "email": "ceo@domus.pt", "role": "ceo"},
    {"id": "u-dir-domus", "name": "Dir Domus", "email": "dir@domus.pt", "role": "diretor"},
    {"id": "u-cons-domus", "name": "Cons Domus", "email": "cons@domus.pt", "role": "consultor"},
    {"id": "u-master", "name": "Master", "email": "master@x.pt", "role": "master"},
    {"id": "u-cliente", "name": "Cliente", "email": "cliente@x.pt", "role": "cliente"},
]

ACESSOS = [
    {"user_id": "u-ceo-power", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "ceo"},
    {"user_id": "u-dir-power", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "diretor"},
    {"user_id": "u-cons-power", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "consultor"},
    {"user_id": "u-adm-prec", "company_id": "cmp-precision", "company_name": "Precision Crédito", "role": "admin"},
    {"user_id": "u-ceo-domus", "company_id": "cmp-domus", "company_name": "Domus", "role": "ceo"},
    {"user_id": "u-dir-domus", "company_id": "cmp-domus", "company_name": "Domus", "role": "diretor"},
    {"user_id": "u-cons-domus", "company_id": "cmp-domus", "company_name": "Domus", "role": "consultor"},
]


@pytest.fixture
def mundo(fake_async_db):
    fake_async_db.companies.docs.extend(dict(e) for e in EMPRESAS)
    fake_async_db.users.docs.extend(dict(u) for u in UTILIZADORES)
    fake_async_db.user_company_roles.docs.extend(dict(a) for a in ACESSOS)
    return fake_async_db


@pytest.fixture
def servico(mundo, monkeypatch):
    """O serviço agendado real, com a BD falsa em toda a cadeia."""
    from services import scheduled_tasks

    monkeypatch.setattr(agenda, "db", mundo)
    monkeypatch.setattr(alert_audience, "db", mundo)
    monkeypatch.setattr(destinos, "db", mundo)
    monkeypatch.delenv("CEO_EMAIL", raising=False)
    monkeypatch.delenv("TENANT_DEFAULT_NETWORK_ID", raising=False)
    svc = scheduled_tasks.ScheduledTasksService()
    svc.db = mundo
    return svc


def _com_assinatura_real_do_send_email(enviados: list, *, falha_para: set | None = None):
    """Um `send_email` falso com a ASSINATURA de produção.

    Um duplo com `**kwargs` aceitava `to_email=` e escondia o `TypeError` que
    rebentava o varrimento em produção.
    """
    from services import email_service

    assinatura = inspect.signature(email_service.send_email)

    async def falso(*args, **kwargs):
        assinatura.bind(*args, **kwargs)  # levanta TypeError como a produção
        enviados.append(kwargs)
        if falha_para and set(kwargs.get("to_emails") or []) & falha_para:
            return {"success": False, "error": "SMTP"}
        return {"success": True}

    return falso


# ════════════════════════════════════════════════════════════════════
#  1. RELATÓRIO DE IA: UM POR REDE
# ════════════════════════════════════════════════════════════════════
def _extraccao(horas_atras: int = 2, ok: bool = True) -> dict:
    quando = datetime.now(timezone.utc) - timedelta(hours=horas_atras)
    return {
        "extracted_at": quando.isoformat(),
        "document_type": "cc",
        "extracted_data": {"client_name": "x"} if ok else {},
    }


@pytest.mark.asyncio
class TestOsDestinatariosDoRelatorioDeIA:
    async def _destinos(self, mundo):
        d = {x.chave: x for x in await destinos.montar_destinos(mundo)}
        return d[destinos.chave_da_rede(REDE_INCUMBENTE)], d[destinos.chave_da_rede(REDE_DOMUS)], d[destinos.CHAVE_GLOBAL]

    async def test_admins_e_a_gestao_da_rede_e_nada_mais(self, mundo, monkeypatch):
        monkeypatch.delenv("CEO_EMAIL", raising=False)
        power, domus, _ = await self._destinos(mundo)
        assert set(await destinos.destinatarios_do_relatorio_de_ia(power, "admins", [], mundo)) == {
            "ceo@power.pt", "adm@precision.pt",
        }
        assert await destinos.destinatarios_do_relatorio_de_ia(domus, "admins", [], mundo) == ["ceo@domus.pt"]

    async def test_all_staff_e_a_equipa_DA_REDE_nunca_a_de_outra(self, mundo, monkeypatch):
        monkeypatch.delenv("CEO_EMAIL", raising=False)
        power, domus, _ = await self._destinos(mundo)
        da_power = set(await destinos.destinatarios_do_relatorio_de_ia(power, "all_staff", [], mundo))
        da_domus = set(await destinos.destinatarios_do_relatorio_de_ia(domus, "all_staff", [], mundo))
        assert da_power == {"ceo@power.pt", "dir@power.pt", "cons@power.pt", "adm@precision.pt"}
        assert da_domus == {"ceo@domus.pt", "dir@domus.pt", "cons@domus.pt"}
        assert not da_power & da_domus

    async def test_all_staff_nunca_inclui_master_nem_clientes(self, mundo, monkeypatch):
        monkeypatch.delenv("CEO_EMAIL", raising=False)
        # Master e cliente com UCR na Domus: mesmo assim não são «equipa».
        mundo.user_company_roles.docs.extend([
            {"user_id": "u-master", "company_id": "cmp-domus", "company_name": "Domus", "role": "admin"},
            {"user_id": "u-cliente", "company_id": "cmp-domus", "company_name": "Domus", "role": "consultor"},
        ])
        _, domus, _ = await self._destinos(mundo)
        emails = set(await destinos.destinatarios_do_relatorio_de_ia(domus, "all_staff", [], mundo))
        assert "master@x.pt" not in emails
        assert "cliente@x.pt" not in emails

    async def test_custom_so_aceita_quem_pertence_ao_destino(self, mundo, monkeypatch):
        """Um id de outra rede na lista configurada NÃO recebe o relatório desta."""
        monkeypatch.delenv("CEO_EMAIL", raising=False)
        power, domus, _ = await self._destinos(mundo)
        ids = ["u-cons-power", "u-cons-domus"]
        assert await destinos.destinatarios_do_relatorio_de_ia(power, "custom", ids, mundo) == ["cons@power.pt"]
        assert await destinos.destinatarios_do_relatorio_de_ia(domus, "custom", ids, mundo) == ["cons@domus.pt"]

    async def test_o_consolidado_so_vai_aos_master_qualquer_que_seja_o_tipo(self, mundo, monkeypatch):
        monkeypatch.delenv("CEO_EMAIL", raising=False)
        _, _, consolidado = await self._destinos(mundo)
        for tipo in ("admins", "all_staff"):
            assert await destinos.destinatarios_do_relatorio_de_ia(consolidado, tipo, [], mundo) == ["master@x.pt"]
        # «custom» com ids de gente de redes: só passa o Master.
        escolhidos = ["u-ceo-power", "u-ceo-domus", "u-master"]
        assert await destinos.destinatarios_do_relatorio_de_ia(consolidado, "custom", escolhidos, mundo) == [
            "master@x.pt",
        ]

    async def test_um_tipo_desconhecido_cai_no_mais_estreito(self, mundo, monkeypatch):
        monkeypatch.delenv("CEO_EMAIL", raising=False)
        _, domus, _ = await self._destinos(mundo)
        assert await destinos.destinatarios_do_relatorio_de_ia(domus, "toda_a_gente", [], mundo) == ["ceo@domus.pt"]

    async def test_conta_antiga_sem_UCR_conta_na_sua_rede_mas_nao_se_tiver_UCR_noutra(self, mundo, monkeypatch):
        monkeypatch.delenv("CEO_EMAIL", raising=False)
        mundo.users.docs.extend([
            {"id": "u-velho", "email": "velho@domus.pt", "role": "consultor", "company": "Domus"},
            {"id": "u-dupla", "email": "dupla@power.pt", "role": "consultor", "company": "Domus"},
        ])
        mundo.user_company_roles.docs.append(
            {"user_id": "u-dupla", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "consultor"}
        )
        _, domus, _ = await self._destinos(mundo)
        emails = set(await destinos.destinatarios_do_relatorio_de_ia(domus, "all_staff", [], mundo))
        assert "velho@domus.pt" in emails
        assert "dupla@power.pt" not in emails, "tem UCR na Power: o campo legado não o põe na Domus"


@pytest.mark.asyncio
class TestOEnvioRealDoRelatorioDeIA:
    async def _correr(self, servico, enviados, *, config=None, falha_para=None):
        servico.db.system_config.docs.append({
            "type": "ai_report_config",
            "config": {"frequency": "daily", "recipients_type": "admins", **(config or {})},
        })
        with patch("services.email_service.send_email", _com_assinatura_real_do_send_email(enviados, falha_para=falha_para)):
            return await servico.send_weekly_ai_report()

    def _semear_processos(self, mundo):
        # Power: 3 extracções (2 com sucesso); Domus: 1.
        mundo.processes.docs.extend([
            {"id": "p-power-1", "network_id": REDE_INCUMBENTE, "company_id": "cmp-power",
             "ai_extraction_history": [_extraccao(), _extraccao(ok=False)]},
            {"id": "p-power-2", "network_id": REDE_INCUMBENTE, "company_id": "cmp-precision",
             "ai_extraction_history": [_extraccao()]},
            {"id": "p-domus", "network_id": REDE_DOMUS, "company_id": "cmp-domus",
             "ai_extraction_history": [_extraccao()]},
        ])

    async def test_cada_rede_recebe_so_o_seu_relatorio_com_os_seus_numeros(self, servico, mundo):
        self._semear_processos(mundo)
        enviados: list = []
        assert await self._correr(servico, enviados) is True

        por_destino = {tuple(sorted(e["to_emails"])): e for e in enviados}
        assert set(por_destino) == {("adm@precision.pt", "ceo@power.pt"), ("ceo@domus.pt",), ("master@x.pt",)}
        assert "Documentos analisados: 3" in por_destino[("adm@precision.pt", "ceo@power.pt")]["body"]
        assert "Documentos analisados: 1" in por_destino[("ceo@domus.pt",)]["body"]
        # O consolidado soma tudo e só vai ao Master.
        assert "Documentos analisados: 4" in por_destino[("master@x.pt",)]["body"]

        todos = [a for e in enviados for a in e["to_emails"]]
        assert len(todos) == len(set(todos)), "o mesmo endereço recebeu dois relatórios"

    async def test_o_CEO_da_Domus_nao_recebe_nada_da_Power(self, servico, mundo):
        self._semear_processos(mundo)
        enviados: list = []
        await self._correr(servico, enviados)
        domus = next(e for e in enviados if e["to_emails"] == ["ceo@domus.pt"])
        assert "Domus" in domus["subject"]
        assert "Power" not in domus["subject"] + domus["body"] + domus["body_html"].replace("PowerCell", "")

    async def test_a_falha_de_uma_rede_nao_marca_essa_rede(self, servico, mundo):
        self._semear_processos(mundo)
        enviados: list = []
        assert await self._correr(servico, enviados, falha_para={"ceo@domus.pt"}) is True
        marcas = {m["chave"] for m in mundo[agenda.COLECCAO].docs}
        assert f"relatorio_ia:{REDE_INCUMBENTE}" in marcas
        assert f"relatorio_ia:{REDE_DOMUS}" not in marcas, "marcou como enviado um envio que falhou"

        antes = len(enviados)
        await self._correr_sem_nova_config(servico, enviados)
        assert [e["to_emails"] for e in enviados[antes:]] == [["ceo@domus.pt"]], \
            "voltou a mandar às redes que já tinham o relatório"

    async def _correr_sem_nova_config(self, servico, enviados):
        with patch("services.email_service.send_email", _com_assinatura_real_do_send_email(enviados)):
            return await servico.send_weekly_ai_report()

    async def test_uma_rede_sem_extraccoes_nao_recebe_os_numeros_de_outra(self, servico, mundo):
        """A Domus sem actividade: o relatório dela diz 0, não os 3 da Power."""
        mundo.processes.docs.append(
            {"id": "p-power", "network_id": REDE_INCUMBENTE, "company_id": "cmp-power",
             "ai_extraction_history": [_extraccao(), _extraccao(), _extraccao()]}
        )
        enviados: list = []
        await self._correr(servico, enviados)
        domus = next(e for e in enviados if e["to_emails"] == ["ceo@domus.pt"])
        assert "Documentos analisados: 0" in domus["body"]

    async def test_a_configuracao_all_staff_continua_confinada(self, servico, mundo):
        self._semear_processos(mundo)
        enviados: list = []
        await self._correr(servico, enviados, config={"recipients_type": "all_staff"})
        domus = next(e for e in enviados if "ceo@domus.pt" in e["to_emails"])
        assert set(domus["to_emails"]) == {"ceo@domus.pt", "dir@domus.pt", "cons@domus.pt"}

    def test_a_marca_e_por_destino_e_so_depois_do_envio(self):
        from services.scheduled_tasks import ScheduledTasksService

        envio = codigo_da_funcao_sem_comentarios(ScheduledTasksService._enviar_relatorio_ia_de)
        assert "marcar_enviado_no_periodo(chave_da_agenda" in envio
        assert envio.index("send_email(") < envio.index("marcar_enviado_no_periodo(")
        # CONTRAPROVA: já não há a chave única global que serviria a todas as redes.
        assert "'relatorio_ia'" not in _fonte("services/scheduled_tasks.py")


# ════════════════════════════════════════════════════════════════════
#  2. PROCESSOS PARADOS HÁ MAIS DE 21 DIAS
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestProcessosParadosNaoAvisamOutraRede:
    def _processo(self, pid, rede=None, empresa=None, dias=40, consultor=None):
        doc = {
            "id": pid, "client_name": f"Cliente {pid}", "status": "em_curso",
            "updated_at": (datetime.now(timezone.utc) - timedelta(days=dias)).isoformat(),
            "assigned_consultor_id": consultor,
        }
        if rede:
            doc["network_id"] = rede
        if empresa:
            doc["company_id"] = empresa
        return doc

    async def _destinatarios(self, mundo, pid):
        return {n["user_id"] for n in mundo.notifications.docs if n.get("process_id") == pid}

    async def test_a_direccao_avisada_e_a_da_rede_do_processo(self, servico, mundo):
        mundo.processes.docs.append(self._processo("p-domus", REDE_DOMUS, "cmp-domus", consultor="u-cons-domus"))
        await servico.check_stale_processes()
        avisados = await self._destinatarios(mundo, "p-domus")
        assert {"u-cons-domus", "u-ceo-domus", "u-dir-domus"} <= avisados
        assert not avisados & {"u-ceo-power", "u-dir-power", "u-adm-prec"}, \
            "a direcção da Power foi avisada de um cliente da Domus"

    async def test_e_vice_versa(self, servico, mundo):
        mundo.processes.docs.append(self._processo("p-power", REDE_INCUMBENTE, "cmp-power"))
        await servico.check_stale_processes()
        avisados = await self._destinatarios(mundo, "p-power")
        assert {"u-ceo-power", "u-dir-power"} <= avisados
        assert not avisados & {"u-ceo-domus", "u-dir-domus"}

    async def test_o_atribuido_e_avisado_mesmo_sem_rede_mas_a_direccao_nao(self, servico, mundo):
        """Falha fechada: sem rede determinável a direcção não é avisada, o atribuído sim."""
        mundo.processes.docs.append(self._processo("p-orfao", consultor="u-cons-power"))
        await servico.check_stale_processes()
        assert await self._destinatarios(mundo, "p-orfao") == {"u-cons-power"}

    async def test_abaixo_dos_21_dias_so_os_atribuidos(self, servico, mundo):
        mundo.processes.docs.append(
            self._processo("p-novo", REDE_DOMUS, "cmp-domus", dias=15, consultor="u-cons-domus")
        )
        await servico.check_stale_processes()
        assert await self._destinatarios(mundo, "p-novo") == {"u-cons-domus"}


# ════════════════════════════════════════════════════════════════════
#  3. send_to_admins
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestSendToAdmins:
    async def _enviar(self, mundo, monkeypatch, **kwargs):
        from services import notification_service

        recebidos: list[str] = []

        async def falso(email, *args, **kw):
            recebidos.append(email)
            return True

        monkeypatch.setattr(notification_service, "send_notification_with_preference_check", falso)
        monkeypatch.setattr(alert_audience, "db", mundo)
        monkeypatch.delenv("TENANT_DEFAULT_NETWORK_ID", raising=False)
        await notification_service.send_to_admins("Novo Processo", "corpo", **kwargs)
        return set(recebidos)

    async def test_com_processo_vai_a_gestao_da_rede_e_ao_master(self, mundo, monkeypatch):
        recebidos = await self._enviar(
            mundo, monkeypatch, processo={"id": "p", "network_id": REDE_DOMUS, "company_id": "cmp-domus"},
        )
        assert recebidos == {"ceo@domus.pt", "master@x.pt"}

    async def test_sem_processo_so_o_master(self, mundo, monkeypatch):
        """Um aviso que não pertence a rede nenhuma não é da gestão de rede nenhuma."""
        assert await self._enviar(mundo, monkeypatch) == {"master@x.pt"}

    async def test_a_gestao_da_power_nunca_recebe_o_aviso_de_um_processo_da_domus(self, mundo, monkeypatch):
        recebidos = await self._enviar(
            mundo, monkeypatch, processo={"id": "p", "network_id": REDE_DOMUS, "company_id": "cmp-domus"},
        )
        assert not recebidos & {"ceo@power.pt", "adm@precision.pt"}

    async def test_o_processo_criado_pelo_cliente_herda_o_carimbo_da_ficha(self, mundo, monkeypatch):
        """Achado lateral: nascia sem rede, caía na de omissão e o aviso ia à gestão errada."""
        from services import process_create

        cliente = {"id": "cli", "network_id": REDE_DOMUS, "company_id": "cmp-domus", "company_name": "Domus"}
        gravado: dict = {}

        class _Processos:
            async def insert_one(self, doc):
                gravado.update(doc)

        class _Bd:
            processes = _Processos()

        avisos: list = []

        async def sem_efeito(*a, **k):
            return None

        async def aviso(subject, body, **kw):
            avisos.append(kw.get("processo"))

        async def inicial(**k):
            return ("novo", None)

        async def numero():
            return 7

        resposta = MagicMock(side_effect=lambda **kw: kw)
        with patch.object(process_create, "db", _Bd()), \
             patch.object(process_create, "load_client_doc_or_404", AsyncMock(return_value=cliente)), \
             patch.object(process_create, "resolve_initial_workflow_status", inicial), \
             patch.object(process_create, "aplicar_regime_de_indexacao", sem_efeito), \
             patch.object(process_create, "link_single_client_to_process", sem_efeito), \
             patch("services.process_service.get_next_process_number", numero), \
             patch("services.trello_service.sync_process_to_trello", sem_efeito):
            await process_create.persist_and_finalize_client_self_create(
                MagicMock(client_id="cli", process_type="credito_habitacao"),
                {"id": "u", "role": "cliente"},
                encrypt_fn=lambda d: d,
                decrypt_fn=lambda d: d,
                decrypt_client_fn=lambda d: {"nome": "Ana"},
                populate_fn=AsyncMock(side_effect=lambda d: d),
                log_history_fn=sem_efeito,
                broadcast_fn=sem_efeito,
                send_to_admins_fn=aviso,
                invalidate_stats_fn=sem_efeito,
                response_cls=resposta,
            )
        assert gravado["network_id"] == REDE_DOMUS
        assert gravado["company_id"] == "cmp-domus"
        assert avisos and avisos[0]["network_id"] == REDE_DOMUS, "o aviso não levou o processo"


# ════════════════════════════════════════════════════════════════════
#  4. JOBS BLOQUEADOS
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestJobsBloqueados:
    async def test_sem_enderecos_configurados_avisa_so_os_master(self, mundo, monkeypatch):
        from services import background_job_sweep

        monkeypatch.setattr(background_job_sweep, "db", mundo)
        monkeypatch.setattr(alert_audience, "db", mundo)
        mundo.system_config.docs.append({"type": "email_notifications", "enabled": True})
        # Mesmo com Admin/CEO de várias redes na base, só o Master recebe.
        mundo.users.docs.append({"id": "u-admin-x", "email": "admin@x.pt", "role": "admin"})
        enviados: list = []
        with patch("services.email_service.send_email", _com_assinatura_real_do_send_email(enviados)):
            await background_job_sweep.send_stuck_job_email([{"id": "j1", "name": "Job", "job_type": "ai"}])
        assert [e["to_emails"] for e in enviados] == [["master@x.pt"]]

    async def test_a_chamada_cumpre_a_assinatura_do_send_email(self, mundo, monkeypatch):
        """O defeito original: `to_email=` não existe e dava `TypeError`."""
        from services import background_job_sweep

        monkeypatch.setattr(background_job_sweep, "db", mundo)
        mundo.system_config.docs.append(
            {"type": "email_notifications", "enabled": True, "admin_emails": ["ops@x.pt"]}
        )
        enviados: list = []
        with patch("services.email_service.send_email", _com_assinatura_real_do_send_email(enviados)):
            await background_job_sweep.send_stuck_job_email([{"id": "j1"}])
        assert [e["to_emails"] for e in enviados] == [["ops@x.pt"]]

    async def test_o_aviso_nunca_derruba_o_varrimento(self, mundo, monkeypatch):
        from services import background_job_sweep

        monkeypatch.setattr(background_job_sweep, "db", mundo)
        mundo.system_config.docs.append(
            {"type": "email_notifications", "enabled": True, "admin_emails": ["ops@x.pt"]}
        )
        with patch("services.email_service.send_email", AsyncMock(side_effect=TypeError("assinatura"))):
            await background_job_sweep.send_stuck_job_email([{"id": "j1"}])  # não levanta

    async def test_o_varrimento_completo_sobrevive_a_jobs_bloqueados(self, mundo, monkeypatch):
        from services import background_job_sweep

        monkeypatch.setattr(background_job_sweep, "db", mundo)
        monkeypatch.setattr(alert_audience, "db", mundo)
        mundo.system_config.docs.append({"type": "email_notifications", "enabled": True})
        antigo = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        mundo.background_jobs.docs.append(
            {"id": "j1", "name": "Job", "status": "running", "updated_at": antigo}
        )
        enviados: list = []
        with patch("services.email_service.send_email", _com_assinatura_real_do_send_email(enviados)):
            assert await background_job_sweep.varrer_jobs_bloqueados() == 1
        assert enviados and enviados[0]["to_emails"] == ["master@x.pt"]


# ════════════════════════════════════════════════════════════════════
#  5. LEMBRETE MENSAL AO CLIENTE
# ════════════════════════════════════════════════════════════════════
class _PrimeiroDoMes(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 10, 1, 8, 0, tzinfo=tz or timezone.utc)


@pytest.mark.asyncio
class TestLembreteMensalEmNomeDaRede:
    def _contexto(self, nome, rede, conta=None):
        from services.portal_email_context import ContextoDoEmailDoPortal

        return ContextoDoEmailDoPortal(
            company_id=f"cmp-{nome.lower()}", company_name=nome, network_id=rede, account=conta,
        )

    async def test_cada_cliente_recebe_o_pedido_em_nome_da_sua_empresa(self, servico, mundo):
        from services import scheduled_tasks

        mundo.processes.docs.extend([
            {"id": "p-domus", "client_id": "c1", "client_name": "Ana", "client_email": "ana@x.pt",
             "status": "em_curso", "network_id": REDE_DOMUS, "company_id": "cmp-domus",
             "company_name": "Domus", "assigned_consultor_id": "u-cons-domus"},
            {"id": "p-power", "client_id": "c2", "client_name": "Rui", "client_email": "rui@x.pt",
             "status": "em_curso", "network_id": REDE_INCUMBENTE, "company_id": "cmp-power",
             "company_name": "Power Real Estate", "assigned_consultor_id": "u-cons-power"},
        ])
        pedidos: list[dict] = []

        async def resolver(**kw):
            pedidos.append(kw)
            return self._contexto(kw["company_name"], kw["network_id"])

        enviados: list[dict] = []

        async def enviar(contexto, **kw):
            enviados.append({"contexto": contexto, **kw})
            return {"success": True}

        async def todas_as_fases():
            return ["em_curso"]

        async def so_activos(processos):
            return processos

        with patch.object(scheduled_tasks, "datetime", _PrimeiroDoMes), \
             patch("services.workflow_phases.nomes_activos_de_todas_as_redes", todas_as_fases), \
             patch("services.workflow_phases.so_processos_com_fase_activa", so_activos), \
             patch("services.portal_email_context.resolver_contexto", resolver), \
             patch("services.portal_email_context.enviar_email_do_portal", enviar), \
             patch.object(smtplib, "SMTP_SSL", side_effect=AssertionError("SMTP de ambiente usado")):
            await servico.send_monthly_document_reminder()

        por_destinatario = {e["to_emails"][0]: e for e in enviados}
        assert set(por_destinatario) == {"ana@x.pt", "rui@x.pt"}

        domus = por_destinatario["ana@x.pt"]
        assert domus["contexto"].company_name == "Domus"
        assert domus["subject"].startswith("Domus - ")
        assert "Equipa Domus" in domus["body_html"]
        assert "Power" not in domus["body_html"] + domus["subject"]

        power = por_destinatario["rui@x.pt"]
        assert power["contexto"].company_name == "Power Real Estate"
        assert "Domus" not in power["body_html"] + power["subject"]

        assert {p["network_id"] for p in pedidos} == {REDE_DOMUS, REDE_INCUMBENTE}

    async def test_o_contexto_e_resolvido_uma_vez_por_empresa(self, servico, mundo):
        from services import scheduled_tasks

        for i in range(3):
            mundo.processes.docs.append({
                "id": f"p{i}", "client_name": f"C{i}", "client_email": f"c{i}@x.pt", "status": "em_curso",
                "network_id": REDE_DOMUS, "company_id": "cmp-domus", "company_name": "Domus",
            })
        chamadas: list = []

        async def resolver(**kw):
            chamadas.append(kw)
            return self._contexto("Domus", REDE_DOMUS)

        async def todas():
            return ["em_curso"]

        async def so_activos(p):
            return p

        with patch.object(scheduled_tasks, "datetime", _PrimeiroDoMes), \
             patch("services.workflow_phases.nomes_activos_de_todas_as_redes", todas), \
             patch("services.workflow_phases.so_processos_com_fase_activa", so_activos), \
             patch("services.portal_email_context.resolver_contexto", resolver), \
             patch("services.portal_email_context.enviar_email_do_portal", AsyncMock(return_value={"success": True})):
            await servico.send_monthly_document_reminder()
        assert len(chamadas) == 1

    async def test_rede_sem_remetente_nao_envia_em_nome_de_outra(self, servico, mundo, monkeypatch):
        """Sem caixa geral nem email de sistema numa rede que não é a de omissão: nada sai."""
        from services import portal_email_context as pec

        monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
        contexto = self._contexto("Domus", REDE_DOMUS, conta=None)
        send = AsyncMock(return_value={"success": True})
        with patch.object(pec, "_conta_de_sistema_generica", AsyncMock(return_value=None)), \
             patch("services.email_service.send_email", send):
            await servico.send_monthly_reminder_email(
                to_email="ana@x.pt", client_name="Ana", month_name="Setembro", year=2026, contexto=contexto,
            )
        send.assert_not_called()


# ════════════════════════════════════════════════════════════════════
#  6. GUARDAS SOBRE O CÓDIGO (com contraprova)
# ════════════════════════════════════════════════════════════════════
def _fonte(relativo: str) -> str:
    return codigo_sem_comentarios((RAIZ / relativo).read_text(encoding="utf-8"))


def _chamadas(caminho: Path) -> set[str]:
    """Nomes das funções chamadas num módulo (sem comentários nem docstrings)."""
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    nomes: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call):
            f = no.func
            nomes.add(f.id if isinstance(f, ast.Name) else getattr(f, "attr", ""))
    return nomes


MODULOS_DOS_EMISSORES_AGENDADOS = (
    "services/scheduled_tasks.py",
    "services/background_job_sweep.py",
    "services/notification_service.py",
    "services/relatorio_semanal_destinos.py",
)


class TestNenhumEmissorAgendadoEscolhePorCargoSemRede:
    @pytest.mark.parametrize("modulo", MODULOS_DOS_EMISSORES_AGENDADOS)
    def test_nenhum_usa_a_busca_por_cargo_sem_rede(self, modulo):
        """`deep_role_in_filter`/`deep_role_filter` num emissor é «todos os Admin do sistema».
        A audiência por cargo vive em `alert_audience` (rede) e nos destinos (UCR)."""
        usadas = _chamadas(RAIZ / modulo)
        assert "deep_role_in_filter" not in usadas, modulo
        assert "deep_role_filter" not in usadas, modulo

    def test_CONTRAPROVA_o_ponto_unico_continua_a_procurar_por_cargo(self):
        """Sem isto a guarda acima passava com um `alert_audience` que não faz nada."""
        assert "deep_role_filter" in _chamadas(RAIZ / "services" / "alert_audience.py")

    def test_o_lembrete_mensal_nao_usa_o_smtp_de_ambiente(self):
        fonte = _fonte("services/scheduled_tasks.py")
        assert "SMTP_SSL" not in fonte
        assert "SMTP_PASSWORD" not in fonte
        assert "_resolve_email_company_name" not in fonte

    def test_o_aviso_de_novo_processo_leva_o_processo(self):
        fonte = codigo_da_funcao_sem_comentarios(
            __import__("services.process_create", fromlist=["x"]).persist_and_finalize_client_self_create
        )
        assert "processo=process_doc" in fonte
