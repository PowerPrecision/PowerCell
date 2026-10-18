"""A conta de email de uma empresa não aparece noutra (QA-6, 18 Out 2026).

O Master, com a Precision escolhida, via a conta da Power no cartão de email e o envio de
teste saía com as credenciais da Power. Causa: sem config própria da empresa pedida, o
resolvedor recuava para a config genérica («default» / por cargo / «o primeiro dict com
email», incluindo `company:<outra>`) — que, para quem tem acesso a várias empresas, é a da
empresa de origem.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from services import email_config_resolver as resolver

POWER, PRECISION, DOMUS = "emp-power", "emp-precision", "emp-domus"


def _cfg(email):
    return {
        "email_address": email, "imap_server": "imap.x.pt", "imap_port": 993,
        "smtp_server": "smtp.x.pt", "smtp_port": 465, "is_configured": True,
        "encrypted_password": "segredo",
    }


async def _mundo(db, *, email_config, ucrs=(POWER, PRECISION, DOMUS), casa="Power Real Estate"):
    await db.users.insert_one({
        "id": "u1", "role": "master", "company": casa, "email_config": email_config,
    })
    for cid, nome in ((POWER, "Power Real Estate"), (PRECISION, "Precision Crédito"), (DOMUS, "Domus")):
        await db.companies.insert_one({"id": cid, "name": nome})
    for cid in ucrs:
        await db.user_company_roles.insert_one({
            "user_id": "u1", "company_id": cid, "role": "admin", "is_active": True,
        })


@pytest.mark.asyncio
class TestOResolvedorNaoAtravessaEmpresas:
    async def test_a_empresa_sem_config_propria_nao_recebe_a_da_casa(self, fake_async_db):
        await _mundo(fake_async_db, email_config={"default": _cfg("master@power.pt")})
        with patch.object(resolver, "db", fake_async_db):
            precision = await resolver.resolve_email_config_for_sync("u1", "admin", PRECISION)
            domus = await resolver.resolve_email_config_for_sync("u1", "admin", DOMUS)
        assert precision is None
        assert domus is None

    async def test_a_empresa_de_origem_continua_a_usar_a_config_generica(self, fake_async_db):
        await _mundo(fake_async_db, email_config={"default": _cfg("master@power.pt")})
        with patch.object(resolver, "db", fake_async_db):
            por_id = await resolver.resolve_email_config_for_sync("u1", "admin", POWER)
        assert por_id and por_id["email_address"] == "master@power.pt"

    async def test_a_config_propria_da_empresa_vence(self, fake_async_db):
        await _mundo(fake_async_db, email_config={
            "default": _cfg("master@power.pt"),
            f"company:{PRECISION}": _cfg("master@precision.pt"),
        })
        with patch.object(resolver, "db", fake_async_db):
            precision = await resolver.resolve_email_config_for_sync("u1", "admin", PRECISION)
        assert precision["email_address"] == "master@precision.pt"

    async def test_o_ultimo_recurso_nao_devolve_a_chave_company_de_outra_empresa(self, fake_async_db):
        # Sem «default» e sem o cargo: o «primeiro dict com email» era o company:<power>.
        await _mundo(fake_async_db, email_config={f"company:{POWER}": _cfg("master@power.pt")})
        with patch.object(resolver, "db", fake_async_db):
            precision = await resolver.resolve_email_config_for_sync("u1", "admin", PRECISION)
        assert precision is None

    async def test_quem_tem_uma_so_empresa_mantem_o_recurso(self, fake_async_db):
        await _mundo(fake_async_db, email_config={"default": _cfg("ana@power.pt")}, ucrs=(POWER,))
        with patch.object(resolver, "db", fake_async_db):
            resolvido = await resolver.resolve_email_config_for_sync("u1", "admin", POWER)
            outro_id = await resolver.resolve_email_config_for_sync("u1", "admin", "id-que-nao-e-conhecido")
        assert resolvido["email_address"] == "ana@power.pt"
        assert outro_id["email_address"] == "ana@power.pt"

    async def test_sem_empresa_pedida_o_comportamento_e_o_de_sempre(self, fake_async_db):
        await _mundo(fake_async_db, email_config={"default": _cfg("master@power.pt")})
        with patch.object(resolver, "db", fake_async_db):
            sem_empresa = await resolver.resolve_email_config_for_sync("u1", "admin", None)
            default = await resolver.resolve_email_config_for_sync("u1", "admin", "default")
        assert sem_empresa["email_address"] == "master@power.pt"
        assert default["email_address"] == "master@power.pt"

    async def test_a_conta_de_envio_nunca_e_a_de_outra_empresa(self, fake_async_db):
        """O envio de teste usa `resolve_sending_account`: tem de recuar para a Caixa Geral
        (ou falhar), não para a conta da Power."""
        await _mundo(fake_async_db, email_config={"default": _cfg("master@power.pt")})
        with patch.object(resolver, "db", fake_async_db):
            conta, origem = await resolver.resolve_sending_account(None, {"id": "u1", "role": "master"}, PRECISION)
        assert conta is None or conta.email != "master@power.pt"
        assert not str(origem).startswith("profile:")
