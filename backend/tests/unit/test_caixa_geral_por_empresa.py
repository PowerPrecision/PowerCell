"""QA-7 (1): a Caixa Geral de uma empresa da rede de omissão é a DELA.

Antes, uma empresa sem configuração própria herdava a global (a da Power) e a Precision
mostrava `geral@powerealestate.pt` na Área Pessoal; o Master na vista «Sistema» também.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import services.email_config_resolver as resolver
import services.system_config as system_config_mod
import services.webmail_heranca as heranca
from tests.unit.helpers_tenant import ANA, REDE_INCUMBENTE, semear, tenant_db  # noqa: F401

GLOBAL_EMAIL = {
    "imap_user": "geral@powerealestate.pt",
    "imap_password": "segredo-da-power",
    "imap_server": "imap.power.pt",
    "smtp_server": "smtp.power.pt",
}


def _conta(nome, email):
    return SimpleNamespace(
        name=nome, email=email, password="pw", imap_server="imap.x", imap_port=993,
        smtp_server="smtp.x", smtp_port=465,
    )


async def _contas_precision_e_power():
    return [_conta("power", "geral@powerealestate.pt"), _conta("precision", "geral@precisioncredito.pt")]


@pytest.fixture(autouse=True)
def _cache_limpa():
    system_config_mod._config_cache.clear()
    yield
    system_config_mod._config_cache.clear()


@pytest.fixture
def base(fake_async_db, monkeypatch):
    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
    semear(fake_async_db)
    fake_async_db.system_config.docs.append({"_id": "main", "email": dict(GLOBAL_EMAIL)})
    return fake_async_db


def _ctx(base):
    return tenant_db(base, resolver, heranca, system_config_mod)


async def _resolver(base, cid, user=ANA):
    with _ctx(base), patch(
        "services.email_service.get_email_accounts_async", _contas_precision_e_power,
    ), patch.object(resolver, "decrypt_email_secret", lambda v, _ctx="": v):
        return await resolver.load_caixa_geral_config(cid, user=user)


class TestCaixaGeralPorEmpresa:
    @pytest.mark.asyncio
    async def test_a_precision_sem_config_propria_nao_recebe_a_caixa_da_power(self, base):
        caixa = await _resolver(base, "cmp-precision")
        assert (caixa or {}).get("email_address") != "geral@powerealestate.pt"
        assert caixa and caixa["email_address"] == "geral@precisioncredito.pt"

    @pytest.mark.asyncio
    async def test_a_power_continua_a_ter_a_sua_caixa(self, base):
        caixa = await _resolver(base, "cmp-power")
        assert caixa and caixa["email_address"] == "geral@powerealestate.pt"

    @pytest.mark.asyncio
    async def test_empresa_sem_conta_com_o_seu_nome_fica_sem_caixa(self, base):
        base.companies.docs.append({"id": "cmp-nova", "name": "Outra Casa", "network_id": REDE_INCUMBENTE})
        assert await _resolver(base, "cmp-nova") is None

    @pytest.mark.asyncio
    async def test_a_config_propria_da_precision_vence(self, base):
        proprio = dict(GLOBAL_EMAIL, imap_user="proprio@precisioncredito.pt")
        base.system_config.docs.append({"_id": "company:cmp-precision", "email": proprio})
        caixa = await _resolver(base, "cmp-precision")
        assert caixa and caixa["email_address"] == "proprio@precisioncredito.pt"


MASTER = {"id": "u-master", "role": "master", "company": "Sistema", "email": "m@x.pt"}


class TestAreaPessoalDoMaster:
    def _request(self):
        from unittest.mock import MagicMock

        req = MagicMock()
        req.headers = {}
        return req

    async def _listar(self, base, user, empresa):
        import services.users_api_email_config as users_api
        import services.user_email_config_service as ucfg

        async def activa(_req, _user):
            return empresa

        with tenant_db(base, resolver, heranca, system_config_mod, users_api, ucfg), patch(
            "services.auth.get_active_company_id_async", activa,
        ), patch("services.auth.get_effective_role", lambda _r, _u: "admin"), patch(
            "services.email_service.get_email_accounts_async", _contas_precision_e_power,
        ), patch.object(resolver, "decrypt_email_secret", lambda v, _ctx="": v):
            return await users_api.run_list_my_email_accounts(self._request(), None, user, None)

    @pytest.mark.asyncio
    async def test_na_vista_sistema_nao_aparece_a_caixa_da_power(self, base):
        resposta = await self._listar(base, MASTER, "default")
        assert resposta["caixa_geral_injected"] is False
        assert all(a.get("email_address") != "geral@powerealestate.pt" for a in resposta["accounts"])

    @pytest.mark.asyncio
    async def test_com_a_precision_escolhida_so_aparece_a_da_precision(self, base):
        resposta = await self._listar(dict_com_master(base), {**MASTER, "vista_empresa_id": "cmp-precision"}, "cmp-precision")
        enderecos = {a.get("email_address") for a in resposta["accounts"]}
        assert "geral@powerealestate.pt" not in enderecos
        assert "geral@precisioncredito.pt" in enderecos

    @pytest.mark.asyncio
    async def test_contraprova_com_a_power_escolhida_aparece_a_da_power(self, base):
        resposta = await self._listar(dict_com_master(base), {**MASTER, "vista_empresa_id": "cmp-power"}, "cmp-power")
        enderecos = {a.get("email_address") for a in resposta["accounts"]}
        assert "geral@powerealestate.pt" in enderecos


def dict_com_master(base):
    base.user_company_roles.docs.append(
        {"user_id": "u-master", "company_id": "cmp-precision", "role": "admin", "is_active": True}
    )
    base.user_company_roles.docs.append(
        {"user_id": "u-master", "company_id": "cmp-power", "role": "admin", "is_active": True}
    )
    return base
