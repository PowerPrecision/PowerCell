"""A assinatura vai no corpo do email enviado — contra um MongoDB REAL (Lote 7.2, Out 2026).

O relato: «o construtor do email não está a injetar a assinatura do utilizador nem da empresa». O código
injectava (`send_email` → `resolve_email_signature`), mas a resolução só sabia procurar o UCR pelo
`company_id` EXACTO — e o projecto tem duas notações para a empresa: o ID (`X-Company-Id`) e o NOME
(`users.company`, e o que `get_active_company_id_async` devolve quando o cabeçalho falta). Com o nome, a
procura não encontrava o UCR e o email saía sem assinatura, sem erro nenhum. O `_find_ucr` do `auth`
sempre casou pelos dois; a assinatura ficou de fora (a mesma divergência de «dois leitores do mesmo dado»).
"""
from __future__ import annotations

import email as _email
import os
import uuid
from unittest.mock import patch

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from services import email_service

pytestmark = pytest.mark.asyncio

SIG_POWER = "<p>Ana Martins — Power Real Estate</p>"
SIG_PRECISION = "<p>Ana Martins — Precision</p>"
SIG_GLOBAL = "<p>Ana (global)</p>"


@pytest_asyncio.fixture
async def bd():
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_sig72_{uuid.uuid4().hex[:8]}"]
    # Dados REAIS: `users.company` é o NOME; o UCR tem o ID e o NOME.
    await base.users.insert_many([
        {"id": "u-ana", "name": "Ana", "company": "Power Real Estate", "email_signature": None},
        {"id": "u-rui", "name": "Rui", "company": "Power Real Estate", "email_signature": SIG_GLOBAL},
    ])
    await base.user_company_roles.insert_many([
        {"user_id": "u-ana", "company_id": "cmp-power", "company_name": "Power Real Estate", "signature": SIG_POWER},
        {"user_id": "u-ana", "company_id": "cmp-prec", "company_name": "Precision", "signature": SIG_PRECISION},
        {"user_id": "u-rui", "company_id": "cmp-power", "company_name": "Power Real Estate", "signature": None},
    ])
    with patch.object(email_service, "db", base):
        yield base
    await cliente.drop_database(base.name)
    cliente.close()


async def _resolver(utilizador, empresa):
    return await email_service.resolve_email_signature(created_by=utilizador, active_company_id=empresa)


class TestAExploracao:
    async def test_a_empresa_activa_pelo_NOME_encontra_a_assinatura(self, bd):
        """O ataque: o cabeçalho falta e a empresa activa chega como NOME — antes: sem assinatura."""
        assinatura, origem = await _resolver("u-ana", "Power Real Estate")
        assert assinatura == SIG_POWER
        assert origem.startswith("ucr_active")

    async def test_o_nome_nao_distingue_maiusculas(self, bd):
        assinatura, _ = await _resolver("u-ana", "precision")
        assert assinatura == SIG_PRECISION

    async def test_sem_empresa_activa_a_empresa_por_omissao_e_um_NOME(self, bd):
        """`users.company` é o nome: a procura por `company_id == users.company` nunca casava."""
        assinatura, origem = await _resolver("u-ana", None)
        assert assinatura == SIG_POWER
        assert origem.startswith("ucr_default")

    async def test_o_sentinel_default_equivale_a_sem_empresa(self, bd):
        assinatura, _ = await _resolver("u-ana", "default")
        assert assinatura == SIG_POWER


class TestContraprovas:
    async def test_pelo_ID_continua_a_funcionar(self, bd):
        assert (await _resolver("u-ana", "cmp-prec"))[0] == SIG_PRECISION

    async def test_empresa_alheia_nao_empresta_a_assinatura_de_outra(self, bd):
        """Rui só tem a assinatura global; numa empresa onde não tem UCR vale a global (é a única dele)."""
        assert (await _resolver("u-rui", "cmp-prec"))[0] == SIG_GLOBAL

    async def test_um_nome_que_nao_e_do_utilizador_nao_devolve_a_assinatura_de_outra_empresa(self, bd):
        assinatura, origem = await _resolver("u-ana", "Domus")
        assert assinatura is None and origem == "none"

    async def test_quem_nao_tem_assinatura_nenhuma_envia_sem(self, bd):
        await bd.user_company_roles.update_many({"user_id": "u-ana"}, {"$set": {"signature": None}})
        assert (await _resolver("u-ana", "Power Real Estate")) == (None, "none")

    async def test_o_nome_nao_e_interpretado_como_expressao_regular(self, bd):
        assert (await _resolver("u-ana", ".*"))[0] is None


class TestONoCorpoDoEmailQueSai:
    async def test_o_email_real_leva_a_assinatura_da_empresa_pelo_nome(self, bd, monkeypatch):
        """Ponta a ponta com o `send_email` REAL e o SMTP falseado ao nível da chamada."""
        enviadas = []

        class SMTP:
            def __init__(self, *a, **k): ...
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def login(self, *a, **k): ...
            def sendmail(self, de, para, raw, *a, **k): enviadas.append(raw)

        monkeypatch.setenv("IMAP_APPEND_ENABLED", "false")
        conta = email_service.EmailAccount(
            name="personal", imap_server="i", imap_port=993, smtp_server="s", smtp_port=465,
            email="ana@x.pt", password="p",
        )
        with patch.object(email_service.smtplib, "SMTP_SSL", SMTP):
            r = await email_service.send_email(
                account_name="personal", to_emails=["c@x.pt"], subject="Assunto", body="Olá",
                body_html="<p>Olá</p>", created_by="u-ana", active_company_id="Power Real Estate",
                account_override=conta,
            )
        assert r["success"] is True
        msg = _email.message_from_string(enviadas[0])
        partes = {p.get_content_type(): p.get_payload(decode=True).decode() for p in msg.walk() if not p.is_multipart()}
        assert "Ana Martins — Power Real Estate" in partes["text/html"]
        assert "Ana Martins — Power Real Estate" in partes["text/plain"]
