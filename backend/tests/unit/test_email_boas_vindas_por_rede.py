"""E-mail de boas-vindas/registo: a marca, o remetente e o link são os da REDE do cliente (QA, Out 2026).

O defeito: o email saía como se todo o cliente fosse da Power — o corpo dizia
«Power Real Estate», o remetente era a conta global (``account_name="power"``)
e o link do Portal nunca chegava ao template. Aqui prova-se, para uma empresa de
OUTRA rede (a Domus), que nada da Power aparece em lado nenhum, que o
remetente é o email geral da rede (ou o de sistema genérico) e que o link vai
no corpo.

Três níveis, porque um duplo demasiado esperto valida o duplo:
  * a resolução do contexto (quem é a empresa, qual é a caixa, qual é o link);
  * o conteúdo e o ``send_email`` chamado (parâmetros que SAEM);
  * o ``send_email`` REAL contra um SMTP falso (o cabeçalho ``From`` e a
    assinatura global do sistema).
"""
from __future__ import annotations

import dataclasses
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.unit.helpers_tenant import EMPRESAS, REDE_DOMUS, REDE_INCUMBENTE, tenant_db

pytestmark = pytest.mark.asyncio

FRONTEND = "https://crm.exemplo.pt"
PORTAL = f"{FRONTEND}/portal"

CAIXA_POWER = {
    "imap_user": "geral@powerealestate.pt", "imap_password": "pw-power",
    "smtp_server": "smtp.power.pt", "imap_server": "imap.power.pt",
}
CAIXA_DOMUS = {
    "imap_user": "geral@domus.pt", "imap_password": "pw-domus",
    "smtp_server": "smtp.domus.pt", "imap_server": "imap.domus.pt",
}
CAIXA_PRECISION = {
    "imap_user": "geral@precision.pt", "imap_password": "pw-precision",
    "smtp_server": "smtp.precision.pt", "imap_server": "imap.precision.pt",
}


def _base(fake, *, domus_email=None, precision_email=None, power_email=True, nomes_globais=True):
    """Empresas + configuração global (a da Power) + o que cada empresa configurou."""
    for e in EMPRESAS:
        fake.companies.docs.append(dict(e))
    if power_email:
        fake.system_config.docs.append({
            "_id": "main", "email": dict(CAIXA_POWER),
            "settings": {"company_name": "Power Real Estate"} if nomes_globais else {},
        })
    if domus_email is not None:
        fake.system_config.docs.append({
            "_id": "company:cmp-domus", "email": dict(domus_email),
            # A cópia herdada que o `get_system_config` grava: leva o NOME da Power.
            "settings": {"company_name": "Power Real Estate"},
        })
    if precision_email is not None:
        fake.system_config.docs.append({"_id": "company:cmp-precision", "email": dict(precision_email)})
    return fake


def _ambiente(fake, monkeypatch):
    """A BD falsa em toda a cadeia + a rede de omissão do grupo incumbente."""
    import services.portal_email_context as ctx_mod

    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
    pilha = ExitStack()
    pilha.enter_context(tenant_db(fake, ctx_mod))
    return pilha


async def _contexto(**kw):
    from services.portal_email_context import resolver_contexto

    kw.setdefault("frontend_url", FRONTEND)
    return await resolver_contexto(**kw)


# ═════════════════════════════════════════════════════════════════════
# 1. QUEM É A EMPRESA E QUAL É O REMETENTE
# ═════════════════════════════════════════════════════════════════════


class TestContextoDaRede:
    async def test_cliente_da_domus_leva_nome_logo_e_caixa_da_domus(self, fake_async_db, monkeypatch):
        _base(fake_async_db, domus_email=CAIXA_DOMUS)
        fake_async_db.companies.docs[-1]["logo_url"] = "https://cdn.exemplo.pt/domus.png"
        fake_async_db.clients.docs.append(
            {"id": "c1", "company_id": "cmp-domus", "network_id": REDE_DOMUS}
        )
        with _ambiente(fake_async_db, monkeypatch):
            ctx = await _contexto(client_id="c1")

        assert ctx.company_name == "Domus"
        assert ctx.network_id == REDE_DOMUS
        assert ctx.logo_url == "https://cdn.exemplo.pt/domus.png"
        assert ctx.account is not None and ctx.account.email == "geral@domus.pt"
        assert ctx.account_source == "caixa_geral_da_empresa"
        assert ctx.portal_url == PORTAL

    async def test_o_nome_herdado_da_configuracao_global_nao_passa(self, fake_async_db, monkeypatch):
        """`company:cmp-domus` é uma CÓPIA da global (nome «Power Real Estate»): vale a empresa."""
        _base(fake_async_db, domus_email=CAIXA_DOMUS)
        with _ambiente(fake_async_db, monkeypatch):
            ctx = await _contexto(company_id="cmp-domus")
        assert ctx.company_name == "Domus"
        assert "Power" not in (ctx.company_name or "")

    async def test_caixa_herdada_da_global_nao_e_da_domus(self, fake_async_db, monkeypatch):
        """Sem email próprio a Domus tem a CÓPIA da Power: não se envia com ela."""
        _base(fake_async_db, domus_email=CAIXA_POWER)
        with _ambiente(fake_async_db, monkeypatch):
            ctx = await _contexto(company_id="cmp-domus")
        assert ctx.account is None
        assert ctx.account_source == "sistema"

    async def test_domus_sem_nenhuma_configuracao_nunca_usa_a_caixa_global(self, fake_async_db, monkeypatch):
        _base(fake_async_db)
        with _ambiente(fake_async_db, monkeypatch):
            ctx = await _contexto(company_id="cmp-domus")
        assert ctx.account is None
        assert ctx.account_source == "sistema"

    async def test_a_rede_de_omissao_usa_a_configuracao_global(self, fake_async_db, monkeypatch):
        """A Power É o grupo incumbente: a configuração global é dela."""
        _base(fake_async_db)
        with _ambiente(fake_async_db, monkeypatch):
            ctx = await _contexto(company_id="cmp-power")
        assert ctx.company_name == "Power Real Estate"
        assert ctx.account.email == "geral@powerealestate.pt"
        assert ctx.account_source == "caixa_geral_da_rede_de_omissao"

    async def test_empresa_da_mesma_rede_serve_de_caixa_da_rede(self, fake_async_db, monkeypatch):
        """A Precision não configurou: usa o email geral de outra empresa da MESMA rede."""
        _base(fake_async_db, precision_email=None)
        fake_async_db.system_config.docs.append(
            {"_id": "company:cmp-power", "email": dict(CAIXA_PRECISION)}
        )
        with _ambiente(fake_async_db, monkeypatch):
            ctx = await _contexto(company_id="cmp-precision")
        assert ctx.company_name == "Precision Crédito"
        assert ctx.account.email == "geral@precision.pt"
        assert ctx.account_source == "caixa_geral_da_rede"

    async def test_a_caixa_de_outra_rede_nunca_e_candidata(self, fake_async_db, monkeypatch):
        _base(fake_async_db, domus_email=CAIXA_DOMUS)
        with _ambiente(fake_async_db, monkeypatch):
            ctx = await _contexto(company_id="cmp-power", network_id=REDE_INCUMBENTE)
        assert ctx.account.email != "geral@domus.pt"

    async def test_sem_empresa_o_nome_e_neutro_e_nao_se_adivinha_a_caixa(self, fake_async_db, monkeypatch):
        _base(fake_async_db)
        with _ambiente(fake_async_db, monkeypatch):
            ctx = await _contexto()
        assert ctx.company_name is None
        assert ctx.nome == "Portal do Cliente"
        assert ctx.account is None

    async def test_o_carimbo_de_quem_cria_define_a_empresa(self, fake_async_db, monkeypatch):
        _base(fake_async_db, domus_email=CAIXA_DOMUS)
        fake_async_db.user_company_roles.docs.append(
            {"user_id": "u-b", "company_id": "cmp-domus", "company_name": "Domus", "role": "diretor"}
        )
        user = {"id": "u-b", "role": "diretor", "company": "Domus", "active_company_id": "cmp-domus"}
        with _ambiente(fake_async_db, monkeypatch):
            ctx = await _contexto(user=user)
        assert ctx.company_name == "Domus"
        assert ctx.account.email == "geral@domus.pt"

    async def test_uma_falha_cai_no_contexto_neutro_e_nunca_levanta(self, fake_async_db, monkeypatch):
        import services.portal_email_context as ctx_mod

        _base(fake_async_db)
        with _ambiente(fake_async_db, monkeypatch), \
                patch.object(ctx_mod, "_empresa_do_registo", AsyncMock(side_effect=RuntimeError("bd"))):
            ctx = await _contexto(company_id="cmp-domus")
        assert ctx.company_name is None and ctx.account is None
        assert ctx.portal_url == PORTAL

    async def test_o_link_e_absoluto_e_sem_dominio_diz_se(self, monkeypatch, caplog):
        from services.portal_email_context import url_do_portal

        monkeypatch.delenv("FRONTEND_URL", raising=False)
        assert url_do_portal("https://a.pt/") == "https://a.pt/portal"
        assert url_do_portal(None, portal_url="https://b.pt/portal/XYZ") == "https://b.pt/portal/XYZ"
        with caplog.at_level("ERROR"):
            assert url_do_portal(None) == ""
        assert "FRONTEND_URL" in caplog.text
        monkeypatch.setenv("FRONTEND_URL", "https://env.pt/")
        assert url_do_portal(None) == "https://env.pt/portal"


# ═════════════════════════════════════════════════════════════════════
# 2. O CONTEÚDO E O QUE SAI PARA O send_email
# ═════════════════════════════════════════════════════════════════════


def _contexto_domus(**kw):
    from services.email_service import EmailAccount
    from services.portal_email_context import ContextoDoEmailDoPortal

    base = dict(
        company_id="cmp-domus", company_name="Domus", network_id=REDE_DOMUS,
        logo_url="https://cdn.exemplo.pt/domus.png",
        account=EmailAccount("caixa_geral_da_rede", "imap.domus.pt", 993, "smtp.domus.pt", 465,
                             "geral@domus.pt", "pw-domus"),
        account_source="caixa_geral_da_empresa", portal_url=PORTAL,
    )
    base.update(kw)
    return ContextoDoEmailDoPortal(**base)


class TestConteudoDoEmail:
    async def _enviar(self, contexto, **kw):
        from services.email import send_registration_confirmation

        send = AsyncMock(return_value={"success": True})
        with patch("services.email_service.send_email", send):
            ok = await send_registration_confirmation(
                "cli@x.pt", "Maria", portal_access_code=kw.pop("codigo", "123456"),
                contexto=contexto, **kw,
            )
        return ok, send

    async def test_nada_da_power_aparece_no_email_da_domus(self):
        ok, send = await self._enviar(_contexto_domus())
        assert ok is True
        k = send.await_args.kwargs
        for texto in (k["subject"], k["body"], k["body_html"]):
            assert "Power" not in texto and "Precision" not in texto
            assert "powerealestate" not in texto.lower()
        assert "Domus" in k["subject"] and "<h1>Domus</h1>" in k["body_html"]
        assert '<p class="company">Domus</p>' in k["body_html"]
        assert "https://cdn.exemplo.pt/domus.png" in k["body_html"]

    async def test_o_link_do_portal_vai_no_html_e_no_texto(self):
        _, send = await self._enviar(_contexto_domus())
        k = send.await_args.kwargs
        assert f'<a href="{PORTAL}" class="btn">Aceder ao Portal do Cliente</a>' in k["body_html"]
        assert f"Aceder ao Portal: {PORTAL}" in k["body"]
        assert "123456" in k["body_html"] and "123456" in k["body"]

    async def test_o_link_vai_mesmo_sem_codigo_de_acesso(self):
        _, send = await self._enviar(_contexto_domus(), codigo=None)
        k = send.await_args.kwargs
        assert PORTAL in k["body_html"] and PORTAL in k["body"]

    async def test_sem_link_nao_ha_botao_nem_endereco_inventado(self):
        _, send = await self._enviar(_contexto_domus(portal_url=""))
        k = send.await_args.kwargs
        assert 'class="btn"' not in k["body_html"]
        assert "Aceder ao Portal:" not in k["body"]

    async def test_sai_da_caixa_geral_da_rede_com_o_nome_da_empresa(self):
        _, send = await self._enviar(_contexto_domus())
        k = send.await_args.kwargs
        assert k["account_override"].email == "geral@domus.pt"
        assert k["from_name_override"] == "Domus"
        assert k["use_system_signature"] is False
        # É uma caixa monitorizada e respondível: não é um envio «de sistema».
        assert not k.get("force_system")

    async def test_sem_caixa_sai_do_email_de_sistema_com_o_nome_da_empresa(self):
        from services.email_service import EmailAccount

        sistema = EmailAccount("system_smtp", "resend", 0, "resend", 0, "no-reply@sistema.pt", "k")
        ctx = _contexto_domus(account=None, account_source="sistema")
        with patch("services.portal_email_context._conta_de_sistema_generica",
                   AsyncMock(return_value=sistema)):
            ok, send = await self._enviar(ctx)
        k = send.await_args.kwargs
        assert ok is True
        assert k["account_override"].email == "no-reply@sistema.pt"
        assert k["force_system"] is True and k["system_purpose"] == "NOTIFICATIONS"
        assert k["from_name_override"] == "Domus"
        assert k["use_system_signature"] is False

    async def test_rede_alheia_sem_email_de_sistema_nao_envia_em_nome_de_outra(self):
        """Sem caixa nem sistema, o recurso às contas de ambiente (a Power) é proibido."""
        ctx = _contexto_domus(account=None, account_source="sistema")
        with patch("services.portal_email_context._conta_de_sistema_generica",
                   AsyncMock(return_value=None)):
            ok, send = await self._enviar(ctx)
        assert ok is False
        send.assert_not_awaited()

    async def test_a_rede_de_omissao_ainda_pode_usar_o_recurso_legado(self, monkeypatch):
        monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
        ctx = _contexto_domus(account=None, network_id=REDE_INCUMBENTE,
                              company_name="Power Real Estate", account_source="sistema")
        with patch("services.portal_email_context._conta_de_sistema_generica",
                   AsyncMock(return_value=None)):
            ok, send = await self._enviar(ctx)
        assert ok is True
        assert send.await_args.kwargs["account_override"] is None

    async def test_sem_contexto_o_email_e_neutro_e_nunca_da_power(self):
        from services.email import send_registration_confirmation

        send = AsyncMock(return_value={"success": True})
        with patch("services.portal_email_context._conta_de_sistema_generica",
                   AsyncMock(return_value=object())), \
                patch("services.email_service.send_email", send):
            await send_registration_confirmation("cli@x.pt", "Maria", portal_access_code="9")
        k = send.await_args.kwargs
        assert "Power" not in k["body_html"] and "Power" not in k["subject"]
        assert "Portal do Cliente" in k["subject"]
        assert "precisioncredito" not in k["body_html"].lower()


# ═════════════════════════════════════════════════════════════════════
# 3. A ENTREGA (client_id → contexto, e o retry da fila)
# ═════════════════════════════════════════════════════════════════════


@pytest.fixture
def entrega_mockada():
    """`deliver_registration_email` sem tocar em estado de entrega nem em fila."""
    import services.email_delivery_status as eds

    with patch.object(eds, "begin_portal_email_task", AsyncMock(return_value="t1")), \
            patch.object(eds, "complete_portal_email_task", AsyncMock()), \
            patch.object(eds, "fail_portal_email_task", AsyncMock()), \
            patch.object(eds, "mark_portal_email_retry_scheduled", AsyncMock()):
        yield


class TestEntrega:
    async def test_o_contexto_vem_do_carimbo_do_cliente(self, fake_async_db, monkeypatch, entrega_mockada):
        import services.client_portal_email as cpe

        _base(fake_async_db, domus_email=CAIXA_DOMUS)
        fake_async_db.clients.docs.append(
            {"id": "c1", "company_id": "cmp-domus", "network_id": REDE_DOMUS}
        )
        envio = AsyncMock(return_value=True)
        with _ambiente(fake_async_db, monkeypatch), \
                patch.object(cpe, "db", fake_async_db), \
                patch("services.email.send_registration_confirmation", envio):
            ok = await cpe.deliver_registration_email(
                "cli@x.pt", "Maria", portal_access_code="1", client_id="c1", frontend_url=FRONTEND,
            )
        assert ok is True
        ctx = envio.await_args.kwargs["contexto"]
        assert ctx.company_name == "Domus"
        assert ctx.account.email == "geral@domus.pt"
        assert ctx.portal_url == PORTAL

    async def test_o_retry_da_fila_leva_a_empresa_e_o_link(self, fake_async_db, monkeypatch, entrega_mockada):
        import services.client_portal_email as cpe

        _base(fake_async_db, domus_email=CAIXA_DOMUS)
        fila = AsyncMock(return_value="job-1")
        with _ambiente(fake_async_db, monkeypatch), \
                patch.object(cpe, "db", fake_async_db), \
                patch("services.email.send_registration_confirmation", AsyncMock(return_value=False)), \
                patch("services.task_queue.task_queue.send_registration_email", fila):
            await cpe.deliver_registration_email(
                "cli@x.pt", "Maria", client_id=None, company_id="cmp-domus", frontend_url=FRONTEND,
            )
        k = fila.await_args.kwargs
        assert k["company_id"] == "cmp-domus"
        assert k["portal_url"] == PORTAL

    async def test_o_handler_do_worker_repassa_o_contexto(self):
        from worker.tasks import send_registration_email_task

        entrega = AsyncMock(return_value=True)
        with patch("services.client_portal_email.deliver_registration_email", entrega):
            await send_registration_email_task(
                {}, client_email="a@b.pt", client_name="X", company_id="cmp-domus", portal_url=PORTAL,
            )
        k = entrega.await_args.kwargs
        assert k["company_id"] == "cmp-domus" and k["portal_url"] == PORTAL

    async def test_a_fila_so_leva_o_contexto_quando_existe(self):
        from services.task_queue import TaskQueueService as TaskQueue

        enfileira = AsyncMock(return_value="j")
        fila = TaskQueue.__new__(TaskQueue)
        with patch.object(TaskQueue, "enqueue", enfileira):
            await fila.send_registration_email("a@b.pt", "X", "123", company_id="cmp-domus", portal_url=PORTAL)
            await fila.send_registration_email("a@b.pt", "X")
        com, sem = enfileira.await_args_list
        assert com.kwargs["company_id"] == "cmp-domus" and com.kwargs["portal_url"] == PORTAL
        assert "company_id" not in sem.kwargs and "portal_url" not in sem.kwargs


# ═════════════════════════════════════════════════════════════════════
# 4. O send_email REAL (parâmetros que saem para o SMTP)
# ═════════════════════════════════════════════════════════════════════


def _decodificada(bruta: str) -> str:
    """Cabeçalhos + corpos DESCODIFICADOS: o corpo vai em base64 e um `in` sobre
    o texto cru passaria sempre que o que se procura NÃO devia estar lá."""
    import email as _email

    m = _email.message_from_string(bruta)
    partes = [f"{k}: {v}" for k, v in m.items()]
    for parte in m.walk():
        carga = parte.get_payload(decode=True)
        if carga:
            partes.append(carga.decode("utf-8", "replace"))
    return "\n".join(partes)


class TestSendEmailReal:
    async def _enviar(self, account, *, global_from_name="Power Real Estate", **kw):
        import services.email_service as es

        smtp = MagicMock()
        smtp.__enter__.return_value = smtp
        config = SimpleNamespace(system_smtp=SimpleNamespace(
            smtp_from_name=global_from_name, email_signature="<p>ASSINATURA-DA-POWER</p>",
        ))
        with patch.object(es.smtplib, "SMTP_SSL", return_value=smtp), \
                patch("services.system_config.get_system_config", AsyncMock(return_value=config)), \
                patch.object(es, "resolve_email_signature", wraps=es.resolve_email_signature) as assinatura:
            r = await es.send_email(
                account_name="x", to_emails=["cli@x.pt"], subject="Assunto",
                body="corpo", body_html="<p>corpo</p>", account_override=account, **kw,
            )
        bruta = smtp.sendmail.call_args.args[2] if smtp.sendmail.called else ""
        return r, _decodificada(bruta), assinatura

    def _conta(self, nome):
        from services.email_service import EmailAccount

        return EmailAccount(nome, "imap.x.pt", 993, "smtp.x.pt", 465, "geral@domus.pt", "pw")

    async def test_o_nome_pedido_vai_no_from_de_qualquer_conta(self):
        r, msg, _ = await self._enviar(self._conta("caixa_geral_da_rede"), from_name_override="Domus")
        assert r["success"] is True
        assert "From: Domus <geral@domus.pt>" in msg

    async def test_acentos_no_nome_sao_codificados(self):
        r, msg, _ = await self._enviar(self._conta("caixa_geral_da_rede"), from_name_override="Crédito Ç")
        assert r["success"] is True
        assert "=?utf-8?" in msg.split("From:")[1].split("\n")[0].lower()

    async def test_o_nome_pedido_vence_o_nome_global_do_sistema(self):
        _, msg, _ = await self._enviar(
            self._conta("system_smtp"), from_name_override="Domus", use_system_signature=False,
        )
        assert "Domus <geral@domus.pt>" in msg
        assert "Power Real Estate" not in msg.split("Subject:")[0]

    async def test_sem_nome_pedido_o_comportamento_global_mantem_se(self):
        _, msg, _ = await self._enviar(self._conta("system_smtp"))
        assert "Power Real Estate <geral@domus.pt>" in msg
        assert "ASSINATURA-DA-POWER" in msg

    async def test_a_assinatura_global_do_sistema_nao_sai_na_rede_alheia(self):
        _, msg, _ = await self._enviar(
            self._conta("system_smtp"), from_name_override="Domus", use_system_signature=False,
        )
        assert "ASSINATURA-DA-POWER" not in msg


# ═════════════════════════════════════════════════════════════════════
# 5. OS TRÊS PONTOS DE ENTRADA REAIS (a ligação, não só o motor)
# ═════════════════════════════════════════════════════════════════════
#
# Os testes acima provam o motor. Faltava provar que cada fluxo o USA: um
# motor correcto que ninguém chama é exactamente o defeito de partida (o
# template tinha `company_name` e `portal_url` desde o Pacote 12 e nenhum
# chamador os passava).


@pytest.fixture
def registo_publico(fake_async_db, monkeypatch):
    """O registo público a sério, a recolher as tarefas de fundo e os envios."""
    import services.client_uniqueness as cu
    import services.form_config_scope as fcs
    import services.portal_email_context as ctx_mod
    import services.public_registration as pr
    from tests.unit.helpers_tenant import semear

    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
    monkeypatch.setenv("FRONTEND_URL", FRONTEND)
    semear(fake_async_db)
    _base_config(fake_async_db)

    tarefas: list = []
    envios: list = []

    def _recolher(coro, name="", **_k):
        tarefas.append(coro)

    async def _capturar(contexto, **kw):
        envios.append({"contexto": contexto, **kw})
        return {"success": True}

    s3 = MagicMock()
    s3.initialize_client_folders = MagicMock(return_value=(True, "Documentação Clientes/x"))
    import services.email_delivery_status as eds

    with tenant_db(fake_async_db, pr, cu, fcs, ctx_mod), \
            patch.object(pr, "s3_service", s3), \
            patch.object(pr, "spawn_background_task", _recolher), \
            patch.object(pr, "notify_new_client_registration", AsyncMock()), \
            patch.object(pr, "gestao_da_rede_do_processo", AsyncMock(return_value=[])), \
            patch.object(pr, "send_new_client_notification", AsyncMock()), \
            patch("services.push_notifications.send_push_notification", AsyncMock()), \
            patch("services.portal_documents_notify.generate_mandatory_document_requests", AsyncMock()), \
            patch("asyncio.create_task", lambda c, **k: c.close()), \
            patch("services.client_portal_email.db", fake_async_db), \
            patch.object(eds, "begin_portal_email_task", AsyncMock(return_value="t")), \
            patch.object(eds, "complete_portal_email_task", AsyncMock()), \
            patch.object(eds, "fail_portal_email_task", AsyncMock()), \
            patch.object(eds, "mark_portal_email_retry_scheduled", AsyncMock()), \
            patch("services.portal_email_context.enviar_email_do_portal", _capturar):
        yield SimpleNamespace(pr=pr, bd=fake_async_db, tarefas=tarefas, envios=envios)


def _base_config(fake):
    fake.system_config.docs.append({"_id": "main", "email": dict(CAIXA_POWER), "settings": {}})
    fake.system_config.docs.append({"_id": "company:cmp-domus", "email": dict(CAIXA_DOMUS)})


class TestRegistoPublico:
    async def _registar(self, mundo, **extra):
        from models.process import PublicClientRegistration

        dados = PublicClientRegistration(
            name="Maria Teste", email="maria@teste.pt", phone="912345678",
            process_type="credito_habitacao", **extra,
        )
        pedido = MagicMock(headers={"origin": "https://crm.domus.pt"}, state=MagicMock(spec=[]))
        resposta = await mundo.pr.run_public_client_registration(pedido, dados)
        for coro in mundo.tarefas:
            await coro
        return resposta

    async def test_os_dois_emails_saem_em_nome_da_domus_com_o_link(self, registo_publico):
        r = await self._registar(registo_publico, empresa_id="cmp-domus")
        assert r.status_code == 200 or getattr(r, "body", None) is not None
        envios = registo_publico.envios
        assert len(envios) == 2, "convite do Portal + confirmação do registo"
        for e in envios:
            ctx = e["contexto"]
            assert ctx.company_name == "Domus" and ctx.network_id == REDE_DOMUS
            assert ctx.account.email == "geral@domus.pt"
            texto = f'{e["subject"]}\n{e["body"]}\n{e["body_html"]}'
            assert "Power" not in texto and "Precision" not in texto
            assert "precisioncredito" not in texto.lower()
            assert "Domus" in texto
        # O link mágico (…/portal/<short_id>) está no corpo dos dois, no domínio do browser.
        for e in envios:
            assert "https://crm.domus.pt/portal/" in e["body_html"]
            assert "https://crm.domus.pt/portal/" in e["body"]

    async def test_o_convite_aponta_para_a_pagina_de_entrada_real(self, registo_publico):
        await self._registar(registo_publico, empresa_id="cmp-domus")
        convite = next(e for e in registo_publico.envios if "Bem-vindo" in e["subject"])
        assert "https://crm.domus.pt/portal" in convite["body_html"]
        assert "www.precisioncredito.pt" not in convite["body_html"]

    async def test_sem_link_de_empresa_usa_a_rede_de_omissao(self, registo_publico):
        """Os links antigos (sem `?empresa=`) continuam a ser da rede de omissão."""
        await self._registar(registo_publico)
        for e in registo_publico.envios:
            assert e["contexto"].network_id == REDE_INCUMBENTE
            assert e["contexto"].account.email == "geral@powerealestate.pt"


class TestFluxosDoStaff:
    async def test_o_cliente_criado_pelo_staff_envia_com_a_empresa_e_o_dominio(self):
        """`run_create_client` passa o domínio e o utilizador ao envio de fundo."""
        import services.client_crud as cc

        assert "frontend_url" in cc.run_create_client.__code__.co_varnames[: cc.run_create_client.__code__.co_argcount + cc.run_create_client.__code__.co_kwonlyargcount]
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        codigo = codigo_da_funcao_sem_comentarios(cc.run_create_client)
        assert "frontend_url=frontend_url" in codigo and "user=user" in codigo

    async def test_a_rota_de_criar_cliente_passa_o_dominio_de_quem_trabalha(self):
        import routes.clients as rc
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        codigo = codigo_da_funcao_sem_comentarios(rc.create_client)
        assert "get_frontend_url(request)" in codigo
        assert "request" in rc.create_client.__code__.co_varnames[:3]

    async def test_o_processo_criado_pelo_staff_envia_com_a_empresa_do_processo(self):
        import routes.processes as rp
        import services.process_create as pc
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        corpo = codigo_da_funcao_sem_comentarios(pc.persist_and_finalize_staff_create)
        assert "company_id=process_doc.get('company_id')" in corpo
        assert "frontend_url=frontend_url" in corpo
        rota = codigo_da_funcao_sem_comentarios(rp.create_client_process)
        assert "frontend_url=get_frontend_url(request)" in rota

    async def test_o_envio_de_fundo_do_processo_repassa_empresa_e_dominio(self):
        import services.process_create as pc

        entrega = AsyncMock(return_value=True)
        with patch.object(pc, "db", MagicMock(clients=MagicMock(find_one=AsyncMock(return_value={
                "portal_access_code": "1"})))), \
                patch("services.client_portal_email.deliver_registration_email", entrega):
            await pc.send_portal_welcome_email_from_process(
                client_id="c1", client_email="a@b.pt", client_name="X",
                company_id="cmp-domus", frontend_url=FRONTEND, user={"id": "u"},
            )
        k = entrega.await_args.kwargs
        assert k["company_id"] == "cmp-domus" and k["frontend_url"] == FRONTEND


class TestLinkMagicoEnviadoPeloStaff:
    async def test_o_email_do_link_e_da_empresa_do_processo(self, fake_async_db, monkeypatch):
        import services.portal_email_context as ctx_mod
        import services.portal_magic_link as pml

        monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
        _base(fake_async_db, domus_email=CAIXA_DOMUS)
        envio = AsyncMock(return_value={"success": True})
        processo = {
            "client_email": "cli@x.pt", "client_name": "Maria", "client_id": "c1",
            "company_id": "cmp-domus", "network_id": REDE_DOMUS,
        }
        with tenant_db(fake_async_db, ctx_mod), \
                patch.object(pml, "ensure_portal_access_code", AsyncMock(return_value="654321")), \
                patch.object(pml, "issue_portal_magic_link", AsyncMock(return_value={
                    "magic_link": "https://crm.domus.pt/portal/ABC12345", "short_id": "ABC12345",
                    "frontend_url": "https://crm.domus.pt"})), \
                patch("services.history.log_history", AsyncMock()), \
                patch("services.portal_email_context.enviar_email_do_portal", envio):
            await pml.send_magic_link_to_client(
                process_id="p1", process=processo, user={"id": "u", "email": "a@b.pt"},
                request=MagicMock(),
            )
        k = envio.await_args.kwargs
        assert envio.await_args.args[0].company_name == "Domus"
        texto = f'{k["body"]}\n{k["body_html"]}'
        assert "Power" not in texto and "Precision" not in texto
        assert "precisioncredito" not in texto.lower()
        assert "https://crm.domus.pt/portal/ABC12345" in texto
        assert "https://crm.domus.pt/portal" in texto
        assert "Domus · Crédito Habitação" in k["body_html"]


# ═════════════════════════════════════════════════════════════════════
# 6. A GUARDA: nenhuma marca nem conta fixa nos módulos deste email
# ═════════════════════════════════════════════════════════════════════


class TestSemMarcaFixa:
    MODULOS = [
        "services.email", "services.portal_magic_link", "services.public_registration",
        "services.client_portal_email", "services.portal_email_context",
    ]

    def _fonte(self, nome):
        import importlib

        from tests.unit.helpers_fonte import codigo_sem_comentarios

        return codigo_sem_comentarios(open(importlib.import_module(nome).__file__, encoding="utf-8").read())

    @pytest.mark.parametrize("modulo", ["services.portal_magic_link", "services.public_registration",
                                        "services.client_portal_email", "services.portal_email_context"])
    async def test_nao_ha_nome_de_empresa_nem_dominio_nem_conta_no_codigo(self, modulo):
        codigo = self._fonte(modulo)
        for proibido in ("Power Precision", "Power Real Estate", "precisioncredito", 'account_name="power"'):
            assert proibido not in codigo, f"{modulo}: «{proibido}» fixo no código"

    async def test_o_email_de_confirmacao_nao_envia_pela_conta_power(self):
        import services.email as email_mod
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        codigo = codigo_da_funcao_sem_comentarios(email_mod.send_registration_confirmation)
        assert 'account_name="power"' not in codigo
        assert "enviar_email_do_portal" in codigo

    async def test_contraprova_o_leitor_le_mesmo_o_modulo(self):
        assert "enviar_email_do_portal" in self._fonte("services.public_registration")
        assert "ContextoDoEmailDoPortal" in self._fonte("services.portal_email_context")


# ═════════════════════════════════════════════════════════════════════
# 7. A MARCA ESTRITA (sem recurso global)
# ═════════════════════════════════════════════════════════════════════


class TestMarcaEstrita:
    async def _marca(self, fake, company_id):
        from services.email_branding import resolve_company_branding_strict

        with patch("database.db", fake):
            return await resolve_company_branding_strict(company_id)

    async def test_a_copia_herdada_da_global_nao_conta_como_marca_da_empresa(self, fake_async_db):
        fake_async_db.companies.docs.append({"id": "cmp-x", "network_id": "rede:x"})  # sem nome nem logo
        fake_async_db.system_config.docs.extend([
            {"_id": "main", "settings": {"company_name": "Power Real Estate", "logo_url": "https://l/power.png"}},
            {"_id": "company:cmp-x", "settings": {"company_name": "Power Real Estate", "logo_url": "https://l/power.png"}},
        ])
        assert await self._marca(fake_async_db, "cmp-x") == (None, None)

    async def test_a_marca_propria_da_empresa_conta(self, fake_async_db):
        fake_async_db.companies.docs.append({"id": "cmp-x", "network_id": "rede:x"})
        fake_async_db.system_config.docs.extend([
            {"_id": "main", "settings": {"company_name": "Power Real Estate", "logo_url": "https://l/power.png"}},
            {"_id": "company:cmp-x", "settings": {"company_name": "Empresa X", "logo_url": "https://l/x.png"}},
        ])
        assert await self._marca(fake_async_db, "cmp-x") == ("Empresa X", "https://l/x.png")

    async def test_sem_empresa_nao_ha_recurso_global(self, fake_async_db):
        fake_async_db.system_config.docs.append(
            {"_id": "main", "settings": {"company_name": "Power Real Estate"}}
        )
        assert await self._marca(fake_async_db, None) == (None, None)
        assert await self._marca(fake_async_db, "inexistente") == (None, None)
