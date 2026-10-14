"""
Lote 4, ponto 3 (Out 2026) — «A ler emails de» segue a empresa que o Master escolhe.

O DEFEITO
  O Master muda o Tenant para «Precision» e a dropdown lateral continua a mostrar a
  Caixa Geral da «Power». A vista consolidada (`scope=all`) injecta a Caixa Geral de
  CADA empresa em que o utilizador tem um UCR com cargo de gestão — e o Master tem UCR
  numa empresa só: a escolhida no cabeçalho nunca era a que aparecia.

A REGRA
  Com uma empresa escolhida (`vista_empresa_id`, só a CONTA Master) a lista mostra as
  caixas dessa empresa — incluindo a Caixa Geral, mesmo sem UCR nela — e deixa de mostrar
  as das outras. Sem empresa escolhida, ou para qualquer outro utilizador, nada muda.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

MASTER = {"id": "u-master", "name": "Master", "role": "master", "effective_role": "master"}


def _sessao(vista=None, **extra):
    s = {**MASTER, **extra}
    if vista:
        s["vista_empresa_id"] = vista
    return s


def _caixa(cid):
    return {
        "email_address": f"geral@{cid}.pt", "smtp_server": "smtp.x", "imap_server": "imap.x",
        "username": f"geral@{cid}.pt", "password": "x",
    }


@pytest.fixture
def mundo(fake_async_db):
    import services.users_api_email_config as mod

    fake_async_db.companies.docs.extend([
        {"id": "cmp-power", "name": "Power Real Estate", "network_id": "rede-a"},
        {"id": "cmp-precision", "name": "Precision Crédito", "network_id": "rede-a"},
    ])
    # O Master tem UCR de Admin só na Power.
    fake_async_db.user_company_roles.docs.append(
        {"user_id": "u-master", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "admin"},
    )
    pedidas: list[str] = []

    async def carregar(cid, user=None):
        pedidas.append(cid)
        return _caixa(cid.replace("cmp-", ""))

    pessoais = [
        {"id": "a1", "email_address": "master@power.pt", "company_id": "cmp-power", "label": "Pessoal"},
        {"id": "a2", "email_address": "master@precision.pt", "company_id": "cmp-precision", "label": "Pessoal"},
    ]
    with patch.object(mod, "db", fake_async_db), \
         patch("services.user_email_config_service.list_user_email_configs_all_companies",
               AsyncMock(return_value=pessoais)), \
         patch("services.email_config_resolver.load_caixa_geral_config", carregar):
        yield SimpleNamespace(db=fake_async_db, pedidas=pedidas, mod=mod)


async def _listar(mundo, user):
    request = SimpleNamespace(headers={}, state=SimpleNamespace())
    return await mundo.mod.run_list_my_email_accounts(request, None, user, scope="all")


def _emails(res):
    return [a["email_address"] for a in res["accounts"]]


@pytest.mark.asyncio
class TestACaixaGeralSegueAEmpresaEscolhida:
    async def test_a_exploracao_precision_escolhida_mostra_a_caixa_geral_da_precision(self, mundo):
        res = await _listar(mundo, _sessao("cmp-precision"))
        emails = _emails(res)
        assert "geral@precision.pt" in emails
        assert "geral@power.pt" not in emails, "a Caixa Geral da Power apareceu com a Precision escolhida"

    async def test_so_pede_a_caixa_geral_da_empresa_escolhida(self, mundo):
        await _listar(mundo, _sessao("cmp-precision"))
        assert mundo.pedidas == ["cmp-precision"]

    async def test_as_caixas_pessoais_das_outras_empresas_tambem_saem_da_vista(self, mundo):
        emails = _emails(await _listar(mundo, _sessao("cmp-precision")))
        assert "master@precision.pt" in emails
        assert "master@power.pt" not in emails

    async def test_a_empresa_onde_o_master_tem_ucr_continua_a_funcionar(self, mundo):
        emails = _emails(await _listar(mundo, _sessao("cmp-power")))
        assert "geral@power.pt" in emails
        assert "geral@precision.pt" not in emails

    async def test_sem_empresa_escolhida_mantem_a_vista_consolidada(self, mundo):
        # Contraprova: a mudança só vale com uma empresa escolhida.
        res = await _listar(mundo, _sessao())
        emails = _emails(res)
        assert "geral@power.pt" in emails
        assert {"master@power.pt", "master@precision.pt"} <= set(emails)

    async def test_empresa_inexistente_nao_esvazia_a_lista(self, mundo):
        emails = _emails(await _listar(mundo, _sessao("cmp-que-nao-existe")))
        assert "geral@power.pt" in emails

    async def test_quem_nao_e_master_nao_ganha_vista(self, mundo):
        """Uma chave forjada no dicionário de um Admin local não lhe dá a caixa de outra empresa."""
        admin = {"id": "u-master", "name": "A", "role": "admin", "effective_role": "admin",
                 "vista_empresa_id": "cmp-precision"}
        emails = _emails(await _listar(mundo, admin))
        assert "geral@precision.pt" not in emails
        assert "geral@power.pt" in emails
