"""Caixas partilhadas por (cargo, rede) e registo público por rede contra um MongoDB REAL (D-8, D-32).

O que um duplo NÃO prova — e que aqui se prova:

* o **upsert com filtro composto** (`$and` + `$or` + `$in: [None, ""]`): é o que faz a
  configuração antiga (sem `network_id`) ser editada pela rede de omissão em vez de
  nascer uma segunda, e uma rede concreta nunca encontrar a de outra;
* `$in: [None, ""]` sobre um campo AUSENTE (a pilha antiga) e o `update_many` do backfill;
* a procura de duplicados do registo público: rede, empresas da rede e pilha por carimbar.
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient

from tests.unit.helpers_tenant import EMPRESAS, REDE_DOMUS, REDE_INCUMBENTE, UCRS, tenant_db

ADM_POWER = {"id": "adm-power", "email": "adm@power.pt", "role": "admin", "effective_role": "admin"}
ADM_DOMUS = {"id": "adm-domus", "email": "adm@domus.pt", "role": "admin", "effective_role": "admin"}
IDX_POWER = {"id": "idx-power", "email": "idx@power.pt", "role": "indexacao", "effective_role": "indexacao"}
IDX_DOMUS = {"id": "idx-domus", "email": "idx@domus.pt", "role": "indexacao", "effective_role": "indexacao"}

CONFIG_LEGADA = {
    "role": "indexacao", "email_address": "index@power.pt", "is_configured": True,
    "encrypted_password": "ENC:power", "auth_method": "imap_smtp",
}


@pytest_asyncio.fixture
async def bd(monkeypatch):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
    nome = f"test_caixas_partilhadas_{uuid.uuid4().hex[:8]}"
    base = cliente[nome]
    await base.companies.insert_many([dict(e) for e in EMPRESAS])
    await base.user_company_roles.insert_many([
        *[dict(u) for u in UCRS],
        {"user_id": "adm-power", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "admin", "is_default": True},
        {"user_id": "adm-domus", "company_id": "cmp-domus", "company_name": "Domus", "role": "admin", "is_default": True},
        {"user_id": "idx-power", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "indexacao", "is_default": True},
        {"user_id": "idx-domus", "company_id": "cmp-domus", "company_name": "Domus", "role": "indexacao", "is_default": True},
    ])
    await base.users.insert_many([{**u, "is_active": True, "name": u["id"]} for u in (ADM_POWER, ADM_DOMUS, IDX_POWER, IDX_DOMUS)])
    await base.shared_role_email_configs.insert_one(dict(CONFIG_LEGADA))
    yield base
    await cliente.drop_database(nome)
    cliente.close()


@pytest.fixture
def cadeia(bd):
    import services.email_config_resolver as ecr
    import services.public_registration as pr
    import services.shared_email_crud as crud
    import services.shared_mailbox_scope as sms
    import services.workflow_scope as ws

    async def _empresa_activa(request, user):
        return request.headers.get("X-Company-Id") or ""

    with tenant_db(bd, sms, crud, ws, ecr, pr), \
            patch("services.auth.get_active_company_id_async", _empresa_activa):
        yield bd


def _pedido(company_id):
    return MagicMock(headers={"X-Company-Id": company_id}, state=MagicMock(spec=[]))


def _payload(**extra):
    from models.shared_email_config import SharedEmailConfigCreate

    base = dict(role="indexacao", email_address="index@domus.pt", imap_server="imap.domus.pt",
                smtp_server="smtp.domus.pt", encrypted_password="segredo")
    base.update(extra)
    return SharedEmailConfigCreate(**base)


async def _configs(base):
    return await base.shared_role_email_configs.find({"role": "indexacao"}, {"_id": 0}).to_list(10)


class TestUpsertComFiltroComposto:
    @pytest.mark.asyncio
    async def test_a_domus_cria_a_sua_e_a_da_power_fica_intacta(self, cadeia):
        import services.shared_email_crud as crud

        await crud.run_upsert_shared_email_config("indexacao", _payload(), ADM_DOMUS, _pedido("cmp-domus"))
        configs = await _configs(cadeia)
        assert len(configs) == 2
        legada = next(c for c in configs if not c.get("network_id"))
        assert legada["email_address"] == "index@power.pt" and legada["encrypted_password"] == "ENC:power"
        assert next(c for c in configs if c.get("network_id") == REDE_DOMUS)["email_address"] == "index@domus.pt"
        # Repetir não duplica.
        await crud.run_upsert_shared_email_config("indexacao", _payload(email_address="outro@domus.pt"), ADM_DOMUS, _pedido("cmp-domus"))
        assert len(await _configs(cadeia)) == 2

    @pytest.mark.asyncio
    async def test_a_power_edita_a_legada_e_carimba_a_sem_criar_outra(self, cadeia):
        import services.shared_email_crud as crud

        await crud.run_upsert_shared_email_config(
            "indexacao", _payload(email_address="novo@power.pt"), ADM_POWER, _pedido("cmp-power"),
        )
        configs = await _configs(cadeia)
        assert len(configs) == 1
        assert configs[0]["network_id"] == REDE_INCUMBENTE and configs[0]["email_address"] == "novo@power.pt"
        await crud.run_upsert_shared_email_config("indexacao", _payload(), ADM_POWER, _pedido("cmp-power"))
        assert len(await _configs(cadeia)) == 1, "a segunda gravação encontra a já carimbada"

    @pytest.mark.asyncio
    async def test_a_leitura_por_rede(self, cadeia):
        import services.shared_email_crud as crud
        from services.shared_mailbox_scope import config_da_caixa, config_do_utilizador, configs_da_rede

        await crud.run_upsert_shared_email_config("indexacao", _payload(), ADM_DOMUS, _pedido("cmp-domus"))
        assert (await config_da_caixa("indexacao", REDE_DOMUS))["email_address"] == "index@domus.pt"
        assert (await config_da_caixa("indexacao", REDE_INCUMBENTE))["email_address"] == "index@power.pt"
        assert (await config_da_caixa("indexacao", None))["email_address"] == "index@power.pt"
        assert (await config_da_caixa("indexacao", "rede-que-nao-existe")) is None
        assert [c["email_address"] for c in await configs_da_rede(REDE_DOMUS)] == ["index@domus.pt"]
        assert [c["email_address"] for c in await configs_da_rede(REDE_INCUMBENTE)] == ["index@power.pt"]
        assert (await config_do_utilizador("indexacao", IDX_DOMUS))["email_address"] == "index@domus.pt"
        assert (await config_do_utilizador("indexacao", IDX_POWER))["email_address"] == "index@power.pt"

    @pytest.mark.asyncio
    async def test_remover_e_desligar_so_tocam_na_propria_rede(self, cadeia):
        import services.shared_email_crud as crud

        await cadeia.shared_role_email_configs.update_one({"role": "indexacao"}, {"$set": {"google_refresh_token": "tok"}})
        await crud.run_upsert_shared_email_config("indexacao", _payload(), ADM_DOMUS, _pedido("cmp-domus"))
        await crud.run_delete_shared_email_config("indexacao", ADM_DOMUS, _pedido("cmp-domus"))
        restantes = await _configs(cadeia)
        assert len(restantes) == 1 and restantes[0]["google_refresh_token"] == "tok"


class TestEmailsDaCaixa:
    @pytest_asyncio.fixture
    async def emails(self, cadeia):
        await cadeia.emails.insert_many([
            {"id": "leg", "shared_role": "indexacao", "message_id": "<m>"},
            {"id": "pw", "shared_role": "indexacao", "network_id": REDE_INCUMBENTE, "message_id": "<m>"},
            {"id": "dm", "shared_role": "indexacao", "network_id": REDE_DOMUS, "message_id": "<m>"},
            {"id": "pessoal", "synced_for_user": "u"},
        ])
        return cadeia

    @pytest.mark.asyncio
    async def test_a_condicao_dos_emails_por_utilizador(self, emails):
        from services.shared_mailbox_scope import condicao_de_emails_da_caixa

        async def ids(user):
            cond = await condicao_de_emails_da_caixa("indexacao", user)
            return sorted([e["id"] async for e in emails.emails.find(cond, {"_id": 0, "id": 1})])

        assert await ids(IDX_POWER) == ["leg", "pw"]
        assert await ids(IDX_DOMUS) == ["dm"]

    @pytest.mark.asyncio
    async def test_o_duplicado_e_por_rede(self, emails):
        from services.shared_mailbox_scope import duplicado_da_caixa

        async def ids(config):
            filtro = duplicado_da_caixa("<m>", "indexacao", config)
            return sorted([e["id"] async for e in emails.emails.find(filtro, {"_id": 0, "id": 1})])

        assert await ids({"network_id": REDE_DOMUS}) == ["dm"]
        assert await ids({"network_id": REDE_INCUMBENTE}) == ["leg", "pw"]
        assert await ids({}) == ["leg", "pw"], "caixa antiga = rede de omissão"

    @pytest.mark.asyncio
    async def test_a_migracao_com_update_many_real(self, emails):
        from scripts import backfill_shared_mailbox_network_id as mig

        plano = await mig.planear(emails, REDE_INCUMBENTE)
        assert plano == {"rede": REDE_INCUMBENTE, "configs_por_carimbar": 1, "emails_por_carimbar": 1}
        escrito = await mig.aplicar(emails, REDE_INCUMBENTE)
        assert escrito["configs_carimbadas"] == 1 and escrito["emails_carimbados"] == 1
        por_id = {e["id"]: e async for e in emails.emails.find({}, {"_id": 0})}
        assert por_id["leg"]["network_id"] == REDE_INCUMBENTE
        assert por_id["dm"]["network_id"] == REDE_DOMUS
        assert "network_id" not in por_id["pessoal"]
        segunda = await mig.aplicar(emails, REDE_INCUMBENTE)
        assert segunda["configs_carimbadas"] == 0 and segunda["emails_carimbados"] == 0


class TestRegistoPublicoPorRede:
    @pytest_asyncio.fixture
    async def clientes(self, cadeia):
        base = {"nome": "Maria", "contacto": {"email": "maria@teste.pt"}}
        await cadeia.clients.insert_many([
            {"id": "c-pw", "network_id": REDE_INCUMBENTE, "company_id": "cmp-power", **base},
            {"id": "c-dm", "network_id": REDE_DOMUS, "company_id": "cmp-domus", **base},
            {"id": "c-leg", **{**base, "contacto": {"email": "antiga@teste.pt"}}},
            {"id": "c-so-empresa", "company_id": "cmp-domus", **{**base, "contacto": {"email": "so-empresa@teste.pt"}}},
        ])
        return cadeia

    async def _procurar(self, rede, email):
        import services.public_registration as pr
        from services.tenant_network import build_network_scope_condition

        condicao = build_network_scope_condition(await pr.ambito_do_registo(rede))
        achado = await pr._cliente_existente_na_rede(condicao, {"contacto.email": email})
        return achado and achado["id"]

    @pytest.mark.asyncio
    async def test_cada_rede_so_encontra_o_seu(self, clientes):
        assert await self._procurar(REDE_DOMUS, "maria@teste.pt") == "c-dm"
        assert await self._procurar(REDE_INCUMBENTE, "maria@teste.pt") == "c-pw"
        assert await self._procurar("rede:cmp-outra", "maria@teste.pt") is None

    @pytest.mark.asyncio
    async def test_a_pilha_por_carimbar_so_para_a_rede_de_omissao(self, clientes):
        assert await self._procurar(REDE_INCUMBENTE, "antiga@teste.pt") == "c-leg"
        assert await self._procurar(REDE_DOMUS, "antiga@teste.pt") is None
        assert await self._procurar(None, "antiga@teste.pt") == "c-leg", "link sem rede: só a pilha antiga"
        assert await self._procurar(None, "maria@teste.pt") is None, "e nunca um cliente de uma rede concreta"

    @pytest.mark.asyncio
    async def test_um_cliente_so_com_a_empresa_conta_para_a_rede_dela(self, clientes):
        assert await self._procurar(REDE_DOMUS, "so-empresa@teste.pt") == "c-so-empresa"
        assert await self._procurar(REDE_INCUMBENTE, "so-empresa@teste.pt") is None
