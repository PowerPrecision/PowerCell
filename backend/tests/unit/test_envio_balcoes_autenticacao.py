"""«535 Incorrect authentication data» no envio para balcões (Bloco 5, ponto 34).

A causa que se consegue provar sem acesso ao servidor de email: o sincronizador
automático (10 em 10 minutos) continuava a fazer login IMAP, para sempre, em
contas cuja password tinha sido recusada — e o servidor passa a bloquear a conta,
respondendo `535 Incorrect authentication data` também ao SMTP do ENVIO, mesmo
com a password certa. Daqui sai o recuo; o resto torna a falha diagnosticável.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from services import mailbox_backoff as backoff
from services import user_email_config_service as ucs

AGORA = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


def iso(horas_atras=0.0):
    return (AGORA - timedelta(hours=horas_atras)).isoformat()


def config(**kw):
    base = {"sync_error_class": "autenticacao", "sync_failures": 3,
            "last_sync_attempt_at": iso(0.5), "updated_at": iso(48)}
    base.update(kw)
    return base


# ── o recuo (puro) ─────────────────────────────────────────────────────────

def test_uma_falha_isolada_de_autenticacao_nao_recua():
    assert backoff.deve_esperar(config(sync_failures=1), AGORA) is False


@pytest.mark.parametrize(
    "falhas,horas_desde_a_ultima,espera",
    [
        (2, 0.5, True), (2, 1.5, False),
        (3, 5, True), (3, 7, False),
        (4, 23, True), (4, 25, False),
        (50, 23, True), (50, 25, False),  # o teto é 24 h, nunca «para sempre»
    ],
)
def test_o_intervalo_cresce_com_as_falhas_e_tem_teto(falhas, horas_desde_a_ultima, espera):
    c = config(sync_failures=falhas, last_sync_attempt_at=iso(horas_desde_a_ultima))
    assert backoff.deve_esperar(c, AGORA) is espera


@pytest.mark.parametrize("classe", ["rede", "limite", "desconhecida", None])
def test_so_a_autenticacao_recua(classe):
    assert backoff.deve_esperar(config(sync_error_class=classe), AGORA) is False


def test_a_password_nova_vence_o_recuo():
    """Corrigir a password não pode deixar a caixa parada até ao fim do intervalo."""
    c = config(last_sync_attempt_at=iso(0.5), updated_at=iso(0.1))
    assert backoff.deve_esperar(c, AGORA) is False


def test_uma_alteracao_ANTERIOR_a_ultima_falha_nao_levanta_o_recuo():
    c = config(last_sync_attempt_at=iso(0.5), updated_at=iso(3))
    assert backoff.deve_esperar(c, AGORA) is True


@pytest.mark.parametrize(
    "campos",
    [
        {"last_sync_attempt_at": None},
        {"last_sync_attempt_at": "ontem"},
        {"sync_failures": "muitas"},
        {"sync_failures": None},
    ],
)
def test_dados_ilegiveis_nunca_param_a_sincronizacao(campos):
    assert backoff.deve_esperar(config(**campos), AGORA) is False


def test_documento_vazio_nao_levanta():
    assert backoff.deve_esperar({}, AGORA) is False
    assert backoff.deve_esperar(None, AGORA) is False


def test_aceita_datas_com_Z_e_sem_fuso():
    c = config(last_sync_attempt_at=(AGORA - timedelta(minutes=10)).replace(tzinfo=None).isoformat() + "Z")
    assert backoff.deve_esperar(c, AGORA) is True
    c = config(last_sync_attempt_at=(AGORA - timedelta(minutes=10)).replace(tzinfo=None).isoformat())
    assert backoff.deve_esperar(c, AGORA) is True


# ── ligado ao selector das contas a sincronizar ────────────────────────────

@pytest.fixture
def bd(fake_async_db):
    with patch.object(ucs, "db", fake_async_db):
        fake_async_db.users.docs.append({"id": "u1", "email": "a@x.pt", "is_active": True})
        fake_async_db.users.docs.append({"id": "u2", "email": "b@x.pt", "is_active": True})
        yield fake_async_db


def conta(id_, user_id, **kw):
    return {"id": id_, "user_id": user_id, "company_id": "c1", "email_address": f"{id_}@x.pt",
            "is_configured": True, "encrypted_password": "ENC:x", "auth_method": "imap_smtp", **kw}


@pytest.mark.asyncio
async def test_a_conta_com_autenticacao_recusada_fica_fora_do_ciclo_automatico(bd):
    agora = datetime.now(timezone.utc)
    bd.user_email_configs.docs += [
        conta("boa", "u1"),
        conta("recusada", "u2", sync_error_class="autenticacao", sync_failures=5,
              last_sync_attempt_at=(agora - timedelta(minutes=10)).isoformat(),
              updated_at=(agora - timedelta(days=3)).isoformat()),
    ]
    ids = {c["id"] for c in await ucs.get_active_email_configs_for_sync()}
    assert ids == {"boa"}


@pytest.mark.asyncio
async def test_a_conta_volta_ao_ciclo_quando_a_configuracao_muda(bd):
    agora = datetime.now(timezone.utc)
    bd.user_email_configs.docs.append(
        conta("recusada", "u2", sync_error_class="autenticacao", sync_failures=5,
              last_sync_attempt_at=(agora - timedelta(minutes=10)).isoformat(),
              updated_at=(agora - timedelta(minutes=1)).isoformat())
    )
    assert {c["id"] for c in await ucs.get_active_email_configs_for_sync()} == {"recusada"}


@pytest.mark.asyncio
async def test_o_recuo_pode_ser_desligado_para_quem_precisa_de_todas(bd):
    agora = datetime.now(timezone.utc)
    bd.user_email_configs.docs.append(
        conta("recusada", "u2", sync_error_class="autenticacao", sync_failures=5,
              last_sync_attempt_at=(agora - timedelta(minutes=10)).isoformat(),
              updated_at=(agora - timedelta(days=3)).isoformat())
    )
    todas = await ucs.get_active_email_configs_for_sync(respeitar_recuo=False)
    assert {c["id"] for c in todas} == {"recusada"}


# ── a falha de envio diz qual conta recusou ────────────────────────────────

def test_a_mensagem_de_falha_de_autenticacao_nomeia_a_conta_e_a_origem_do_perfil():
    from services.email_documentation import descrever_falha_de_envio

    conta_ = SimpleNamespace(email="ana@precision.pt")
    msg = descrever_falha_de_envio({"error": "Falha de autenticação SMTP.", "error_code": "smtp_auth"}, conta_, "profile:user")
    assert "ana@precision.pt" in msg and "do seu perfil" in msg and "Perfil → Configuração de Webmail" in msg


@pytest.mark.parametrize("origem", ["caixa_geral", "system_config:default", "global:power"])
def test_a_mensagem_distingue_a_caixa_geral_do_perfil(origem):
    from services.email_documentation import descrever_falha_de_envio

    msg = descrever_falha_de_envio({"error": "x", "error_code": "smtp_auth"}, SimpleNamespace(email="geral@x.pt"), origem)
    assert "da Caixa Geral da empresa" in msg and "administrador" in msg and "do seu perfil" not in msg


def test_outras_falhas_nao_ganham_o_sufixo_de_credenciais():
    from services.email_documentation import descrever_falha_de_envio

    assert descrever_falha_de_envio({"error": "Não foi possível enviar o email."}, SimpleNamespace(email="a@b.c"), "profile:user") == "Não foi possível enviar o email."


@pytest.mark.asyncio
async def test_send_email_devolve_o_codigo_e_a_conta_numa_recusa_535():
    import smtplib

    from services import email_service as es

    conta_ = es.EmailAccount(name="personal", imap_server="h", imap_port=993, smtp_server="h",
                             smtp_port=465, email="ana@precision.pt", password="segredo")

    class SMTPQueRecusa:
        def __init__(self, *a, **k): ...
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def login(self, *a): raise smtplib.SMTPAuthenticationError(535, b"Incorrect authentication data")

    with patch.object(es.smtplib, "SMTP_SSL", SMTPQueRecusa):
        r = await es.send_email(account_name="personal", to_emails=["b@x.pt"], subject="s", body="b", account_override=conta_)
    assert r["success"] is False
    assert r["error_code"] == "smtp_auth"
    assert r["account_email"] == "ana@precision.pt"
    assert "segredo" not in str(r)


@pytest.mark.asyncio
async def test_password_ilegivel_nao_e_descrita_como_credenciais_recusadas():
    from services import email_service as es

    conta_ = es.EmailAccount(name="personal", imap_server="h", imap_port=993, smtp_server="h",
                             smtp_port=465, email="ana@precision.pt", password="ENC:lixo")
    with patch("services.email_config_resolver.decrypt_email_secret", return_value=""):
        r = await es.send_email(account_name="personal", to_emails=["b@x.pt"], subject="s", body="b", account_override=conta_)
    assert r["success"] is False
    assert r["error_code"] == "smtp_password_unreadable"
    assert "ana@precision.pt" in r["error"]


# ── password gravada sem quebras de linha ──────────────────────────────────

@pytest.mark.parametrize("entrada,esperado", [("abc\r\n", "abc"), ("abc\n", "abc"), ("\nabc", "abc"), (" abc ", " abc "), ("a b", "a b"), (None, None)])
def test_a_password_perde_as_quebras_de_linha_e_so_essas(entrada, esperado):
    from models.email_config import EmailConfigCreate

    assert EmailConfigCreate(email_address="a@b.pt", password=entrada).password == esperado


# ── Caixa Geral por falta do perfil: fica no log ───────────────────────────

@pytest.mark.asyncio
async def test_perfil_ilegivel_que_cai_na_caixa_geral_deixa_o_motivo_no_log(caplog):
    from services import email_config_resolver as r

    resolvido = {"email_address": "ana@x.pt", "smtp_server": "h", "encrypted_password": "ENC:x", "config_source": "user"}
    caixa = {"password": "pw", "smtp_server": "h", "email_address": "geral@x.pt", "source": "system_config:default"}
    with patch.object(r, "resolve_email_config_for_sync", AsyncMock(return_value=resolvido)), \
         patch.object(r, "resolve_active_ucr_role", AsyncMock(return_value="consultor")), \
         patch.object(r, "decrypt_email_secret", return_value=""), \
         patch.object(r, "load_caixa_geral_config", AsyncMock(return_value=caixa)):
        with caplog.at_level("WARNING"):
            conta_, origem = await r.resolve_sending_account(None, {"id": "u1"}, "c1")
    assert conta_.email == "geral@x.pt" and origem == "system_config:default"
    assert any("perfil não é utilizável" in m and "ilegível" in m for m in caplog.messages)
