"""O email que o CRM envia e o que a sincronização traz dos «Enviados» são UM só (QA-6).

Os duplicados («Enviado via personal» + «User webmail sync») nasciam de uma comparação
estrita demais: a empresa e o endereço tinham de ser iguais letra a letra, e o Message-ID
tinha de sobreviver ao servidor SMTP.
"""
from datetime import datetime, timedelta, timezone

import pytest

from services import email_service

UTIL = "user-1"
CAIXA = "ana@power.pt"


def _enviado(**extra):
    agora = datetime.now(timezone.utc)
    doc = {
        "id": "e1", "direction": "sent", "folder": "Sent", "synced": False,
        "synced_for_user": UTIL, "account": CAIXA, "message_id": "<nosso@power.pt>",
        "subject": "Documentos", "to_emails": ["cliente@x.pt"],
        "sent_at": agora.isoformat(), "created_at": agora.isoformat(),
    }
    doc.update(extra)
    return doc


async def _tenho(db, **kw):
    base = dict(
        msg_id="<nosso@power.pt>", user_id=UTIL, company_id=None, mailbox_addr=CAIXA,
        conta_original="Ana@Power.pt", assunto="", destinatarios=[], sent_at=None,
    )
    base.update(kw)
    return await email_service._ja_tenho_este_email(db, **base)


@pytest.mark.asyncio
async def test_o_mesmo_message_id_e_o_mesmo_email(fake_async_db):
    await fake_async_db.emails.insert_one(_enviado())
    assert await _tenho(fake_async_db) is True


@pytest.mark.asyncio
async def test_a_empresa_so_conta_quando_o_documento_a_tem(fake_async_db):
    # O envio do CRM sem empresa na sessão não leva `company_id`; a sincronização conhece a da config.
    await fake_async_db.emails.insert_one(_enviado())
    assert await _tenho(fake_async_db, company_id="power-id") is True


@pytest.mark.asyncio
async def test_empresa_diferente_no_documento_e_outro_email(fake_async_db):
    await fake_async_db.emails.insert_one(_enviado(company_id="domus-id"))
    assert await _tenho(fake_async_db, company_id="power-id") is False


@pytest.mark.asyncio
async def test_outra_caixa_do_mesmo_utilizador_nao_e_duplicado(fake_async_db):
    await fake_async_db.emails.insert_one(_enviado(account="ana@domus.pt"))
    assert await _tenho(fake_async_db) is False


@pytest.mark.asyncio
async def test_documento_antigo_com_o_endereco_em_maiusculas(fake_async_db):
    await fake_async_db.emails.insert_one(_enviado(account="Ana@Power.pt"))
    assert await _tenho(fake_async_db) is True


@pytest.mark.asyncio
async def test_servidor_que_reescreve_o_message_id_nao_duplica(fake_async_db):
    await fake_async_db.emails.insert_one(_enviado())
    agora = datetime.now(timezone.utc) + timedelta(minutes=2)
    assert await _tenho(
        fake_async_db, msg_id="<reescrito@servidor>", assunto="Documentos",
        destinatarios=["Cliente@X.pt"], sent_at=agora.isoformat(),
    ) is True
    # Aprendeu o id do servidor: a passagem seguinte acha-o logo pelo Message-ID.
    assert await _tenho(fake_async_db, msg_id="<reescrito@servidor>") is True


@pytest.mark.asyncio
async def test_mesmo_assunto_a_outros_destinatarios_ou_muito_depois_nao_e_o_mesmo(fake_async_db):
    await fake_async_db.emails.insert_one(_enviado())
    agora = datetime.now(timezone.utc)
    assert await _tenho(
        fake_async_db, msg_id="<outro@s>", assunto="Documentos",
        destinatarios=["outro@x.pt"], sent_at=agora.isoformat(),
    ) is False
    assert await _tenho(
        fake_async_db, msg_id="<outro2@s>", assunto="Documentos",
        destinatarios=["cliente@x.pt"], sent_at=(agora + timedelta(hours=3)).isoformat(),
    ) is False


@pytest.mark.asyncio
async def test_o_recebido_nunca_cai_na_via_do_envio_proprio(fake_async_db):
    await fake_async_db.emails.insert_one(_enviado())
    assert await _tenho(fake_async_db, msg_id="<recebido@s>") is False
