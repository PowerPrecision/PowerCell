"""Lote 7.1 — «Ver comprovativo» (403), envio de email do Master/CEO (403) e o Webmail sem o Index.

Cada ataque foi escrito primeiro e verificado VERMELHO no código anterior:

* `GET /financial-validation/process/{id}/proof-url` respondia 403 ao CEO que validava um processo
  vindo de um parceiro: o comprovativo entra com a LEAD (pasta do CLIENTE) e a guarda de posse do
  Portal, perguntada só pelo processo, só aceitava a subpasta `…/{cliente}/processos/{processo}`.
* `POST /emails/send` respondia 403 ao Master/CEO que escolhia uma empresa onde não tem conta pessoal
  (e, com a caixa geral, enviava pela conta de ambiente «power» fosse qual fosse a empresa activa).
* O perfil Index (`indexacao`) não tem Webmail.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import REDE_INCUMBENTE, semear, tenant_db

pytestmark = pytest.mark.asyncio

RAIZ = "Documentação Clientes"
DIRETORA_DA_POWER = {"id": "u-ana", "name": "Ana", "role": "diretor", "effective_role": "diretor"}


def _s3(existe=True):
    return patch.multiple(
        "services.s3_storage.s3_service",
        is_configured=MagicMock(return_value=True),
        file_exists=MagicMock(return_value=existe),
        get_presigned_url=MagicMock(return_value="https://s3.exemplo/assinado"),
    )


@pytest.fixture
def mundo(fake_async_db, monkeypatch):
    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
    semear(fake_async_db)
    # O processo veio de um parceiro: a lead enviou o comprovativo para a pasta do CLIENTE e,
    # quando nasceu o processo, o `s3_folder` dele ficou na subpasta do processo.
    fake_async_db.clients.docs.append({
        "id": "c-par", "nome": "Lead do Parceiro", "network_id": REDE_INCUMBENTE, "company_id": "cmp-power",
        "contacto": {}, "dados_pessoais": {}, "s3_folder": f"{RAIZ}/c-par",
    })
    fake_async_db.processes.docs.append({
        "id": "p-par", "client_id": "c-par", "client_name": "Lead do Parceiro", "status": "novo",
        "network_id": REDE_INCUMBENTE, "company_id": "cmp-power",
        "s3_folder": f"{RAIZ}/c-par/processos/p-par",
        "validacao_financeira": {"estado": "pendente"},
    })
    return fake_async_db


def _comprovativo(db, chave):
    db.documents.docs.append({
        "id": "doc-1", "client_id": "c-par", "comprovativo_de_pagamento": True,
        "attached_files": [{
            "file_id": "f1", "original_filename": "pagamento.pdf", "s3_path": chave,
            "uploaded_at": "2026-10-01T10:00:00+00:00",
        }],
    })


def _modulos():
    import services.financial_validation as fv
    import services.partner_drafts as pd

    return fv, pd


class TestOComprovativoAbre:
    async def test_o_ataque_o_comprovativo_na_pasta_do_cliente_abre_num_processo_com_pasta_propria(self, mundo):
        """O caso real: a pasta gravada no processo é a SUBPASTA, o ficheiro está na raiz do cliente."""
        from services.financial_validation import run_url_do_comprovativo

        _comprovativo(mundo, f"{RAIZ}/c-par/Comprovativos/pagamento.pdf")
        with tenant_db(mundo, *_modulos()), _s3():
            r = await run_url_do_comprovativo("process", "p-par", DIRETORA_DA_POWER)

        assert r["success"] is True
        assert r["url"] == "https://s3.exemplo/assinado"
        assert r["filename"] == "pagamento.pdf"

    async def test_o_comprovativo_dentro_da_pasta_do_processo_continua_a_abrir(self, mundo):
        from services.financial_validation import run_url_do_comprovativo

        _comprovativo(mundo, f"{RAIZ}/c-par/processos/p-par/Financeiros/pagamento.pdf")
        with tenant_db(mundo, *_modulos()), _s3():
            r = await run_url_do_comprovativo("process", "p-par", DIRETORA_DA_POWER)
        assert r["success"] is True

    async def test_a_lead_ainda_sem_processo_abre(self, mundo):
        from services.financial_validation import run_url_do_comprovativo

        mundo.clients.docs[-1]["validacao_financeira"] = {"estado": "pendente"}
        _comprovativo(mundo, f"{RAIZ}/c-par/Comprovativos/pagamento.pdf")
        with tenant_db(mundo, *_modulos()), _s3():
            r = await run_url_do_comprovativo("lead", "c-par", DIRETORA_DA_POWER)
        assert r["success"] is True


class TestAParedeContinua:
    """A guarda de posse não foi aliviada: só passou a perguntar também pela pasta do cliente."""

    @pytest.mark.parametrize("chave", [
        "backups/dump-2026-09-01.zip",                          # fora da raiz documental
        f"{RAIZ}/outro-cliente/Comprovativos/pagamento.pdf",    # pasta de outro cliente
        f"{RAIZ}/c-par-vizinho/pagamento.pdf",                  # prefixo de texto, não de segmento
    ])
    async def test_uma_chave_alheia_continua_a_dar_403(self, mundo, chave):
        from services.financial_validation import run_url_do_comprovativo

        _comprovativo(mundo, chave)
        with tenant_db(mundo, *_modulos()), _s3():
            with pytest.raises(HTTPException) as exc:
                await run_url_do_comprovativo("process", "p-par", DIRETORA_DA_POWER)
        assert exc.value.status_code == 403

    async def test_um_processo_de_outra_rede_continua_a_ser_404(self, mundo):
        from services.financial_validation import run_url_do_comprovativo

        mundo.processes.docs.append({
            "id": "p-domus-par", "client_id": "c-par", "status": "novo", "network_id": "grupo_domus",
            "company_id": "cmp-domus", "validacao_financeira": {"estado": "pendente"},
        })
        _comprovativo(mundo, f"{RAIZ}/c-par/Comprovativos/pagamento.pdf")
        with tenant_db(mundo, *_modulos()), _s3():
            with pytest.raises(HTTPException) as exc:
                await run_url_do_comprovativo("process", "p-domus-par", DIRETORA_DA_POWER)
        assert exc.value.status_code == 404

    async def test_o_consultor_continua_sem_o_botao_nem_a_rota(self, mundo):
        from services.financial_validation import run_url_do_comprovativo

        _comprovativo(mundo, f"{RAIZ}/c-par/Comprovativos/pagamento.pdf")
        consultor = {"id": "u-ana", "role": "consultor", "effective_role": "consultor"}
        with tenant_db(mundo, *_modulos()), _s3():
            with pytest.raises(HTTPException) as exc:
                await run_url_do_comprovativo("process", "p-par", consultor)
        assert exc.value.status_code == 403


class TestOIndexNaoTemWebmail:
    def _pedido(self, caminho):
        rota = MagicMock()
        rota.path = caminho
        r = MagicMock()
        r.scope = {"route": rota}
        r.method = "GET"
        r.url.path = caminho
        return r

    async def test_o_index_recebe_403_no_webmail(self):
        from services.webmail_perfis import exigir_perfil_com_webmail

        index = {"id": "u-i", "role": "indexacao", "effective_role": "indexacao"}
        for caminho in ("/api/emails/webmail", "/api/emails/send", "/api/emails/contacts", "/api/emails/{email_id}"):
            with pytest.raises(HTTPException) as exc:
                await exigir_perfil_com_webmail(self._pedido(caminho), index)
            assert exc.value.status_code == 403, caminho

    async def test_quem_e_index_de_base_mas_entra_como_consultor_tem_webmail(self):
        """O perfil que conta é o ACTIVO (a forma do `_is_stealth_user`)."""
        from services.webmail_perfis import exigir_perfil_com_webmail

        user = {"id": "u-i", "role": "indexacao", "effective_role": "consultor"}
        assert await exigir_perfil_com_webmail(self._pedido("/api/emails/webmail"), user) is None

    async def test_o_inverso_consultor_de_base_a_entrar_como_index_nao_tem(self):
        from services.webmail_perfis import exigir_perfil_com_webmail

        user = {"id": "u-c", "role": "consultor", "effective_role": "indexacao"}
        with pytest.raises(HTTPException) as exc:
            await exigir_perfil_com_webmail(self._pedido("/api/emails/webmail"), user)
        assert exc.value.status_code == 403

    @pytest.mark.parametrize("papel", ["master", "admin", "ceo", "diretor", "administrativo", "consultor", "intermediario"])
    async def test_os_restantes_perfis_de_staff_passam(self, papel):
        from services.webmail_perfis import exigir_perfil_com_webmail

        user = {"id": "u", "role": papel, "effective_role": papel}
        assert await exigir_perfil_com_webmail(self._pedido("/api/emails/webmail"), user) is None

    async def test_o_ecra_do_processo_continua_a_poder_ler_o_correio_ligado_a_ele(self):
        from services.webmail_perfis import ROTAS_DE_PROCESSO_QUE_FICAM, exigir_perfil_com_webmail

        index = {"id": "u-i", "role": "indexacao", "effective_role": "indexacao"}
        for sufixo in ROTAS_DE_PROCESSO_QUE_FICAM:
            assert await exigir_perfil_com_webmail(self._pedido(f"/api/emails{sufixo}"), index) is None

    def test_a_lista_de_excepcoes_e_a_escrita_aqui(self):
        """Por igualdade: uma rota nova de `/emails` nasce FECHADA ao Index."""
        from services.webmail_perfis import ROTAS_DE_PROCESSO_QUE_FICAM

        assert ROTAS_DE_PROCESSO_QUE_FICAM == frozenset({
            "/process/{process_id}", "/timeline/{process_id}", "/stats/{process_id}",
            "/sync-status/{process_id}", "/notifications/unread",
        })

    def test_o_router_de_emails_traz_a_guarda_e_ela_corre_primeiro(self):
        import routes.emails as emails
        from services.webmail_perfis import exigir_perfil_com_webmail

        dependencias = [d.dependency for d in emails.router.dependencies]
        assert exigir_perfil_com_webmail in dependencias
        assert dependencias[0] is exigir_perfil_com_webmail

    async def test_o_envio_tambem_recusa_o_index_dentro_do_servico(self):
        """Defesa em profundidade: o serviço não depende de o router ter a guarda."""
        from models.email import EmailSendRequest
        from services.email_process_crud import run_send_email

        payload = EmailSendRequest(to_emails=["a@b.pt"], subject="x", body="y")
        index = {"id": "u-i", "email": "i@x.pt", "role": "indexacao", "effective_role": "indexacao"}
        request = MagicMock()
        request.headers = {"x-company-id": "cmp-power"}
        with pytest.raises(HTTPException) as exc:
            await run_send_email(payload, request, index)
        assert exc.value.status_code == 403
        assert "Index" in exc.value.detail


# ════════════════════════════════════════════════════════════════════
#  O ENVIO DO MASTER/CEO COM EMPRESA ESCOLHIDA
# ════════════════════════════════════════════════════════════════════
CAIXA_DA_DOMUS = {
    "email_address": "geral@domus.pt", "password": "segredo", "smtp_server": "smtp.domus.pt",
    "smtp_port": 465, "imap_server": "imap.domus.pt", "imap_port": 993, "source": "caixa_geral",
}


def _pedido(empresa="cmp-domus"):
    r = MagicMock()
    r.headers = {"x-company-id": empresa}
    return r


def _payload(**extra):
    from models.email import EmailSendRequest

    return EmailSendRequest(to_emails=["cliente@exemplo.pt"], subject="Assunto", body="Corpo", **extra)


def _utilizador(papel):
    return {"id": f"u-{papel}", "email": f"{papel}@x.pt", "name": papel, "role": papel, "effective_role": papel}


class _Envio:
    """Apanha o registo que `run_send_email` põe na fila (o que se EXECUTA é testado à parte)."""

    def __init__(self, *, pessoal=None, caixa=None):
        self.registos = []
        self.pessoal = pessoal
        self.caixa = caixa

    async def correr(self, papel, **extra):
        from services.email_process_crud import run_send_email

        async def _fila(record):
            self.registos.append(record)
            return {"success": True, "queued": True, "send_id": record["id"]}

        with patch("services.email_config_resolver.resolve_email_config_for_sync", AsyncMock(return_value=self.pessoal)), \
             patch("services.email_config_resolver.load_caixa_geral_config", AsyncMock(return_value=self.caixa)), \
             patch("services.email_branding.resolve_active_company_branding", AsyncMock(return_value=("Domus", None))), \
             patch("services.email_send_queue.queue_email_send", _fila):
            return await run_send_email(_payload(**extra), _pedido(), _utilizador(papel))


class TestOEnvioComEmpresaEscolhida:
    @pytest.mark.parametrize("papel", ["master", "ceo", "admin", "diretor"])
    async def test_o_ataque_sem_conta_pessoal_na_empresa_usa_a_caixa_geral_dela(self, papel):
        """Era 403 («Configuração de email não encontrada para esta empresa»)."""
        envio = _Envio(pessoal=None, caixa=CAIXA_DA_DOMUS)
        await envio.correr(papel, from_box="personal")

        assert len(envio.registos) == 1
        r = envio.registos[0]
        assert r["usar_caixa_geral"] is True
        assert r["account"] == "caixa_geral"
        assert r["from_email"] == "geral@domus.pt"
        assert r["company_id"] == "cmp-domus"
        assert "password" not in str(r)

    async def test_com_conta_pessoal_na_empresa_continua_a_ser_a_pessoal(self):
        envio = _Envio(pessoal={"email_address": "rui@domus.pt"}, caixa=CAIXA_DA_DOMUS)
        await envio.correr("ceo", from_box="personal")

        r = envio.registos[0]
        assert r["usar_caixa_geral"] is False
        assert r["account"] == "personal"
        assert r["from_email"] == "rui@domus.pt"

    async def test_sem_conta_pessoal_nem_caixa_geral_continua_a_ser_403_com_motivo(self):
        envio = _Envio(pessoal=None, caixa=None)
        with pytest.raises(HTTPException) as exc:
            await envio.correr("ceo", from_box="personal")
        assert exc.value.status_code == 403
        assert "Configuração de email" in exc.value.detail
        assert envio.registos == []

    @pytest.mark.parametrize("papel", ["consultor", "intermediario"])
    async def test_o_consultor_sem_conta_pessoal_NAO_cai_na_caixa_geral(self, papel):
        """A Caixa Geral é de quem a pode abrir (`CAIXA_GERAL_ROLES`); o consultor não."""
        envio = _Envio(pessoal=None, caixa=CAIXA_DA_DOMUS)
        with pytest.raises(HTTPException) as exc:
            await envio.correr(papel, from_box="personal")
        assert exc.value.status_code == 403
        assert envio.registos == []

    async def test_a_caixa_geral_pedida_sai_pela_da_empresa_activa_e_nao_pela_conta_power(self):
        """Antes: `account = "power"` (conta de ambiente) fosse qual fosse a empresa activa."""
        envio = _Envio(pessoal=None, caixa=CAIXA_DA_DOMUS)
        await envio.correr("ceo", from_box="general")

        r = envio.registos[0]
        assert r["account"] == "caixa_geral" and r["account"] != "power"
        assert r["usar_caixa_geral"] is True
        assert r["from_email"] == "geral@domus.pt"

    async def test_a_caixa_geral_pedida_sem_caixa_configurada_diz_que_falta_e_nao_envia(self):
        envio = _Envio(pessoal=None, caixa=None)
        with pytest.raises(HTTPException) as exc:
            await envio.correr("ceo", from_box="general")
        assert exc.value.status_code == 400
        assert "Caixa Geral" in exc.value.detail
        assert envio.registos == []

    async def test_o_consultor_nao_envia_pela_caixa_geral(self):
        envio = _Envio(pessoal={"email_address": "c@x.pt"}, caixa=CAIXA_DA_DOMUS)
        with pytest.raises(HTTPException) as exc:
            await envio.correr("consultor", from_box="general")
        assert exc.value.status_code == 403

    async def test_decide_o_perfil_activo_e_nao_o_do_jwt(self):
        """Consultor de base que entra COMO CEO tem a Caixa Geral (a forma do `_is_stealth_user`)."""
        from services.email_process_crud import run_send_email

        envio = _Envio(pessoal=None, caixa=CAIXA_DA_DOMUS)
        base_consultor_como_ceo = {**_utilizador("consultor"), "effective_role": "ceo"}

        async def _fila(record):
            envio.registos.append(record)
            return {"success": True}

        with patch("services.email_config_resolver.resolve_email_config_for_sync", AsyncMock(return_value=None)), \
             patch("services.email_config_resolver.load_caixa_geral_config", AsyncMock(return_value=CAIXA_DA_DOMUS)), \
             patch("services.email_branding.resolve_active_company_branding", AsyncMock(return_value=("Domus", None))), \
             patch("services.email_send_queue.queue_email_send", _fila):
            await run_send_email(_payload(from_box="general"), _pedido(), base_consultor_como_ceo)
        assert envio.registos[0]["usar_caixa_geral"] is True


class TestOExecutorEnviaPelaCaixaDaEmpresa:
    """Um nível ABAIXO: o executor real reconstrói a conta e passa-a ao `send_email`."""

    async def test_o_send_email_recebe_a_conta_da_caixa_e_nao_a_power(self, fake_async_db):
        import services.email_send_queue as fila

        registo = fila.build_pending_send_record(
            account="caixa_geral", to_emails=["c@x.pt"], subject="s", body="b", body_html=None,
            cc_emails=None, process_id=None, from_box="general", from_email="geral@domus.pt",
            company_id="cmp-domus", created_by="u-ceo", created_by_email="ceo@x.pt",
            attachment_ids=[], usar_caixa_geral=True,
        )
        fake_async_db.pending_email_sends.docs.append(registo)
        enviar = AsyncMock(return_value={"success": True})

        with patch.object(fila, "db", fake_async_db), \
             patch.object(fila, "send_email", enviar), \
             patch("services.email_config_resolver.load_caixa_geral_config", AsyncMock(return_value=CAIXA_DA_DOMUS)):
            r = await fila.execute_pending_email_send(registo["id"])

        assert r["success"] is True
        chamada = enviar.await_args.kwargs
        conta = chamada["account_override"]
        assert conta is not None
        assert (conta.email, conta.smtp_server) == ("geral@domus.pt", "smtp.domus.pt")
        assert chamada["active_company_id"] == "cmp-domus"

    async def test_se_a_caixa_deixou_de_existir_o_envio_falha_com_motivo_e_nao_sai_pela_power(self, fake_async_db):
        import services.email_send_queue as fila

        registo = fila.build_pending_send_record(
            account="caixa_geral", to_emails=["c@x.pt"], subject="s", body="b", body_html=None,
            cc_emails=None, process_id=None, from_box="general", from_email="geral@domus.pt",
            company_id="cmp-domus", created_by="u-ceo", created_by_email="ceo@x.pt",
            attachment_ids=[], usar_caixa_geral=True,
        )
        fake_async_db.pending_email_sends.docs.append(registo)
        enviar = AsyncMock(return_value={"success": True})

        with patch.object(fila, "db", fake_async_db), \
             patch.object(fila, "send_email", enviar), \
             patch("services.email_config_resolver.load_caixa_geral_config", AsyncMock(return_value=None)):
            r = await fila.execute_pending_email_send(registo["id"])

        assert r["success"] is False
        assert "Caixa Geral" in r["reason"]
        enviar.assert_not_awaited()

    async def test_um_envio_pessoal_nao_leva_conta_alternativa(self, fake_async_db):
        import services.email_send_queue as fila

        registo = fila.build_pending_send_record(
            account="personal", to_emails=["c@x.pt"], subject="s", body="b", body_html=None,
            cc_emails=None, process_id=None, from_box="personal", from_email="rui@domus.pt",
            company_id="cmp-domus", created_by="u-ceo", created_by_email="ceo@x.pt", attachment_ids=[],
        )
        assert registo["usar_caixa_geral"] is False
        fake_async_db.pending_email_sends.docs.append(registo)
        enviar = AsyncMock(return_value={"success": True})
        with patch.object(fila, "db", fake_async_db), patch.object(fila, "send_email", enviar):
            await fila.execute_pending_email_send(registo["id"])
        assert enviar.await_args.kwargs["account_override"] is None
