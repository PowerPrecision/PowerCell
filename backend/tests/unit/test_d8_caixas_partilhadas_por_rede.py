"""
D-8 — as caixas partilhadas por cargo cruzavam emails entre redes.

O ATAQUE (a que `TestAExploracao` dá corpo)
  `shared_role_email_configs` tinha UMA linha por cargo para o sistema
  inteiro, e tudo o que a lia ou escrevia identificava-a só pelo cargo:

    * o Admin da Domus editava — e ligava por OAuth — a caixa de Indexação
      da Power;
    * a regra «caixa partilhada do seu cargo» dava a TODOS os utilizadores
      `indexacao` de TODAS as redes os emails da Indexação de cada rede
      (documentos e dados de clientes);
    * `box=shared_indexacao` na lista, nos não lidos e nas estatísticas do
      Webmail não tinha fronteira de rede;
    * o aviso em tempo real (`new_email`: assunto + remetente) ia a todos os
      utilizadores com o cargo, e o da Caixa Geral a todo o staff.

O QUE SE GARANTE
  1. Administração: cada rede gere a SUA caixa (cargo, rede). A configuração
     legada (sem `network_id`) é da rede de omissão e carimba-se ao ser editada.
  2. Escrita: o email sincronizado herda a rede da caixa; o «já sincronizei?»
     é por rede (o mesmo Message-ID chega a duas redes).
  3. Leitura: o cargo só vale DENTRO da rede (`email_access`, lista, não
     lidos, estatísticas, pesquisa, resolução da conta).
  4. Aviso em tempo real: só quem tem o email no seu âmbito.
  5. Migração: carimba o que falta, recusa-se sem rede, idempotente.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import (  # noqa: F401  (rede_de_omissao_incumbente é fixture)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

BACKEND = Path(__file__).resolve().parents[2]

ADM_POWER = {"id": "adm-power", "email": "adm@power.pt", "role": "admin", "effective_role": "admin"}
ADM_DOMUS = {"id": "adm-domus", "email": "adm@domus.pt", "role": "admin", "effective_role": "admin"}
IDX_POWER = {"id": "idx-power", "email": "idx@power.pt", "role": "indexacao", "effective_role": "indexacao"}
IDX_DOMUS = {"id": "idx-domus", "email": "idx@domus.pt", "role": "indexacao", "effective_role": "indexacao"}
MASTER = {"id": "master", "email": "m@x.pt", "role": "master", "effective_role": "master"}

UTILIZADORES = [
    {**u, "is_active": True, "name": u["id"]} for u in (ADM_POWER, ADM_DOMUS, IDX_POWER, IDX_DOMUS, MASTER)
]
UCRS = [
    {"user_id": "adm-power", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "admin", "is_default": True},
    {"user_id": "adm-domus", "company_id": "cmp-domus", "company_name": "Domus", "role": "admin", "is_default": True},
    {"user_id": "idx-power", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "indexacao", "is_default": True},
    {"user_id": "idx-domus", "company_id": "cmp-domus", "company_name": "Domus", "role": "indexacao", "is_default": True},
    {"user_id": "master", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "master", "is_default": True},
]

#: A caixa de Indexação que existia ANTES do D-8: sem `network_id`.
CONFIG_LEGADA = {
    "role": "indexacao", "email_address": "index@power.pt", "display_name": "Indexação Power",
    "is_configured": True, "encrypted_password": "ENC:power", "auth_method": "imap_smtp",
    "google_refresh_token": "tok-power", "google_email": "index@power.pt",
    "imap_server": "imap.power.pt", "smtp_server": "smtp.power.pt",
}

E_LEGADO = {"id": "e-leg", "shared_role": "indexacao", "from_email": "cli@a.pt", "to_emails": ["index@power.pt"]}
E_POWER = {"id": "e-pw", "shared_role": "indexacao", "network_id": REDE_INCUMBENTE,
           "from_email": "cli@a.pt", "to_emails": ["index@power.pt"]}
E_DOMUS = {"id": "e-dm", "shared_role": "indexacao", "network_id": REDE_DOMUS,
           "from_email": "cli@b.pt", "to_emails": ["index@domus.pt"]}


def _pedido(company_id=None):
    headers = {"X-Company-Id": company_id} if company_id else {}
    return MagicMock(headers=headers, state=MagicMock(spec=[]))


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    import services.email_access as ea
    import services.email_config_resolver as ecr
    import services.email_process_crud as epc
    import services.email_service as es
    import services.email_webmail as ew
    import services.gmail_api_service as gas
    import services.shared_email_crud as crud
    import services.shared_email_google as google
    import services.shared_email_sync  # noqa: F401  (sem db próprio: usa o do scope)
    import services.shared_mailbox_scope as sms
    import services.workflow_scope as ws

    semear(fake_async_db)
    fake_async_db.users.docs.extend(dict(u) for u in UTILIZADORES)
    fake_async_db.user_company_roles.docs.extend(dict(u) for u in UCRS)
    fake_async_db.shared_role_email_configs.docs.append(dict(CONFIG_LEGADA))

    async def _empresa_activa(request, user):
        return request.headers.get("X-Company-Id") or ""

    with tenant_db(fake_async_db, sms, crud, google, ws, ea, ecr, epc, es, ew, gas), \
            patch("services.auth.get_active_company_id_async", _empresa_activa):
        yield fake_async_db


def _configs(bd, role="indexacao"):
    return [c for c in bd.shared_role_email_configs.docs if c.get("role") == role]


def _da_rede(bd, rede, role="indexacao"):
    return next((c for c in _configs(bd, role) if c.get("network_id") == rede), None)


def _legada(bd):
    return next(c for c in _configs(bd) if not c.get("network_id"))


def _payload(**extra):
    from models.shared_email_config import SharedEmailConfigCreate

    base = dict(role="indexacao", email_address="index@domus.pt", display_name="Indexação Domus",
                imap_server="imap.domus.pt", smtp_server="smtp.domus.pt", encrypted_password="segredo-domus")
    base.update(extra)
    return SharedEmailConfigCreate(**base)


# ====================================================================
# 1. O ATAQUE — cada rede gere só a sua caixa
# ====================================================================

class TestAExploracao:
    @pytest.mark.asyncio
    async def test_o_admin_da_domus_nao_ve_a_caixa_da_power(self, mundo):
        import services.shared_email_crud as crud

        r = await crud.run_list_shared_email_configs(ADM_DOMUS, _pedido("cmp-domus"))
        assert r.total == 0
        g = await crud.run_get_shared_email_config("indexacao", ADM_DOMUS, _pedido("cmp-domus"))
        assert g.email_address is None and g.has_google_oauth is False and g.is_configured is False

    @pytest.mark.asyncio
    async def test_o_admin_da_domus_nao_edita_a_caixa_da_power_cria_a_sua(self, mundo):
        import services.shared_email_crud as crud

        antes = dict(_legada(mundo))
        await crud.run_upsert_shared_email_config("indexacao", _payload(), ADM_DOMUS, _pedido("cmp-domus"))

        assert {k: _legada(mundo)[k] for k in antes} == antes, "a configuração da Power ficou intacta"
        propria = _da_rede(mundo, REDE_DOMUS)
        assert propria and propria["email_address"] == "index@domus.pt"
        assert len(_configs(mundo)) == 2

    @pytest.mark.asyncio
    async def test_o_admin_da_domus_nao_pode_apontar_para_a_rede_da_power_com_o_cabecalho(self, mundo):
        """`X-Company-Id` de uma empresa alheia não muda de rede quem administra."""
        import services.shared_email_crud as crud

        antes = dict(_legada(mundo))
        await crud.run_upsert_shared_email_config("indexacao", _payload(), ADM_DOMUS, _pedido("cmp-power"))
        assert {k: _legada(mundo)[k] for k in antes} == antes
        assert _da_rede(mundo, REDE_DOMUS) is not None, "gravou na PRÓPRIA rede, não na do cabeçalho"

    @pytest.mark.asyncio
    async def test_remover_na_domus_nao_remove_a_da_power(self, mundo):
        import services.shared_email_crud as crud

        with pytest.raises(HTTPException) as exc:
            await crud.run_delete_shared_email_config("indexacao", ADM_DOMUS, _pedido("cmp-domus"))
        assert exc.value.status_code == 404
        assert _legada(mundo)["email_address"] == "index@power.pt"

        await crud.run_upsert_shared_email_config("indexacao", _payload(), ADM_DOMUS, _pedido("cmp-domus"))
        await crud.run_delete_shared_email_config("indexacao", ADM_DOMUS, _pedido("cmp-domus"))
        assert _da_rede(mundo, REDE_DOMUS) is None
        assert _legada(mundo)["email_address"] == "index@power.pt"

    @pytest.mark.asyncio
    async def test_desligar_o_google_na_domus_nao_desliga_o_da_power(self, mundo):
        import services.shared_email_google as google

        with pytest.raises(HTTPException) as exc:
            await google.run_shared_email_google_disconnect("indexacao", ADM_DOMUS, _pedido("cmp-domus"))
        assert exc.value.status_code == 404
        assert _legada(mundo)["google_refresh_token"] == "tok-power"

    @pytest.mark.asyncio
    async def test_a_sincronizacao_manual_da_domus_nunca_usa_a_config_da_power(self, mundo):
        import services.shared_email_sync as sync
        chamada = AsyncMock()
        with patch("services.gmail_api_service.gmail_api_sync_to_db", chamada):
            with pytest.raises(HTTPException) as exc:
                await sync.run_shared_email_manual_sync("indexacao", ADM_DOMUS, _pedido("cmp-domus"))
        assert exc.value.status_code == 404
        chamada.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_sincronizacao_manual_leva_a_rede_da_caixa(self, mundo):
        import services.shared_email_sync as sync
        mundo.shared_role_email_configs.docs.append({
            **CONFIG_LEGADA, "network_id": REDE_DOMUS, "email_address": "index@domus.pt",
            "auth_method": "google_oauth", "google_refresh_token": "tok-domus",
        })
        chamada = AsyncMock(return_value={"success": True, "total_synced": 1})
        with patch("services.gmail_api_service.gmail_api_sync_to_db", chamada):
            await sync.run_shared_email_manual_sync("indexacao", ADM_DOMUS, _pedido("cmp-domus"))
        assert chamada.await_args.kwargs["network_id"] == REDE_DOMUS


# ====================================================================
# 2. ADMINISTRAÇÃO — o contexto de rede e a migração implícita
# ====================================================================

class TestAdministracaoPorRede:
    @pytest.mark.asyncio
    async def test_a_config_legada_e_da_rede_de_omissao_e_carimba_se_ao_editar(self, mundo):
        import services.shared_email_crud as crud

        lista = await crud.run_list_shared_email_configs(ADM_POWER, _pedido("cmp-power"))
        assert [c.email_address for c in lista.configs] == ["index@power.pt"]

        await crud.run_upsert_shared_email_config(
            "indexacao", _payload(email_address="novo@power.pt"), ADM_POWER, _pedido("cmp-power"),
        )
        assert len(_configs(mundo)) == 1, "editou a existente, não criou uma segunda"
        assert _configs(mundo)[0]["network_id"] == REDE_INCUMBENTE
        assert _configs(mundo)[0]["email_address"] == "novo@power.pt"

    @pytest.mark.asyncio
    async def test_o_master_gere_a_caixa_da_empresa_activa(self, mundo):
        import services.shared_email_crud as crud

        await crud.run_upsert_shared_email_config("indexacao", _payload(), MASTER, _pedido("cmp-domus"))
        assert _da_rede(mundo, REDE_DOMUS) is not None
        assert _legada(mundo)["email_address"] == "index@power.pt"

    @pytest.mark.asyncio
    async def test_a_resposta_da_gravacao_nao_leva_segredos_nem_a_rede(self, mundo):
        import services.shared_email_crud as crud

        r = await crud.run_upsert_shared_email_config("indexacao", _payload(), ADM_DOMUS, _pedido("cmp-domus"))
        corpo = r.model_dump()
        assert "encrypted_password" not in corpo and "google_refresh_token" not in corpo
        assert r.has_imap_password is True

    @pytest.mark.asyncio
    async def test_o_inicio_do_oauth_grava_a_rede_do_administrador_no_state(self, mundo):
        import services.shared_email_google as google

        fluxo = MagicMock()
        fluxo.authorization_url.return_value = ("https://accounts.google.com/x", "s")
        flow_cls = MagicMock()
        flow_cls.from_client_config.return_value = fluxo
        pedido = MagicMock(headers={"X-Company-Id": "cmp-domus", "host": "api.x"}, state=MagicMock(spec=[]))
        with patch("google_auth_oauthlib.flow.Flow", flow_cls), \
                patch.object(google, "_get_google_config", return_value={
                    "client_id": "c", "client_secret": "s", "scopes": [], "redirect_uri": "https://x/cb"}):
            await google.run_shared_email_google_login("indexacao", pedido, ADM_DOMUS)
        assert [d["network_id"] for d in mundo.oauth_states.docs] == [REDE_DOMUS]

    @pytest.mark.asyncio
    async def test_o_estado_do_oauth_fixa_a_rede_no_inicio_do_fluxo(self, mundo):
        """O callback é anónimo: a rede vem do `state` que o admin autenticado criou."""
        import services.shared_email_google as google

        mundo.oauth_states.docs.append({
            "_id": "oid-1", "state": "s1", "user_id": "adm-domus", "shared_role": "indexacao",
            "network_id": REDE_DOMUS, "redirect_uri": "https://x/cb", "email_address": "index@domus.pt",
        })
        credenciais = MagicMock(refresh_token="rt-domus")
        fluxo = MagicMock(credentials=credenciais)
        flow_cls = MagicMock()
        flow_cls.from_client_config.return_value = fluxo
        servico = MagicMock()
        servico.users.return_value.getProfile.return_value.execute.return_value = {"emailAddress": "index@domus.pt"}
        with patch("google_auth_oauthlib.flow.Flow", flow_cls), \
                patch("googleapiclient.discovery.build", return_value=servico), \
                patch.object(google, "_get_google_config", return_value={
                    "client_id": "c", "client_secret": "s", "scopes": [], "redirect_uri": "https://x/cb"}):
            r = await google.run_shared_email_google_callback(MagicMock(headers={}), "codigo", state="s1")
        assert r.status_code == 200
        propria = _da_rede(mundo, REDE_DOMUS)
        assert propria and propria["google_email"] == "index@domus.pt"
        assert _legada(mundo)["google_refresh_token"] == "tok-power", "o OAuth da Domus não tocou na caixa da Power"


# ====================================================================
# 3. ESCRITA — o email herda a rede da caixa
# ====================================================================

class TestOEmailHerdaARedeDaCaixa:
    def test_o_carimbo_da_caixa(self, rede_de_omissao_incumbente):
        from services.shared_mailbox_scope import carimbo_da_caixa

        assert carimbo_da_caixa({"network_id": REDE_DOMUS}) == {"network_id": REDE_DOMUS}
        assert carimbo_da_caixa(dict(CONFIG_LEGADA)) == {"network_id": REDE_INCUMBENTE}, "legada = rede de omissão"

    def test_sem_rede_de_omissao_a_caixa_legada_fica_por_carimbar(self, monkeypatch):
        from services.shared_mailbox_scope import carimbo_da_caixa

        monkeypatch.delenv("TENANT_DEFAULT_NETWORK_ID", raising=False)
        assert carimbo_da_caixa(dict(CONFIG_LEGADA)) == {}

    @pytest.mark.asyncio
    async def test_o_mesmo_message_id_nas_duas_redes_nao_e_duplicado(self, mundo):
        from services.shared_mailbox_scope import duplicado_da_caixa

        mundo.emails.docs.append({**E_POWER, "message_id": "<m1>"})
        da_power = duplicado_da_caixa("<m1>", "indexacao", {"network_id": REDE_INCUMBENTE})
        da_domus = duplicado_da_caixa("<m1>", "indexacao", {"network_id": REDE_DOMUS})
        assert await mundo.emails.find_one(da_power) is not None
        assert await mundo.emails.find_one(da_domus) is None, "a Domus tem direito à sua cópia"

    @pytest.mark.asyncio
    async def test_a_sincronizacao_imap_carimba_e_nao_confunde_redes(self, mundo):
        import services.email_service as es

        mundo.shared_role_email_configs.docs.append({
            **CONFIG_LEGADA, "network_id": REDE_DOMUS, "email_address": "index@domus.pt",
            "encrypted_password": "ENC:domus", "google_refresh_token": "",
        })
        mundo.emails.docs.append({**E_POWER, "message_id": "<igual>"})
        entrada = {
            "message_id": "<igual>", "subject": "Olá", "from_email": "cli@b.pt", "to_emails": ["index@domus.pt"],
            "date": "2026-10-01T10:00:00+00:00", "body": "corpo", "direction": "received",
        }

        def _fetch(account, pasta, dias, maximo):
            return {"emails": [dict(entrada)] if pasta == "INBOX" else []}

        with patch.object(es, "_fetch_all_from_folder_sync", _fetch), \
                patch("services.encryption.encryption_service.decrypt", return_value="pw"), \
                patch("services.email_realtime.notify_new_email_for_shared_role", AsyncMock(return_value=0)), \
                patch.dict("os.environ", {"EMAIL_SYNC_ENABLED": "true"}):
            r = await es.sync_shared_role_emails("indexacao", network_id=REDE_DOMUS)

        assert r["success"] and r["total_synced"] == 1 and r["total_duplicates"] == 0
        novo = next(e for e in mundo.emails.docs if e.get("network_id") == REDE_DOMUS)
        assert novo["shared_role"] == "indexacao" and novo["message_id"] == "<igual>"

    @pytest.mark.asyncio
    async def test_a_sincronizacao_gmail_carimba_com_a_rede_da_caixa_e_nao_confunde_redes(self, mundo):
        import services.gmail_api_service as gas

        mundo.shared_role_email_configs.docs.append({
            **CONFIG_LEGADA, "network_id": REDE_DOMUS, "email_address": "index@domus.pt",
            "google_refresh_token": "ENC:tok-domus",
        })
        # O MESMO Message-ID já existe na caixa da Power.
        mundo.emails.docs.append({**E_POWER, "message_id": "<g1>", "source": "gmail_api"})
        servico = MagicMock()
        servico.users.return_value.messages.return_value.list.return_value.execute.return_value = {
            "messages": [{"id": "g1"}]
        }
        servico.users.return_value.messages.return_value.get.return_value.execute.return_value = {}
        analisado = {
            "message_id": "<g1>", "gmail_message_id": "g1", "direction": "received",
            "from_email": "cli@b.pt", "to_emails": ["index@domus.pt"], "subject": "Olá",
            "date": "2026-10-01T10:00:00+00:00",
        }
        with patch.object(gas, "_build_gmail_service", return_value=servico), \
                patch.object(gas, "_parse_gmail_message", return_value=analisado), \
                patch.object(gas.encryption_service, "decrypt", return_value="tok"), \
                patch("services.email_realtime.notify_new_email_for_shared_role", AsyncMock(return_value=0)):
            r = await gas.gmail_api_sync_to_db("indexacao", network_id=REDE_DOMUS)

        assert r["success"] and r["total_synced"] == 1 and r["total_duplicates"] == 0
        novo = next(e for e in mundo.emails.docs if e.get("network_id") == REDE_DOMUS)
        assert novo["shared_role"] == "indexacao" and novo["account"] == "gmail_indexacao"
        assert next(c for c in _configs(mundo) if c.get("network_id") == REDE_DOMUS)["total_emails_synced"] == 1
        assert "total_emails_synced" not in _legada(mundo) or _legada(mundo)["total_emails_synced"] == 0

    @pytest.mark.asyncio
    async def test_sem_config_na_rede_nao_ha_sincronizacao_nem_recurso_ao_sistema(self, mundo):
        import services.email_service as es

        with patch.dict("os.environ", {"EMAIL_SYNC_ENABLED": "true"}):
            r = await es.sync_shared_role_emails("indexacao", network_id=REDE_DOMUS)
        assert r["success"] is False and "esta rede" in r["error"]

    @pytest.mark.asyncio
    async def test_o_gmail_sync_so_alcanca_a_config_da_rede_pedida(self, mundo):
        from services.gmail_api_service import get_shared_email_config

        assert (await get_shared_email_config("indexacao", REDE_DOMUS)) is None
        assert (await get_shared_email_config("indexacao", REDE_INCUMBENTE))["email_address"] == "index@power.pt"
        # Esquecer a rede fecha: só a pilha antiga, nunca uma rede concreta. A da
        # Domus entra PRIMEIRO na colecção — um `find_one` sem fronteira devolvia-a.
        mundo.shared_role_email_configs.docs.insert(
            0, {**CONFIG_LEGADA, "network_id": REDE_DOMUS, "email_address": "d@d.pt"},
        )
        assert (await get_shared_email_config("indexacao"))["email_address"] == "index@power.pt"
        assert (await get_shared_email_config("indexacao", None))["email_address"] == "index@power.pt"

    @pytest.mark.asyncio
    async def test_o_worker_percorre_pares_cargo_rede(self, mundo):
        from services.shared_mailbox_scope import caixas_a_sincronizar

        mundo.shared_role_email_configs.docs.append({**CONFIG_LEGADA, "network_id": REDE_DOMUS})
        assert sorted(await caixas_a_sincronizar(), key=lambda p: p[1]) == sorted(
            [("indexacao", REDE_INCUMBENTE), ("indexacao", REDE_DOMUS)], key=lambda p: p[1],
        )


# ====================================================================
# 4. LEITURA — o cargo só vale dentro da rede
# ====================================================================

class TestACaixaDoCargoSoDentroDaRede:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("email,utilizador,pode", [
        (E_POWER, IDX_POWER, True),
        (E_POWER, IDX_DOMUS, False),
        (E_DOMUS, IDX_DOMUS, True),
        (E_DOMUS, IDX_POWER, False),
        (E_LEGADO, IDX_POWER, True),
        (E_LEGADO, IDX_DOMUS, False),
        (E_POWER, MASTER, True),
        (E_DOMUS, MASTER, True),
    ])
    async def test_quem_le_o_email_da_caixa_partilhada(self, mundo, email, utilizador, pode):
        from services.email_access import pode_ler_email

        assert await pode_ler_email(dict(email), dict(utilizador)) is pode

    @pytest.mark.asyncio
    async def test_a_config_do_cargo_na_rede_de_quem_pergunta(self, mundo):
        from services.shared_mailbox_scope import config_do_utilizador

        mundo.shared_role_email_configs.docs.append({**CONFIG_LEGADA, "network_id": REDE_DOMUS, "email_address": "d@d.pt"})
        assert (await config_do_utilizador("indexacao", IDX_POWER))["email_address"] == "index@power.pt"
        assert (await config_do_utilizador("indexacao", IDX_DOMUS))["email_address"] == "d@d.pt"

    @pytest.mark.asyncio
    async def test_uma_rede_sem_caixa_nao_herda_a_de_outra(self, mundo):
        from services.shared_mailbox_scope import config_do_utilizador

        assert await config_do_utilizador("indexacao", IDX_DOMUS) is None

    @pytest.mark.asyncio
    async def test_a_conta_de_envio_do_cargo_e_a_da_rede(self, mundo):
        """Antes: o IDX da Domus resolvia a config da Power (com o refresh token dela)."""
        import services.email_config_resolver as ecr

        assert await ecr._load_shared_role_config("indexacao", IDX_DOMUS) is None
        ok = await ecr._load_shared_role_config("indexacao", IDX_POWER)
        assert ok and ok["email_address"] == "index@power.pt"

    @pytest.mark.asyncio
    async def test_a_condicao_dos_emails_da_caixa(self, mundo):
        from services.shared_mailbox_scope import condicao_de_emails_da_caixa
        from tests.unit.helpers_tenant import casa

        cond_domus = await condicao_de_emails_da_caixa("indexacao", IDX_DOMUS)
        cond_power = await condicao_de_emails_da_caixa("indexacao", IDX_POWER)
        assert [casa(e, cond_domus) for e in (E_POWER, E_DOMUS, E_LEGADO)] == [False, True, False]
        assert [casa(e, cond_power) for e in (E_POWER, E_DOMUS, E_LEGADO)] == [True, False, True]


# ====================================================================
# 5. O WEBMAIL — lista, não lidos e estatísticas
# ====================================================================

class TestOWebmail:
    @pytest.fixture
    def emails(self, mundo):
        for base in (E_LEGADO, E_POWER, E_DOMUS):
            mundo.emails.docs.append({
                **base, "direction": "received", "status": "synced", "is_read": False, "is_archived": False,
                "sent_at": "2026-10-01T10:00:00+00:00", "subject": base["id"], "body": "x",
            })
        return mundo

    @pytest.mark.asyncio
    @pytest.mark.parametrize("utilizador,esperado", [
        (IDX_POWER, {"e-leg", "e-pw"}),
        (IDX_DOMUS, {"e-dm"}),
        (MASTER, {"e-leg", "e-pw", "e-dm"}),
    ])
    async def test_a_lista_da_caixa_partilhada_so_mostra_a_rede(self, emails, utilizador, esperado):
        import services.email_webmail as ew

        with patch.object(ew, "enrich_emails", AsyncMock(side_effect=lambda x: x)), \
                patch.object(ew, "_user_ucr_roles", AsyncMock(return_value={"indexacao", "master"})), \
                patch("services.auth.get_effective_role_async", AsyncMock(return_value=utilizador["role"])), \
                patch.object(ew, "get_user_mailbox_addresses", AsyncMock(return_value=[]), create=True):
            r = await ew.run_webmail_list(_pedido(), dict(utilizador), box="shared_indexacao")
        assert {e["id"] for e in r["emails"]} == esperado
        assert r["total"] == len(esperado)
        assert r["unread_count"] == len(esperado)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("utilizador,esperado", [(IDX_POWER, 2), (IDX_DOMUS, 1)])
    async def test_as_estatisticas_da_caixa_partilhada_contam_so_a_rede(self, emails, utilizador, esperado):
        """O duplo não faz `$facet`: capta-se o pipeline e avalia-se cada `$match` sobre os emails."""
        import services.email_webmail as ew
        from tests.unit.helpers_tenant import casa

        captado = {}

        class _Agregacao:
            def __init__(self, pipeline):
                captado["pipeline"] = pipeline

            async def to_list(self, _n):
                return []

        with patch.object(emails.emails, "aggregate", lambda pipeline: _Agregacao(pipeline)), \
                patch.object(ew, "_user_ucr_roles", AsyncMock(return_value={"indexacao"})), \
                patch("services.auth.get_effective_role_async", AsyncMock(return_value=utilizador["role"])):
            await ew.run_webmail_stats(dict(utilizador), box="shared_indexacao", request=_pedido())

        facetas = captado["pipeline"][0]["$facet"]
        for nome in ("unread", "inbox", "starred", "trash", "sent", "drafts", "sent_today"):
            assert "$match" in facetas[nome][0], nome
        inbox = facetas["inbox"][0]["$match"]
        unread = facetas["unread"][0]["$match"]
        todos = [dict(d) for d in emails.emails.docs]
        assert sum(casa(e, inbox) for e in todos) == esperado
        assert sum(casa(e, unread) for e in todos) == esperado
        # Toda a faceta, não só a da caixa de entrada: a rede entra em TODOS os contadores.
        for nome in ("sent", "starred", "trash", "drafts", "sent_today"):
            match = facetas[nome][0]["$match"]
            assert not any(casa({**e, "is_starred": True, "is_archived": True, "status": "draft",
                                 "direction": "sent", "sent_at": "2999"}, match) and e.get("network_id") == (
                REDE_DOMUS if utilizador is IDX_POWER else REDE_INCUMBENTE) for e in todos), nome

    @pytest.mark.asyncio
    async def test_a_caixa_pessoal_nao_leva_a_condicao_de_rede(self, mundo):
        import services.email_webmail as ew

        assert await ew.condicao_de_rede_das_caixas("personal", dict(IDX_DOMUS)) is None
        assert await ew.condicao_de_rede_das_caixas(None, dict(IDX_DOMUS)) is None
        assert await ew.condicao_de_rede_das_caixas("shared_indexacao", dict(IDX_DOMUS))
        assert await ew.condicao_de_rede_das_caixas("general", dict(IDX_DOMUS))
        # O Master não tem fronteira: nenhuma condição a acrescentar.
        assert await ew.condicao_de_rede_das_caixas("shared_indexacao", dict(MASTER)) is None


class TestOSyncDoUtilizadorDoCargo:
    @pytest.fixture
    def sistema_configurado(self):
        sistema = MagicMock(imap_host="imap.sistema.pt", email_user="sistema@power.pt", app_password="x", imap_port=993)
        with patch("services.system_config.get_system_config", AsyncMock(return_value=MagicMock(system_webmail=sistema))):
            yield

    async def _sincronizar(self, utilizador):
        import services.email_webmail as ew

        with patch("services.auth.get_effective_role_async", AsyncMock(return_value=utilizador["role"])), \
                patch("services.auth.get_active_company_id_async", AsyncMock(return_value=None)), \
                patch.object(ew, "_user_ucr_roles", AsyncMock(return_value={"indexacao"})):
            return await ew.run_webmail_sync_user(_pedido(), dict(utilizador))

    @pytest.mark.asyncio
    async def test_uma_ilha_sem_caixa_propria_nao_herda_a_caixa_de_sistema(self, mundo, sistema_configurado):
        r = await self._sincronizar(IDX_DOMUS)
        assert r["success"] is False and "sua rede" in r["error"]

    @pytest.mark.asyncio
    async def test_o_grupo_incumbente_sem_caixa_propria_continua_a_usar_a_de_sistema(self, mundo, sistema_configurado):
        """Contraprova: o recurso à caixa de sistema não desapareceu, ficou para a pilha antiga."""
        mundo.shared_role_email_configs.docs.clear()
        job = MagicMock()
        job.create_job = AsyncMock(return_value="j1")
        with patch("services.background_jobs.BackgroundJobService", return_value=job), \
                patch("services.background_tasks.spawn_background_task", lambda coro, **k: coro.close()):
            r = await self._sincronizar(IDX_POWER)
        assert r["success"] is True and r["job_id"] == "j1"


# ====================================================================
# 6. O AVISO EM TEMPO REAL
# ====================================================================

class TestOAvisoEmTempoReal:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("email,esperado", [
        (E_POWER, {"idx-power"}),
        (E_DOMUS, {"idx-domus"}),
        (E_LEGADO, {"idx-power"}),
    ])
    async def test_a_caixa_partilhada_so_avisa_a_rede_do_email(self, mundo, email, esperado):
        import services.email_realtime as rt

        enviar = AsyncMock(return_value=1)
        with patch.object(rt, "notify_new_email", enviar):
            await rt.notify_new_email_for_shared_role("indexacao", dict(email))
        assert set(enviar.await_args.args[0]) == esperado

    @pytest.mark.asyncio
    async def test_a_caixa_geral_so_avisa_o_staff_da_rede(self, mundo):
        import services.email_realtime as rt

        mundo.users.docs.append({"id": "dir-domus", "role": "diretor", "email": "d@domus.pt", "is_active": True})
        mundo.user_company_roles.docs.append(
            {"user_id": "dir-domus", "company_id": "cmp-domus", "company_name": "Domus", "role": "diretor"}
        )
        mundo.users.docs.append({"id": "dir-power", "role": "diretor", "email": "d@power.pt", "is_active": True})
        mundo.user_company_roles.docs.append(
            {"user_id": "dir-power", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "diretor"}
        )
        enviar = AsyncMock(return_value=1)
        email = {"id": "g", "shared_role": "geral", "network_id": REDE_DOMUS, "direction": "received",
                 "to_emails": ["geral@domus.pt"]}
        with patch.object(rt, "notify_new_email", enviar):
            await rt.notify_new_email_for_global_mailbox(email)
        avisados = set(enviar.await_args.args[0])
        assert "dir-domus" in avisados and "adm-domus" in avisados
        assert not avisados & {"dir-power", "adm-power", "idx-power"}, "nada da Power"
        assert "master" in avisados, "o Master não tem fronteira"

    @pytest.mark.asyncio
    async def test_um_email_por_carimbar_so_avisa_o_grupo_incumbente(self, mundo):
        from services.shared_mailbox_scope import destinatarios_da_caixa

        assert await destinatarios_da_caixa("indexacao", {"shared_role": "indexacao"}) == ["idx-power"]


# ====================================================================
# 7. MIGRAÇÃO
# ====================================================================

class TestAMigracao:
    @pytest.fixture
    def com_emails(self, mundo):
        mundo.emails.docs.extend([
            {**E_LEGADO}, {**E_POWER}, {**E_DOMUS},
            {"id": "pessoal", "synced_for_user": "u1"},  # sem shared_role: NÃO se toca
        ])
        return mundo

    @pytest.mark.asyncio
    async def test_a_omissao_so_le(self, com_emails):
        from scripts import backfill_shared_mailbox_network_id as mig

        antes = [dict(c) for c in com_emails.shared_role_email_configs.docs]
        plano = await mig.planear(com_emails, REDE_INCUMBENTE)
        assert plano["configs_por_carimbar"] == 1 and plano["emails_por_carimbar"] == 1
        assert [dict(c) for c in com_emails.shared_role_email_configs.docs] == antes

    @pytest.mark.asyncio
    async def test_aplicar_carimba_so_o_que_falta_e_e_idempotente(self, com_emails):
        from scripts import backfill_shared_mailbox_network_id as mig

        escrito = await mig.aplicar(com_emails, REDE_INCUMBENTE)
        assert escrito["configs_carimbadas"] == 1 and escrito["emails_carimbados"] == 1
        assert _legada_ou_none(com_emails) is None
        por_id = {e["id"]: e for e in com_emails.emails.docs}
        assert por_id["e-leg"]["network_id"] == REDE_INCUMBENTE
        assert por_id["e-dm"]["network_id"] == REDE_DOMUS, "nunca sobrepõe um carimbo"
        assert "network_id" not in por_id["pessoal"], "os emails pessoais não são desta migração"
        segunda = await mig.aplicar(com_emails, REDE_INCUMBENTE)
        assert segunda["configs_carimbadas"] == 0 and segunda["emails_carimbados"] == 0

    def test_recusa_se_sem_rede(self, monkeypatch):
        from scripts import backfill_shared_mailbox_network_id as mig

        monkeypatch.delenv("TENANT_DEFAULT_NETWORK_ID", raising=False)
        with pytest.raises(mig.RedeIndeterminada):
            mig.rede_a_carimbar(None)
        assert mig.rede_a_carimbar("rede-x") == "rede-x"

    def test_a_omissao_vem_da_rede_de_omissao(self, rede_de_omissao_incumbente):
        from scripts import backfill_shared_mailbox_network_id as mig

        assert mig.rede_a_carimbar(None) == REDE_INCUMBENTE

    def test_o_script_so_escreve_o_campo_network_id(self):
        fonte = (BACKEND / "scripts" / "backfill_shared_mailbox_network_id.py").read_text()
        sets = [n for n in ast.walk(ast.parse(fonte)) if isinstance(n, ast.Dict)
                and any(isinstance(k, ast.Constant) and k.value == "$set" for k in n.keys)]
        assert sets, "contraprova: o leitor encontrou os $set"
        for d in sets:
            for k, v in zip(d.keys, d.values):
                if isinstance(k, ast.Constant) and k.value == "$set":
                    assert ast.unparse(v) == "{'network_id': rede}"


def _legada_ou_none(bd):
    return next((c for c in bd.shared_role_email_configs.docs if not c.get("network_id")), None)


# ====================================================================
# 8. INVENTÁRIOS POR AST — um acesso novo à colecção tem de dizer a rede
# ====================================================================

#: Escritos com motivo: o único acesso fora do módulo de âmbito que não usa o
#: filtro de (cargo, rede) é a listagem do worker, que percorre TODAS as caixas
#: e passa a cada uma a SUA rede (`rede_da_config`).
EXCEPCOES = {("services/webmail_worker_sync.py", "find")}
METODOS = {"find_one", "find", "update_one", "update_many", "delete_one", "delete_many", "count_documents"}


def _acessos():
    encontrados = []
    for pasta in ("services", "routes"):
        for ficheiro in (BACKEND / pasta).rglob("*.py"):
            fonte = ficheiro.read_text()
            if "shared_role_email_configs" not in fonte:
                continue
            for no in ast.walk(ast.parse(fonte)):
                if (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
                        and no.func.attr in METODOS
                        and ast.unparse(no.func.value) == "db.shared_role_email_configs"):
                    encontrados.append((str(ficheiro.relative_to(BACKEND)), no))
    return encontrados


class TestInventarios:
    def test_o_inventario_le_mesmo_os_acessos(self):
        acessos = _acessos()
        assert len(acessos) >= 8, "contraprova: o leitor encontrou os acessos à colecção"
        assert any(f.endswith("shared_email_crud.py") for f, _ in acessos)

    def test_nenhum_acesso_identifica_a_caixa_so_pelo_cargo(self):
        """Um filtro `{"role": ...}` à mão é o defeito original."""
        for ficheiro, no in _acessos():
            if (ficheiro, no.func.attr) in EXCEPCOES or ficheiro.endswith("shared_mailbox_scope.py"):
                continue
            primeiro = no.args[0] if no.args else None
            assert not (isinstance(primeiro, ast.Dict) and any(
                isinstance(k, ast.Constant) and k.value == "role" for k in primeiro.keys
            )), f"{ficheiro}:{no.lineno} identifica a caixa só pelo cargo"

    def test_a_excepcao_do_worker_existe(self):
        assert ("services/webmail_worker_sync.py", "find") in {(f, n.func.attr) for f, n in _acessos()}

    def test_todos_os_endpoints_de_administracao_recebem_o_pedido(self):
        """Sem o `Request` não há `X-Company-Id` e a rede cai na de omissão."""
        import routes.shared_email as rota

        arvore = ast.parse(inspect.getsource(rota))
        endpoints = [n for n in arvore.body if isinstance(n, ast.AsyncFunctionDef) and n.decorator_list]
        assert len(endpoints) >= 7
        for fn in endpoints:
            nomes = [a.arg for a in fn.args.args]
            assert "request" in nomes, fn.name

    def test_nenhum_leitor_filtra_emails_por_cargo_sem_rede(self):
        """`{"shared_role": <cargo variável>}` à mão nas leituras do utilizador."""
        proibido = '{"shared_role": user_role'
        for modulo in ("email_process_crud.py", "email_webmail.py", "email_access.py"):
            assert proibido not in (BACKEND / "services" / modulo).read_text(), modulo

    def test_a_lista_as_estatisticas_e_os_nao_lidos_usam_a_condicao_de_rede(self):
        import services.email_webmail as ew

        assert "condicao_de_rede_das_caixas" in inspect.getsource(ew.run_webmail_list)
        assert "condicao_de_rede_das_caixas" in inspect.getsource(ew.run_webmail_stats)

    def test_todo_chamador_dos_sincronizadores_diz_a_rede(self):
        """`gmail_api_sync_to_db` e `sync_shared_role_emails` sem `network_id` só alcançam a
        caixa antiga: um chamador novo que se esqueça deixa a rede dele sem sincronizar."""
        chamadores = []
        for ficheiro in (BACKEND / "services").rglob("*.py"):
            fonte = ficheiro.read_text()
            for no in ast.walk(ast.parse(fonte)):
                if (isinstance(no, ast.Call) and isinstance(no.func, (ast.Name, ast.Attribute))):
                    nome = no.func.id if isinstance(no.func, ast.Name) else no.func.attr
                    if nome in {"gmail_api_sync_to_db", "sync_shared_role_emails"}:
                        chamadores.append((ficheiro.name, nome, {k.arg for k in no.keywords}))
        assert len(chamadores) >= 6, "contraprova: o leitor encontrou os chamadores"
        for ficheiro, nome, kwargs in chamadores:
            assert "network_id" in kwargs, f"{ficheiro}: {nome}() sem network_id"

    def test_o_indice_esta_declarado_em_db_indexes(self):
        fonte = (BACKEND / "services" / "db_indexes.py").read_text()
        assert "idx_shared_role_configs_cargo_rede" in fonte
