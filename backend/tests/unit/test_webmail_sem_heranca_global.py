"""Webmail: uma rede satélite NUNCA herda a configuração global (QA, Out 2026).

O DEFEITO REPORTADO
  Um utilizador da Domus (ilha) abria a configuração de Webmail e via a «Caixa
  Geral» da Power com o aviso «Servidores IMAP/SMTP herdados da configuração
  global». O `load_caixa_geral_config` chamava `get_system_config(<empresa>)`,
  que — para uma empresa sem config própria — GRAVA uma cópia da global e a
  devolvia; sem cópia, recorria a `default` e às contas de ambiente.
  `resolve_email_config` acabava em `system_config.main` para qualquer um.

A REGRA
  A global é da rede de omissão. Fora dela só conta o que a empresa configurou
  ela; sem isso, vazio. Cada teste tem a CONTRAPROVA do lado da Power (a
  herança legítima continua a funcionar), senão «nunca herda» passava com uma
  função que devolvesse sempre `None`.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import services.email_config_resolver as resolver
import services.system_config as system_config_mod
import services.user_email_config_service as user_email_config_mod
import services.users_api_email_config as users_api
import services.webmail_heranca as heranca
from tests.unit.helpers_tenant import (
    ANA,
    BRUNO,
    CARLA,
    REDE_INCUMBENTE,
    semear,
    tenant_db,
)

GLOBAL_EMAIL = {
    "imap_user": "geral@powerealestate.pt",
    "imap_password": "segredo-da-power",
    "imap_server": "imap.power.pt",
    "smtp_server": "smtp.power.pt",
}


@pytest.fixture(autouse=True)
def _cache_limpa():
    system_config_mod._config_cache.clear()
    yield
    system_config_mod._config_cache.clear()


@pytest.fixture
def base(fake_async_db, monkeypatch):
    """Duas redes + a configuração global da Power; rede de omissão = Power."""
    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
    semear(fake_async_db)
    fake_async_db.system_config.docs.append({"_id": "main", "email": dict(GLOBAL_EMAIL)})
    return fake_async_db


def _ctx(db):
    return tenant_db(db, resolver, heranca, system_config_mod, users_api, user_email_config_mod)


def _contas_de_ambiente():
    conta = MagicMock()
    conta.name = "power"
    conta.email = "ambiente@powerealestate.pt"
    conta.password = "pw"
    conta.imap_server = "imap.power.pt"
    conta.imap_port = 993
    conta.smtp_server = "smtp.power.pt"
    conta.smtp_port = 465
    return AsyncMock(return_value=[conta])


class TestCaixaGeralDaRedeSatelite:
    @pytest.mark.asyncio
    async def test_empresa_sem_config_propria_nao_recebe_a_caixa_da_power(self, base):
        with _ctx(base), patch(
            "services.email_service.get_email_accounts_async", _contas_de_ambiente(),
        ):
            caixa = await resolver.load_caixa_geral_config("cmp-domus", user=BRUNO)
        assert caixa is None

    @pytest.mark.asyncio
    async def test_nao_grava_a_copia_da_global_ao_perguntar(self, base):
        # `get_system_config(<empresa>)` cria `company:<id>` a partir da global:
        # perguntar não pode ter esse efeito.
        with _ctx(base):
            await resolver.load_caixa_geral_config("cmp-domus", user=BRUNO)
        assert not [d for d in base.system_config.docs if d["_id"] == "company:cmp-domus"]

    @pytest.mark.asyncio
    async def test_a_copia_herdada_ja_gravada_nao_conta(self, base):
        # O estado em que a produção já está: a cópia existe, com o utilizador da global.
        base.system_config.docs.append(
            {"_id": "company:cmp-domus", "company_id": "cmp-domus", "email": dict(GLOBAL_EMAIL)},
        )
        with _ctx(base):
            assert await resolver.load_caixa_geral_config("cmp-domus", user=BRUNO) is None

    @pytest.mark.asyncio
    async def test_a_caixa_que_a_propria_empresa_configurou_aparece(self, base):
        base.system_config.docs.append({
            "_id": "company:cmp-domus", "company_id": "cmp-domus",
            "email": {
                "imap_user": "geral@domus.pt", "imap_password": "pw-domus",
                "imap_server": "imap.domus.pt", "smtp_server": "smtp.domus.pt",
            },
        })
        with _ctx(base):
            caixa = await resolver.load_caixa_geral_config("cmp-domus", user=BRUNO)
        assert caixa and caixa["email_address"] == "geral@domus.pt"
        assert caixa["imap_server"] == "imap.domus.pt"

    @pytest.mark.asyncio
    async def test_config_propria_incompleta_nao_cai_nas_contas_de_ambiente(self, base):
        # A ilha começou a configurar a caixa (sem password): não pode ser
        # "completada" com a conta de ambiente da Power.
        base.system_config.docs.append({
            "_id": "company:cmp-domus", "company_id": "cmp-domus",
            "email": {"imap_user": "geral@domus.pt", "imap_server": "imap.domus.pt"},
        })
        with _ctx(base), patch(
            "services.email_service.get_email_accounts_async", _contas_de_ambiente(),
        ):
            assert await resolver.load_caixa_geral_config("cmp-domus", user=BRUNO) is None

    @pytest.mark.asyncio
    async def test_o_sentinel_default_nao_serve_a_um_utilizador_da_ilha(self, base):
        with _ctx(base), patch(
            "services.email_service.get_email_accounts_async", _contas_de_ambiente(),
        ):
            assert await resolver.load_caixa_geral_config("default", user=BRUNO) is None
            assert await resolver.load_caixa_geral_config(None, user=BRUNO) is None

    @pytest.mark.asyncio
    async def test_um_pedido_com_empresa_de_outra_rede_e_recusado(self, base):
        # O Bruno (Domus) mandou o id da Power no cabeçalho/query.
        with _ctx(base):
            assert await resolver.load_caixa_geral_config("cmp-power", user=BRUNO) is None

    @pytest.mark.asyncio
    async def test_contraprova_a_power_continua_a_ter_a_sua_caixa(self, base):
        with _ctx(base):
            caixa = await resolver.load_caixa_geral_config("cmp-power", user=ANA)
        assert caixa and caixa["email_address"] == "geral@powerealestate.pt"

    @pytest.mark.asyncio
    async def test_contraprova_a_rede_de_omissao_ainda_usa_o_recurso_default(self, base):
        # Utilizador da Power sem empresa («default»): a global é dela.
        with _ctx(base):
            caixa = await resolver.load_caixa_geral_config("default", user=ANA)
        assert caixa and caixa["email_address"] == "geral@powerealestate.pt"

    @pytest.mark.asyncio
    async def test_contraprova_a_rede_de_omissao_ainda_usa_as_contas_de_ambiente(
        self, fake_async_db, monkeypatch,
    ):
        monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
        semear(fake_async_db)  # sem system_config nenhuma
        with _ctx(fake_async_db), patch(
            "services.email_service.get_email_accounts_async", _contas_de_ambiente(),
        ), patch.object(resolver, "decrypt_email_secret", lambda v, c="": v):
            caixa = await resolver.load_caixa_geral_config("cmp-power", user=ANA)
        assert caixa and caixa["email_address"] == "ambiente@powerealestate.pt"

    @pytest.mark.asyncio
    async def test_sem_rede_de_omissao_mantem_o_comportamento_anterior(
        self, fake_async_db, monkeypatch,
    ):
        # Dev/CI: não há a quem atribuir a global — não se isola nada.
        monkeypatch.delenv("TENANT_DEFAULT_NETWORK_ID", raising=False)
        semear(fake_async_db)
        fake_async_db.system_config.docs.append({"_id": "main", "email": dict(GLOBAL_EMAIL)})
        with _ctx(fake_async_db):
            caixa = await resolver.load_caixa_geral_config("cmp-domus", user=BRUNO)
        assert caixa and caixa["email_address"] == "geral@powerealestate.pt"

    @pytest.mark.asyncio
    async def test_empresa_desconhecida_falha_fechada(self, base):
        with _ctx(base):
            assert await resolver.load_caixa_geral_config("cmp-inventada", user=ANA) is None


class TestResolverNaoHerdaServidoresGlobais:
    def _seed_utilizador(self, base, user_id, company):
        base.users.docs.append({"id": user_id, "role": "diretor", "company": company, "email_config": {}})

    @pytest.mark.asyncio
    async def test_utilizador_da_ilha_sem_config_fica_sem_servidores(self, base):
        self._seed_utilizador(base, "u-bruno", "cmp-domus")
        with _ctx(base):
            resolvido = await resolver.resolve_email_config(
                "u-bruno", active_company_id="cmp-domus",
            )
        assert resolvido["config_source"] == "none"
        assert resolvido["imap_server"] is None and resolvido["smtp_server"] is None

    @pytest.mark.asyncio
    async def test_contraprova_utilizador_da_power_herda_a_global(self, base):
        base.system_config.docs[0]["email"].update(
            {"imap_server": "imap.power.pt", "smtp_server": "smtp.power.pt"},
        )
        self._seed_utilizador(base, "u-ana", "cmp-power")
        with _ctx(base):
            resolvido = await resolver.resolve_email_config(
                "u-ana", active_company_id="cmp-power",
            )
        assert resolvido["config_source"] == "system"
        assert resolvido["imap_server"] == "imap.power.pt"

    @pytest.mark.asyncio
    async def test_a_conta_propria_do_utilizador_da_ilha_continua_a_funcionar(self, base):
        base.users.docs.append({
            "id": "u-bruno", "role": "diretor", "company": "cmp-domus",
            "email_config": {"company:cmp-domus": {
                "is_configured": True, "email_address": "bruno@domus.pt",
                "imap_server": "imap.domus.pt", "smtp_server": "smtp.domus.pt",
                "encrypted_password": "x",
            }},
        })
        with _ctx(base):
            resolvido = await resolver.resolve_email_config(
                "u-bruno", active_company_id="cmp-domus",
            )
        assert resolvido["config_source"] == "user"
        assert resolvido["imap_server"] == "imap.domus.pt"


class TestListagemDeContas:
    def _request(self):
        req = MagicMock()
        req.headers = {}
        return req

    async def _listar(self, base, user, empresa, papel="diretor", scope=None):
        async def activa(_req, _user):
            return empresa

        with _ctx(base), patch(
            "services.auth.get_active_company_id_async", activa,
        ), patch("services.auth.get_effective_role", lambda _r, _u: papel), patch(
            "services.email_service.get_email_accounts_async", _contas_de_ambiente(),
        ):
            return await users_api.run_list_my_email_accounts(
                self._request(), None, user, scope,
            )

    @pytest.mark.asyncio
    async def test_rede_satelite_sem_caixa_propria_lista_vazio(self, base):
        resposta = await self._listar(base, BRUNO, "cmp-domus")
        assert resposta["accounts"] == []
        assert resposta["caixa_geral_injected"] is False

    @pytest.mark.asyncio
    async def test_vista_consolidada_da_ilha_tambem_nao_injecta_a_da_power(self, base):
        resposta = await self._listar(base, BRUNO, "cmp-domus", scope="all")
        assert resposta["accounts"] == []
        assert resposta["caixa_geral_injected"] is False

    @pytest.mark.asyncio
    async def test_cabecalho_com_empresa_de_outra_rede_nao_lista_a_caixa_dessa_rede(self, base):
        # O Bruno (Domus) manda o id da Power em X-Company-Id: a listagem não
        # pode injectar a Caixa Geral da Power só porque o cargo é de gestão.
        resposta = await self._listar(base, BRUNO, "cmp-power")
        assert resposta["caixa_geral_injected"] is False
        assert resposta["accounts"] == []

    @pytest.mark.asyncio
    async def test_quem_trabalha_nas_duas_redes_so_ve_cada_caixa_na_sua_rede(self, base):
        # A Carla é consultor (sem direito à Caixa Geral): contraprova de que o
        # cargo continua a decidir, e de que a Domus nunca recebe a da Power.
        resposta = await self._listar(base, CARLA, "cmp-domus", papel="consultor", scope="all")
        assert resposta["caixa_geral_injected"] is False

    @pytest.mark.asyncio
    async def test_contraprova_a_power_continua_a_ver_a_caixa_geral(self, base):
        resposta = await self._listar(base, ANA, "cmp-power")
        assert resposta["caixa_geral_injected"] is True
        assert [a["email_address"] for a in resposta["accounts"]] == ["geral@powerealestate.pt"]

    @pytest.mark.asyncio
    async def test_a_caixa_geral_propria_da_ilha_aparece_so_na_ilha(self, base):
        base.system_config.docs.append({
            "_id": "company:cmp-domus", "company_id": "cmp-domus",
            "email": {
                "imap_user": "geral@domus.pt", "imap_password": "pw",
                "imap_server": "imap.domus.pt", "smtp_server": "smtp.domus.pt",
            },
        })
        da_ilha = await self._listar(base, BRUNO, "cmp-domus")
        assert [a["email_address"] for a in da_ilha["accounts"]] == ["geral@domus.pt"]
        da_power = await self._listar(base, ANA, "cmp-power")
        assert [a["email_address"] for a in da_power["accounts"]] == ["geral@powerealestate.pt"]


class TestEnderecosDoWebmail:
    @pytest.mark.asyncio
    async def test_o_separador_da_ilha_nao_inclui_a_caixa_geral_da_power(self, base):
        import services.webmail_scope as scope_mod

        with _ctx(base), patch.object(scope_mod, "db", base):
            domus = await scope_mod.conta_da_caixa_geral("cmp-domus")
            power = await scope_mod.conta_da_caixa_geral("cmp-power")
        assert domus == set()
        assert power == {"geral@powerealestate.pt"}


class TestPodeHerdar:
    @pytest.mark.asyncio
    async def test_so_a_rede_de_omissao_herda(self, base):
        with _ctx(base):
            assert await heranca.pode_herdar_configuracao_global("cmp-power") is True
            assert await heranca.pode_herdar_configuracao_global("cmp-precision") is True
            assert await heranca.pode_herdar_configuracao_global("cmp-domus") is False

    @pytest.mark.asyncio
    async def test_sem_utilizador_o_sentinel_nao_herda(self, base):
        with _ctx(base):
            assert await heranca.pode_herdar_configuracao_global("default") is False
            assert await heranca.pode_herdar_configuracao_global("default", user=ANA) is True
            assert await heranca.pode_herdar_configuracao_global("default", user=BRUNO) is False
