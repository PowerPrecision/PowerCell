"""
Formulário público POR REDE (multi-tenant, Out 2026, D-37).

O PEDIDO
  O registo deixa de ser genérico e global: cada empresa tem o seu formulário
  público. O `form_config` é isolado por `network_id`; o link de registo leva o
  identificador da empresa e carrega ESTRITAMENTE o formulário dessa rede; a
  administração (Master/Admin/CEO) edita só o da rede em contexto.

COMO SE TESTA
  O cenário tem DUAS redes cujos formulários diferem de propósito — a Domus pergunta
  um campo que a Power/Precision não pergunta, e vice-versa. É isto que distingue
  «um formulário por rede» de «o mesmo formulário lido de um sítio diferente».

  * o ATAQUE primeiro: um administrador de uma rede não escreve no formulário de
    outra, nem no modelo; um link com uma empresa que não existe não cai no
    formulário de outra;
  * o link público carrega o formulário DA empresa do link;
  * o Portal do cliente e o parceiro usam o formulário da rede do CLIENTE/da LEAD;
  * o registo carimba o cliente com a empresa do link;
  * inventário por AST: nenhum acesso a `db.form_config` sem dizer de que rede.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from services import form_config_scope as fcs
from services.auth import get_current_user
from tests.unit.helpers_tenant import (  # noqa: F401  (rede_de_omissao_incumbente é fixture)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

BACKEND = Path(__file__).resolve().parents[2]


def _campo(chave, passo=1, ordem=1, **extra):
    return {
        "field_key": chave, "label": chave.replace("_", " ").title(), "step": passo,
        "order": ordem, "is_visible": True, "is_required": False, "field_type": "text", **extra,
    }


#: O MODELO (sem `network_id`): o formulário que existia antes da migração.
MODELO = {"type": "public_form", "fields": [_campo("name"), _campo("email", ordem=2)], "step_config": {}, "step_labels": {}}
#: Power/Precision: o modelo mais um campo seu.
FORMULARIO_INCUMBENTE = {
    "type": "public_form", "network_id": REDE_INCUMBENTE,
    "fields": [_campo("name"), _campo("email", ordem=2), _campo("custom_power", ordem=3, is_custom=True)],
    "step_config": {}, "step_labels": {"1": "Dados Power"},
}
#: Domus: outro formulário (sem o email, com um campo próprio).
FORMULARIO_DOMUS = {
    "type": "public_form", "network_id": REDE_DOMUS,
    "fields": [_campo("name"), _campo("custom_domus", ordem=2, is_custom=True)],
    "step_config": {}, "step_labels": {"1": "Dados Domus"},
}

POWER_ADMIN = {"id": "u-admin", "role": "admin", "effective_role": "admin", "name": "Admin Power"}
DOMUS_ADMIN = {"id": "u-admin-domus", "role": "admin", "effective_role": "admin", "name": "Admin Domus"}
CEO = {"id": "u-ceo", "role": "ceo", "effective_role": "ceo", "name": "CEO"}
MASTER = {"id": "u-master", "role": "master", "effective_role": "master", "name": "Master"}


def _pedido(company_id=None):
    headers = {"X-Company-Id": company_id} if company_id else {}
    return MagicMock(headers=headers, state=MagicMock(spec=[]))


def _chaves(campos):
    return [c["field_key"] for c in campos]


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    import services.form_config_fields as ff
    import services.form_config_templates as ft
    import services.workflow_scope as ws

    semear(fake_async_db)
    fake_async_db.form_config.docs.extend(dict(d) for d in (MODELO, FORMULARIO_INCUMBENTE, FORMULARIO_DOMUS))
    fake_async_db.user_company_roles.docs.extend([
        {"user_id": "u-admin", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "admin", "is_default": True},
        {"user_id": "u-admin-domus", "company_id": "cmp-domus", "company_name": "Domus",
         "role": "admin", "is_default": True},
        {"user_id": "u-ceo", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "ceo", "is_default": True},
        {"user_id": "u-master", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "master", "is_default": True},
    ])
    async def _empresa_activa(request, user):
        return request.headers.get("X-Company-Id") or ""

    with tenant_db(fake_async_db, fcs, ff, ft, ws), \
            patch("services.auth.get_active_company_id_async", _empresa_activa):
        yield fake_async_db


def _doc(bd, rede):
    return next((d for d in bd.form_config.docs if d.get("network_id") == rede), None)


def _modelo(bd):
    return next(d for d in bd.form_config.docs if not d.get("network_id"))


# ====================================================================
# O ATAQUE: o que uma rede NUNCA pode fazer à outra
# ====================================================================

class TestAExploracao:
    @pytest.mark.asyncio
    async def test_um_link_com_empresa_inexistente_nao_cai_no_formulario_de_outra(self, mundo):
        with pytest.raises(HTTPException) as erro:
            await fcs.rede_do_link_publico("cmp-que-nao-existe")
        assert erro.value.status_code == 404

    @pytest.mark.asyncio
    async def test_o_nome_da_empresa_nao_e_um_identificador(self, mundo):
        """Dois homónimos escolhiam o formulário à sorte: só o `id` serve."""
        with pytest.raises(HTTPException) as erro:
            await fcs.rede_do_link_publico("Domus")
        assert erro.value.status_code == 404

    @pytest.mark.asyncio
    async def test_uma_empresa_inactiva_nao_serve_formulario(self, mundo):
        for e in mundo.companies.docs:
            if e["id"] == "cmp-domus":
                e["is_active"] = False
        with pytest.raises(HTTPException) as erro:
            await fcs.rede_do_link_publico("cmp-domus")
        assert erro.value.status_code == 404

    @pytest.mark.asyncio
    async def test_o_admin_da_power_escreve_so_no_formulario_da_power(self, mundo):
        import services.form_config_fields as ff

        antes_domus = dict(_doc(mundo, REDE_DOMUS))
        antes_modelo = dict(_modelo(mundo))
        await ff.run_update_form_config(
            ff.FormConfigUpdate(fields=[_campo("name"), _campo("so_power")]), POWER_ADMIN, _pedido("cmp-power"))
        assert _chaves(_doc(mundo, REDE_INCUMBENTE)["fields"]) == ["name", "so_power"]
        assert _doc(mundo, REDE_DOMUS) == antes_domus
        assert _modelo(mundo) == antes_modelo

    @pytest.mark.asyncio
    async def test_o_admin_nao_pede_a_rede_dos_outros_pelo_cabecalho(self, mundo):
        """O `X-Company-Id` de uma empresa alheia não muda de rede quem edita."""
        import services.form_config_fields as ff

        await ff.run_update_form_config(
            ff.FormConfigUpdate(fields=[_campo("name"), _campo("tentativa")]), POWER_ADMIN, _pedido("cmp-domus"))
        assert "tentativa" not in _chaves(_doc(mundo, REDE_DOMUS)["fields"])
        assert "tentativa" in _chaves(_doc(mundo, REDE_INCUMBENTE)["fields"])

    @pytest.mark.asyncio
    async def test_o_modelo_nunca_se_edita_por_esta_via(self, mundo):
        import services.form_config_fields as ff

        mundo.form_config.docs[:] = [d for d in mundo.form_config.docs if d.get("network_id") != REDE_INCUMBENTE]
        antes = dict(_modelo(mundo))
        await ff.run_update_form_config(
            ff.FormConfigUpdate(fields=[_campo("name"), _campo("novo")]), POWER_ADMIN, _pedido())
        assert _modelo(mundo) == antes
        assert _chaves(_doc(mundo, REDE_INCUMBENTE)["fields"]) == ["name", "novo"]


# ====================================================================
# LER: o link público
# ====================================================================

class TestOLinkPublico:
    @pytest.mark.asyncio
    async def test_cada_empresa_carrega_o_formulario_da_sua_rede(self, mundo):
        from services.public_form_config import run_get_public_form_config

        domus = (await run_get_public_form_config(MagicMock(), "cmp-domus")).body
        power = (await run_get_public_form_config(MagicMock(), "cmp-power")).body
        import json

        domus, power = json.loads(domus), json.loads(power)
        assert "custom_domus" in _chaves(domus["all_fields"]) and "custom_power" not in _chaves(domus["all_fields"])
        assert "custom_power" in _chaves(power["all_fields"]) and "custom_domus" not in _chaves(power["all_fields"])
        assert domus["step_labels"] == {"1": "Dados Domus"}
        assert domus["empresa"] == {"id": "cmp-domus", "nome": "Domus"}

    @pytest.mark.asyncio
    async def test_duas_empresas_da_mesma_rede_partilham_o_formulario(self, mundo):
        from services.public_form_config import run_get_public_form_config
        import json

        a = json.loads((await run_get_public_form_config(MagicMock(), "cmp-power")).body)
        b = json.loads((await run_get_public_form_config(MagicMock(), "cmp-precision")).body)
        assert _chaves(a["all_fields"]) == _chaves(b["all_fields"])
        assert a["empresa"]["id"] != b["empresa"]["id"]

    @pytest.mark.asyncio
    async def test_um_link_antigo_sem_empresa_usa_a_rede_de_omissao(self, mundo):
        from services.public_form_config import run_get_public_form_config
        import json

        corpo = json.loads((await run_get_public_form_config(MagicMock(), None)).body)
        assert "custom_power" in _chaves(corpo["all_fields"])
        assert corpo["empresa"] is None

    @pytest.mark.asyncio
    async def test_uma_rede_sem_formulario_proprio_recebe_o_modelo(self, mundo):
        mundo.form_config.docs[:] = [d for d in mundo.form_config.docs if d.get("network_id") != REDE_DOMUS]
        from services.public_form_config import load_merged_form_fields

        campos = await load_merged_form_fields(REDE_DOMUS)
        assert "custom_domus" not in _chaves(campos)
        assert "custom_power" not in _chaves(campos)

    @pytest.mark.asyncio
    async def test_um_link_com_empresa_desconhecida_e_404_por_http(self, mundo):
        from routes import public as rota

        app = FastAPI()
        app.include_router(rota.router)
        with patch("middleware.rate_limit.limiter.enabled", False, create=True):
            c = TestClient(app, raise_server_exceptions=False)
            r = c.get("/public/form-config?empresa=cmp-que-nao-existe")
            assert r.status_code == 404
            ok = c.get("/public/form-config?empresa=cmp-domus")
            assert ok.status_code == 200 and "custom_domus" in _chaves(ok.json()["all_fields"])


# ====================================================================
# ESCREVER: copy-on-write na rede em contexto
# ====================================================================

class TestEditarSoARedeEmContexto:
    @pytest.mark.asyncio
    async def test_a_primeira_escrita_materializa_a_copia_do_modelo(self, mundo):
        import services.form_config_fields as ff

        mundo.form_config.docs[:] = [d for d in mundo.form_config.docs if d.get("network_id") != REDE_DOMUS]
        modelo_antes = dict(_modelo(mundo))
        r = await ff.run_create_custom_field(
            ff.CustomFieldCreate(label="Profissão", step=1, field_type="text"), DOMUS_ADMIN, _pedido())
        proprio = _doc(mundo, REDE_DOMUS)
        assert proprio is not None
        assert r["field"]["field_key"] in _chaves(proprio["fields"])
        assert {"name", "email"} <= set(_chaves(proprio["fields"])), "a cópia herda o modelo"
        assert _modelo(mundo) == modelo_antes

    @pytest.mark.asyncio
    async def test_materializar_nao_altera_um_formulario_que_a_rede_ja_tem(self, mundo):
        antes = dict(_doc(mundo, REDE_DOMUS))
        assert await fcs.garantir_formulario_da_rede(REDE_DOMUS) is False
        assert _doc(mundo, REDE_DOMUS) == antes

    @pytest.mark.asyncio
    async def test_materializar_e_idempotente(self, mundo):
        mundo.form_config.docs[:] = [d for d in mundo.form_config.docs if d.get("network_id") != REDE_DOMUS]
        assert await fcs.garantir_formulario_da_rede(REDE_DOMUS) is True
        assert await fcs.garantir_formulario_da_rede(REDE_DOMUS) is False
        assert len([d for d in mundo.form_config.docs if d.get("network_id") == REDE_DOMUS]) == 1

    @pytest.mark.asyncio
    async def test_sem_modelo_a_copia_nasce_dos_defaults(self, mundo):
        from services.form_config_defaults import DEFAULT_FORM_CONFIG

        mundo.form_config.docs[:] = []
        assert await fcs.garantir_formulario_da_rede(REDE_DOMUS) is True
        assert len(_doc(mundo, REDE_DOMUS)["fields"]) == len(DEFAULT_FORM_CONFIG)

    @pytest.mark.asyncio
    async def test_apagar_um_campo_personalizado_so_toca_na_rede(self, mundo):
        import services.form_config_fields as ff

        await ff.run_delete_custom_field("custom_power", POWER_ADMIN, _pedido())
        assert "custom_power" not in _chaves(_doc(mundo, REDE_INCUMBENTE)["fields"])
        assert _chaves(_doc(mundo, REDE_DOMUS)["fields"]) == ["name", "custom_domus"]

    @pytest.mark.asyncio
    async def test_um_campo_da_domus_nao_se_apaga_a_partir_da_power(self, mundo):
        import services.form_config_fields as ff

        with pytest.raises(HTTPException) as erro:
            await ff.run_delete_custom_field("custom_domus", POWER_ADMIN, _pedido())
        assert erro.value.status_code == 404
        assert "custom_domus" in _chaves(_doc(mundo, REDE_DOMUS)["fields"])

    @pytest.mark.asyncio
    async def test_repor_so_repoe_a_rede_em_contexto(self, mundo):
        import services.form_config_fields as ff
        from services.form_config_defaults import DEFAULT_FORM_CONFIG

        await ff.run_reset_form_config(MASTER, _pedido("cmp-domus"))
        assert len(_doc(mundo, REDE_DOMUS)["fields"]) == len(DEFAULT_FORM_CONFIG)
        assert "custom_power" in _chaves(_doc(mundo, REDE_INCUMBENTE)["fields"])

    @pytest.mark.asyncio
    async def test_o_ecran_diz_que_rede_edita_e_os_links_de_cada_empresa(self, mundo):
        import services.form_config_fields as ff

        r = await ff.run_get_form_config(POWER_ADMIN, _pedido("cmp-power"))
        assert r["network_id"] == REDE_INCUMBENTE
        assert r["tem_formulario_proprio"] is True
        assert sorted(r["empresas"]) == ["Power Real Estate", "Precision Crédito"]
        assert {e["id"] for e in r["empresas_detalhe"]} == {"cmp-power", "cmp-precision"}
        assert "custom_power" in _chaves(r["fields"]) and "custom_domus" not in _chaves(r["fields"])


# ====================================================================
# MODELOS PERSONALIZADOS: também são da rede
# ====================================================================

class TestModelosPersonalizados:
    @pytest.mark.asyncio
    async def test_um_modelo_guardado_pela_power_nao_e_visto_nem_activado_pela_domus(self, mundo):
        import services.form_config_templates as ft

        guardado = await ft.run_save_as_template(ft.TemplateSave(name="Meu"), POWER_ADMIN, _pedido("cmp-power"))
        tid = guardado["template"]["id"]
        assert next(t for t in mundo.form_templates.docs if t["id"] == tid)["network_id"] == REDE_INCUMBENTE

        da_domus = await ft.run_list_templates(DOMUS_ADMIN, _pedido("cmp-domus"))
        assert tid not in [t["id"] for t in da_domus["templates"]]
        for chamada in (ft.run_preview_template, ft.run_activate_template, ft.run_duplicate_template):
            with pytest.raises(HTTPException) as erro:
                await chamada(tid, DOMUS_ADMIN, _pedido("cmp-domus"))
            assert erro.value.status_code == 404

        da_power = await ft.run_list_templates(POWER_ADMIN, _pedido("cmp-power"))
        assert tid in [t["id"] for t in da_power["templates"]]

    @pytest.mark.asyncio
    async def test_activar_um_modelo_substitui_so_os_campos_da_rede_e_guarda_o_resto(self, mundo):
        import services.form_config_templates as ft

        mundo.form_config.docs[:] = [d for d in mundo.form_config.docs if d.get("network_id") != REDE_DOMUS]
        _modelo(mundo)["step_labels"] = {"2": "Do modelo"}
        mundo.form_templates.docs.append({"id": "tpl_d", "name": "D", "network_id": REDE_DOMUS, "fields": [_campo("so_dele")]})
        await ft.run_activate_template("tpl_d", DOMUS_ADMIN, _pedido())
        assert _chaves(_doc(mundo, REDE_DOMUS)["fields"]) == ["so_dele"]
        assert _doc(mundo, REDE_DOMUS)["step_labels"] == {"2": "Do modelo"}, "a cópia nasceu do modelo antes de escrever"
        assert "so_dele" not in _chaves(_modelo(mundo)["fields"])

    @pytest.mark.asyncio
    async def test_os_modelos_anteriores_a_separacao_continuam_visiveis(self, mundo):
        """Sem carimbo (antes da migração) não se perdem; a migração carimba-os."""
        import services.form_config_templates as ft

        mundo.form_templates.docs.append({"id": "tpl_velho", "name": "Velho", "fields": []})
        lista = await ft.run_list_templates(DOMUS_ADMIN, _pedido())
        assert "tpl_velho" in [t["id"] for t in lista["templates"]]


# ====================================================================
# O PORTAL DO CLIENTE E O PARCEIRO: o formulário da rede de QUEM
# ====================================================================

class TestOutrosLeitores:
    @pytest.mark.asyncio
    async def test_o_portal_usa_o_formulario_da_rede_do_cliente(self, mundo):
        from services.portal_profile import carregar_campos_editaveis, rede_do_formulario_do_cliente

        assert rede_do_formulario_do_cliente({"network_id": REDE_DOMUS}) == REDE_DOMUS
        assert rede_do_formulario_do_cliente({"id": "legado"}) == REDE_INCUMBENTE
        domus = await carregar_campos_editaveis(REDE_DOMUS)
        power = await carregar_campos_editaveis(REDE_INCUMBENTE)
        assert isinstance(domus, dict) and isinstance(power, dict)

    @pytest.mark.asyncio
    async def test_o_portal_passa_a_rede_do_cliente_ao_leitor(self):
        from services import portal_profile

        with patch("services.public_form_config.load_merged_form_fields", AsyncMock(return_value=[])) as leitor:
            await portal_profile.carregar_campos_editaveis(REDE_DOMUS)
        leitor.assert_awaited_once_with(REDE_DOMUS)

    def test_o_parceiro_usa_a_rede_da_lead(self, rede_de_omissao_incumbente):
        from services.partner_client_form import _rede_do_formulario

        class Caso:
            process = None
            client = {"network_id": REDE_DOMUS}

        assert _rede_do_formulario(Caso()) == REDE_DOMUS

        class Processo:
            process = {"network_id": REDE_INCUMBENTE}
            client = {"network_id": REDE_DOMUS}

        assert _rede_do_formulario(Processo()) == REDE_INCUMBENTE, "o processo manda"

        class Antigo:
            process = None
            client = {"id": "x"}

        assert _rede_do_formulario(Antigo()) == REDE_INCUMBENTE, "sem carimbo, a rede de omissão"


# ====================================================================
# O REGISTO: o cliente nasce da empresa do link
# ====================================================================

@pytest.fixture
def registo(mundo):
    import services.public_registration as pr

    s3 = MagicMock()
    s3.initialize_client_folders = MagicMock(return_value=(True, "Documentação Clientes/x"))

    def _fechar(coro, **_k):
        coro.close()

    import services.client_uniqueness as cu

    with tenant_db(mundo, pr, cu), \
            patch.object(pr, "s3_service", s3), \
            patch.object(pr, "spawn_background_task", _fechar), \
            patch("services.portal_documents_notify.generate_mandatory_document_requests", AsyncMock()), \
            patch("asyncio.create_task", lambda c, **k: c.close()):
        yield pr, mundo


def _dados(**extra):
    from models.process import PublicClientRegistration

    base = dict(name="Maria Teste", email="maria@teste.pt", phone="912345678", process_type="credito_habitacao")
    base.update(extra)
    return PublicClientRegistration(**base)


class TestORegisto:
    @pytest.mark.asyncio
    async def test_o_cliente_nasce_carimbado_com_a_empresa_do_link(self, registo):
        pr, bd = registo
        r = await pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-domus"))
        assert r.status_code == 200, r.body
        cliente = next(c for c in bd.clients.docs if c.get("fonte") == "public_form")
        assert cliente["company_id"] == "cmp-domus"
        assert cliente["company_name"] == "Domus"
        assert cliente["network_id"] == REDE_DOMUS

    @pytest.mark.asyncio
    async def test_uma_empresa_desconhecida_recusa_e_nao_cria_nada(self, registo):
        pr, bd = registo
        antes = len(bd.clients.docs)
        r = await pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-que-nao-existe"))
        assert r.status_code == 404
        assert len(bd.clients.docs) == antes

    @pytest.mark.asyncio
    async def test_a_mesma_pessoa_noutra_rede_nunca_reutiliza_nem_recarimba_o_cliente_alheio(self, registo):
        """D-32 → D-42 (INVERTIDO): o link de outra rede já não cria «outro cliente» — a identidade é
        global, logo o registo anónimo é recusado (409 genérico) — mas continua a não reutilizar,
        actualizar nem recarimbar o cliente alheio."""
        pr, bd = registo
        r = await pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-domus"))
        assert r.status_code == 200
        # a mesma pessoa regista-se agora pelo link da Power
        r = await pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-power"))
        assert r.status_code == 409
        clientes = [c for c in bd.clients.docs if c.get("fonte") == "public_form"]
        assert [c["network_id"] for c in clientes] == [REDE_DOMUS], "um só cliente, ainda da Domus"

    @pytest.mark.asyncio
    async def test_o_mesmo_contacto_na_mesma_rede_e_recusado_com_409(self, registo):
        """D-38: antes (D-32) reutilizava-se o cliente e actualizava-se em silêncio."""
        pr, bd = registo
        assert (await pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-domus"))).status_code == 200
        r = await pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-domus"))
        assert r.status_code == 409
        assert len([c for c in bd.clients.docs if c.get("fonte") == "public_form"]) == 1

    @pytest.mark.asyncio
    async def test_um_cliente_da_pool_bloqueia_todos_os_links(self, registo):
        """D-42 (INVERTIDO: no D-38 bloqueava só o link da rede de omissão): a identidade é global,
        a pilha por carimbar também conta para o link de uma ilha."""
        pr, bd = registo
        assert (await pr.run_public_client_registration(_pedido(), _dados())).status_code == 200
        assert "network_id" not in next(c for c in bd.clients.docs if c.get("fonte") == "public_form")
        assert (await pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-power"))).status_code == 409
        assert (await pr.run_public_client_registration(_pedido(), _dados(empresa_id="cmp-domus"))).status_code == 409
        clientes = [c for c in bd.clients.docs if c.get("fonte") == "public_form"]
        assert len(clientes) == 1
        assert "network_id" not in clientes[0], "a pilha ficou intacta"


# ====================================================================
# A MIGRAÇÃO
# ====================================================================

class TestAMigracao:
    @pytest.mark.asyncio
    async def test_so_mostra_e_nao_escreve(self, mundo):
        from scripts import migrar_formularios_por_rede as mig

        mundo.form_config.docs[:] = [d for d in mundo.form_config.docs if d.get("network_id") != REDE_DOMUS]
        antes = [dict(d) for d in mundo.form_config.docs]
        plano = await mig.planear(mundo)
        assert [dict(d) for d in mundo.form_config.docs] == antes
        assert plano["redes_sem_formulario"] == [REDE_DOMUS]
        assert plano["modelo_existe"] is True

    @pytest.mark.asyncio
    async def test_cria_a_copia_so_onde_falta_e_e_idempotente(self, mundo):
        from scripts import migrar_formularios_por_rede as mig

        mundo.form_config.docs[:] = [d for d in mundo.form_config.docs if d.get("network_id") != REDE_DOMUS]
        incumbente = dict(_doc(mundo, REDE_INCUMBENTE))
        escrito = await mig.aplicar(mundo)
        assert escrito["formularios_criados"] == [REDE_DOMUS]
        assert _doc(mundo, REDE_INCUMBENTE) == incumbente, "nunca altera o que a rede já tem"
        assert _chaves(_doc(mundo, REDE_DOMUS)["fields"]) == _chaves(_modelo(mundo)["fields"])
        assert (await mig.aplicar(mundo))["formularios_criados"] == []

    @pytest.mark.asyncio
    async def test_carimba_os_modelos_personalizados_antigos_com_a_rede_de_omissao(self, mundo):
        from scripts import migrar_formularios_por_rede as mig

        mundo.form_templates.docs.extend([
            {"id": "tpl_velho", "name": "Velho", "fields": []},
            {"id": "tpl_domus", "name": "D", "network_id": REDE_DOMUS, "fields": []},
        ])
        escrito = await mig.aplicar(mundo)
        por_id = {t["id"]: t for t in mundo.form_templates.docs}
        assert escrito["templates_carimbados"] == 1
        assert por_id["tpl_velho"]["network_id"] == REDE_INCUMBENTE
        assert por_id["tpl_domus"]["network_id"] == REDE_DOMUS


# ====================================================================
# AS ROTAS
# ====================================================================

class TestAsRotas:
    @pytest.fixture
    def cliente(self, mundo):
        import services.auth as auth_mod
        from routes import form_config as rota

        atual = {"user": POWER_ADMIN}
        app = FastAPI()
        app.include_router(rota.router)
        app.dependency_overrides[get_current_user] = lambda: atual["user"]
        with tenant_db(mundo, auth_mod):
            c = TestClient(app, raise_server_exceptions=False)
            c.definir_utilizador = lambda u: atual.update(user=u)
            yield c, mundo

    @pytest.mark.parametrize("utilizador", [POWER_ADMIN, CEO, MASTER])
    def test_admin_ceo_e_master_editam_o_da_sua_rede(self, cliente, utilizador):
        c, bd = cliente
        c.definir_utilizador(utilizador)
        r = c.put("/admin/form-config/fields", json={"fields": [_campo("name"), _campo(f"de_{utilizador['id']}")]})
        assert r.status_code == 200, r.text
        assert f"de_{utilizador['id']}" in _chaves(_doc(bd, REDE_INCUMBENTE)["fields"])
        assert f"de_{utilizador['id']}" not in _chaves(_doc(bd, REDE_DOMUS)["fields"])

    @pytest.mark.parametrize("papel", ["diretor", "consultor", "intermediario", "indexacao"])
    def test_os_outros_perfis_nao_editam(self, cliente, papel):
        c, bd = cliente
        c.definir_utilizador({"id": "u-x", "role": papel, "effective_role": papel})
        assert c.put("/admin/form-config/fields", json={"fields": []}).status_code == 403
        assert c.get("/admin/form-config/fields").status_code == 403

    def test_repor_continua_so_do_master(self, cliente):
        c, _bd = cliente
        assert c.post("/admin/form-config/reset").status_code == 403
        c.definir_utilizador(MASTER)
        assert c.post("/admin/form-config/reset").status_code == 200


# ====================================================================
# O INVENTÁRIO — nenhum acesso a `db.form_config` sem dizer de que rede
# ====================================================================

def _acessos_a_form_config(caminho: Path):
    """``[(linha, operação, fonte do 1.º argumento)]`` de cada `db.form_config.<op>(...)`."""
    fonte = caminho.read_text(encoding="utf-8")
    achados = []
    for no in ast.walk(ast.parse(fonte)):
        if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)):
            continue
        base = no.func.value
        if (isinstance(base, ast.Attribute) and base.attr == "form_config"
                and isinstance(base.value, ast.Name) and base.value.id in {"db", "base"}):
            primeiro = ast.get_source_segment(fonte, no.args[0]) if no.args else ""
            achados.append((no.lineno, no.func.attr, primeiro or ""))
    return achados


class TestOInventario:
    def test_o_leitor_le_mesmo_os_acessos(self):
        """Contraprova: sem ela, uma guarda que não encontra nada passa sempre."""
        assert len(_acessos_a_form_config(BACKEND / "services" / "form_config_scope.py")) >= 3

    def test_todo_o_acesso_a_form_config_diz_de_que_rede(self):
        sem_rede = []
        for pasta in ("services", "routes"):
            for caminho in sorted((BACKEND / pasta).glob("*.py")):
                for linha, op, filtro in _acessos_a_form_config(caminho):
                    if "CAMPO_REDE" not in filtro and "network_id" not in filtro:
                        sem_rede.append(f"{caminho.name}:{linha} {op}({filtro})")
        assert not sem_rede, f"acesso a form_config sem dizer de que rede: {sem_rede}"

    #: Rotas que NÃO resolvem a rede em contexto, com o motivo.
    SEM_REDE_EM_CONTEXTO = {
        "delete_template": "Só Master, apaga um modelo personalizado por id — manutenção global, não edição de uma rede.",
    }

    def _rotas_sem_request(self):
        fonte = (BACKEND / "routes" / "form_config.py").read_text(encoding="utf-8")
        return [
            f.name for f in ast.walk(ast.parse(fonte))
            if isinstance(f, ast.AsyncFunctionDef)
            and any(isinstance(d, ast.Call) and getattr(d.func, "attr", "") in {"get", "put", "post", "delete"} for d in f.decorator_list)
            and "request" not in [a.arg for a in f.args.args]
        ]

    def test_nenhuma_rota_do_formulario_fica_sem_request(self):
        sem = [r for r in self._rotas_sem_request() if r not in self.SEM_REDE_EM_CONTEXTO]
        assert not sem, f"rotas do formulário sem `request` (a rede em contexto sai dele): {sem}"

    def test_as_excepcoes_sao_reais_e_so_master(self):
        """Contraprova: uma excepção escrita que já não existe, ou que se alargou, falha."""
        assert sorted(self._rotas_sem_request()) == sorted(self.SEM_REDE_EM_CONTEXTO)
        fonte = (BACKEND / "routes" / "form_config.py").read_text(encoding="utf-8")
        i = fonte.index("async def delete_template")
        assert "UserRole.MASTER" in fonte[i:i + 200] and "ADMIN" not in fonte[i:i + 200]
