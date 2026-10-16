"""Webmail: a empresa activa limita os separadores e as contas, para QUALQUER staff (Lote 7.1).

O ataque, escrito primeiro: um CEO com acesso à Precision (rede do grupo) e à Domus (outra rede) trabalha
COMO Domus. O Webmail mostrava-lhe os separadores e a Caixa Geral da Precision (a vista consolidada junta
todas as empresas dele) e aceitava `?company_id=cmp-precision`. A Lote 4 tinha feito isto só para o Master.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from tests.unit.helpers_tenant import EMPRESAS, REDE_INCUMBENTE, tenant_db

CEO = {"id": "u-ceo", "name": "Rui", "role": "ceo", "effective_role": "ceo"}


def _sessao(vista=None):
    return {**CEO, **({"vista_empresa_id": vista} if vista else {})}


def _caixa(cid):
    return {
        "email_address": f"geral@{cid}.pt", "smtp_server": "smtp.x", "imap_server": "imap.x",
        "username": f"geral@{cid}.pt", "password": "x",
    }


@pytest.fixture
def mundo(fake_async_db, monkeypatch):
    import services.users_api_email_config as contas
    import services.webmail_scope as separadores

    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
    fake_async_db.companies.docs.extend(dict(e) for e in EMPRESAS)
    fake_async_db.user_company_roles.docs.extend([
        {"user_id": "u-ceo", "company_id": "cmp-precision", "company_name": "Precision Crédito", "role": "ceo"},
        {"user_id": "u-ceo", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "ceo"},
        {"user_id": "u-ceo", "company_id": "cmp-domus", "company_name": "Domus", "role": "ceo"},
    ])
    pessoais = [
        {"id": "a1", "email_address": "rui@precision.pt", "company_id": "cmp-precision", "label": "Pessoal"},
        {"id": "a2", "email_address": "rui@domus.pt", "company_id": "cmp-domus", "label": "Pessoal"},
    ]

    async def carregar(cid, user=None):
        return _caixa(cid.replace("cmp-", ""))

    with tenant_db(fake_async_db, contas, separadores), \
         patch("services.user_email_config_service.list_user_email_configs_all_companies", AsyncMock(return_value=pessoais)), \
         patch("services.email_config_resolver.load_caixa_geral_config", carregar):
        yield SimpleNamespace(db=fake_async_db, contas=contas, separadores=separadores)


async def _contas(mundo, user):
    request = SimpleNamespace(headers={}, state=SimpleNamespace())
    res = await mundo.contas.run_list_my_email_accounts(request, None, user, scope="all")
    return {a["email_address"] for a in res["accounts"]}


@pytest.mark.asyncio
class TestOsSeparadoresSeguemAEmpresaActiva:
    async def test_o_ataque_o_ceo_como_domus_so_tem_o_separador_da_domus(self, mundo):
        from services.webmail_scope import empresas_do_webmail

        assert [e.company_id for e in await empresas_do_webmail(_sessao("cmp-domus"))] == ["cmp-domus"]

    async def test_como_precision_tem_as_empresas_da_rede_do_grupo_e_nao_a_domus(self, mundo):
        """A fronteira é a REDE: Power e Precision partilham-na (decisão do Lote 4)."""
        from services.webmail_scope import empresas_do_webmail

        ids = {e.company_id for e in await empresas_do_webmail(_sessao("cmp-precision"))}
        assert ids == {"cmp-precision", "cmp-power"}

    async def test_sem_empresa_escolhida_tem_todos_os_separadores(self, mundo):
        from services.webmail_scope import empresas_do_webmail

        ids = {e.company_id for e in await empresas_do_webmail(_sessao())}
        assert ids == {"cmp-precision", "cmp-power", "cmp-domus"}

    async def test_um_cabecalho_forjado_nao_esvazia_nem_alarga(self, mundo):
        from services.webmail_scope import empresas_do_webmail

        ids = {e.company_id for e in await empresas_do_webmail(_sessao("cmp-que-nao-existe"))}
        assert ids == {"cmp-precision", "cmp-power", "cmp-domus"}


@pytest.mark.asyncio
class TestAVistaConsolidadaDasContasSegueAEmpresaActiva:
    async def test_o_ataque_como_domus_nao_aparece_nada_da_precision(self, mundo):
        emails = await _contas(mundo, _sessao("cmp-domus"))
        assert "geral@domus.pt" in emails and "rui@domus.pt" in emails
        assert not {e for e in emails if "precision" in e or "power" in e}, emails

    async def test_como_precision_nao_aparece_nada_da_domus(self, mundo):
        emails = await _contas(mundo, _sessao("cmp-precision"))
        assert "rui@precision.pt" in emails and "geral@precision.pt" in emails
        assert not {e for e in emails if "domus" in e}, emails

    async def test_sem_empresa_escolhida_a_vista_consolidada_continua_inteira(self, mundo):
        emails = await _contas(mundo, _sessao())
        assert {"rui@precision.pt", "rui@domus.pt", "geral@precision.pt", "geral@domus.pt"} <= emails

    async def test_a_empresa_pedida_por_parametro_de_outra_rede_e_recusada(self, mundo):
        """`?company_id=` da Precision com a Domus activa: a Caixa Geral não existe para ele."""
        from services.email_config_resolver import load_caixa_geral_config as _real  # noqa: F401
        from services.webmail_heranca import empresa_no_ambito_do_utilizador

        assert await empresa_no_ambito_do_utilizador("cmp-precision", _sessao("cmp-domus")) is False
        assert await empresa_no_ambito_do_utilizador("cmp-domus", _sessao("cmp-domus")) is True
        assert await empresa_no_ambito_do_utilizador("cmp-precision", _sessao("cmp-precision")) is True
