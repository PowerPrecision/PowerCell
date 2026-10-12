"""
«Repor ao Modelo» (workflow e formulário de uma rede) — acção destrutiva com password.

O QUE SE GARANTE
  * o servidor só executa depois de validar a password ACTUAL do utilizador do
    token — o modal do ecrã não é uma parede, o endpoint é chamável sem ele;
  * password errada → 403 (nunca 401: desligaria a sessão), nada é apagado, e as
    falhas contam para um travão por utilizador (429 sem olhar para a password);
  * só se apaga a cópia DA REDE: o modelo e as outras redes ficam como estavam;
  * o workflow não se repõe por cima de processos em curso numa fase que o modelo
    não tem (409 com as fases); o servidor não diz se a rede tem cópia a quem não
    provou a password;
  * Master/Admin/CEO e só na rede do seu âmbito (404 fora dele);
  * a password nunca aparece em log nem no rasto de auditoria.
"""
from __future__ import annotations

import ast
import inspect
import logging
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from services import workflow_phases as wp
from services.auth import get_current_user, hash_password
from tests.unit.helpers_tenant import (  # noqa: F401  (rede_de_omissao_incumbente é fixture)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

SENHA = "Segredo-Certo-9!"

MODELO = [
    {"id": "m-novo", "name": "novo", "label": "Novo", "order": 1, "is_active": True},
    {"id": "m-concluidos", "name": "concluidos", "label": "Concluídos", "order": 2, "is_active": False},
]


def _copia(rede, *nomes):
    return [
        {"id": f"{rede}:{n}", "name": n, "label": n, "order": i, "is_active": True, "network_id": rede}
        for i, n in enumerate(nomes, 1)
    ]


POWER_ADMIN = {"id": "u-admin", "role": "admin", "effective_role": "admin", "name": "Admin Power", "email": "a@p.pt"}
DOMUS_ADMIN = {"id": "u-admin-domus", "role": "admin", "effective_role": "admin", "name": "Admin Domus", "email": "a@d.pt"}
CEO = {"id": "u-ceo", "role": "ceo", "effective_role": "ceo", "name": "CEO", "email": "c@p.pt"}
MASTER = {"id": "u-master", "role": "master", "effective_role": "master", "name": "Master", "email": "m@p.pt"}
CONSULTOR = {"id": "u-consultor", "role": "consultor", "effective_role": "consultor", "name": "Cons", "email": "k@p.pt"}


def _pedido(company_id=None):
    from unittest.mock import MagicMock

    return MagicMock(headers={"X-Company-Id": company_id} if company_id else {}, state=MagicMock(spec=[]))


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    import services.admin_helpers as helpers
    import services.reauth_password as reauth
    import services.repor_ao_modelo as repor
    import services.client_uniqueness as cu
    import services.workflow_scope as ws
    import services.form_config_scope as fcs

    semear(fake_async_db)
    bd = fake_async_db
    bd.workflow_statuses.docs.extend([dict(f) for f in MODELO])
    bd.workflow_statuses.docs.extend(_copia(REDE_INCUMBENTE, "novo", "fase_custom", "concluidos"))
    bd.workflow_statuses.docs.extend(_copia(REDE_DOMUS, "triagem_domus", "novo"))
    bd.form_config.docs.extend([
        {"type": "public_form", "fields": [{"field_key": "modelo"}]},
        {"type": "public_form", "network_id": REDE_INCUMBENTE, "fields": [{"field_key": "power"}]},
        {"type": "public_form", "network_id": REDE_DOMUS, "fields": [{"field_key": "domus"}]},
    ])
    bd.user_company_roles.docs.extend([
        {"user_id": "u-admin", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "admin", "is_default": True},
        {"user_id": "u-admin-domus", "company_id": "cmp-domus", "company_name": "Domus", "role": "admin", "is_default": True},
        {"user_id": "u-ceo", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "ceo", "is_default": True},
        {"user_id": "u-master", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "master", "is_default": True},
    ])
    for u in (POWER_ADMIN, DOMUS_ADMIN, CEO, MASTER, CONSULTOR):
        bd.users.docs.append({"id": u["id"], "email": u["email"], "password": hash_password(SENHA), "is_active": True})

    with tenant_db(bd, ws, helpers, reauth, repor, cu, fcs), \
            patch("services.auth.get_active_company_id_async", AsyncMock(return_value="cmp-power")):
        wp.invalidar_cache_de_fases()
        yield bd, repor
    wp.invalidar_cache_de_fases()


def _fases(bd, rede):
    return sorted(d["name"] for d in bd.workflow_statuses.docs if (d.get("network_id") or None) == rede)


def _formularios(bd):
    return {d.get("network_id") or "modelo" for d in bd.form_config.docs}


def _corpo(repor, senha=SENHA, **extra):
    return repor.ReporAoModeloIn(password=senha, **extra)


# ════════════════════════════════════════════════════════════════════
#  WORKFLOW
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestWorkflow:
    async def test_com_a_password_certa_apaga_so_a_copia_da_rede(self, mundo):
        bd, repor = mundo
        r = await repor.run_repor_workflow_ao_modelo(_corpo(repor), POWER_ADMIN, _pedido("cmp-power"))

        assert r["reposto"] is True and r["network_id"] == REDE_INCUMBENTE and r["fases_removidas"] == 3
        assert _fases(bd, REDE_INCUMBENTE) == []
        assert _fases(bd, None) == ["concluidos", "novo"], "o modelo não se toca"
        assert _fases(bd, REDE_DOMUS) == ["novo", "triagem_domus"], "as outras redes não se tocam"

    async def test_depois_de_repor_a_rede_le_o_modelo(self, mundo):
        bd, repor = mundo
        await repor.run_repor_workflow_ao_modelo(_corpo(repor), POWER_ADMIN, _pedido("cmp-power"))
        nomes = [f["name"] for f in await wp.carregar_fases(rede=REDE_INCUMBENTE, usar_cache=False)]
        assert nomes == ["novo", "concluidos"]

    async def test_a_cache_de_fases_e_invalidada(self, mundo):
        bd, repor = mundo
        antes = [f["name"] for f in await wp.carregar_fases(rede=REDE_INCUMBENTE)]
        assert "fase_custom" in antes
        await repor.run_repor_workflow_ao_modelo(_corpo(repor), POWER_ADMIN, _pedido("cmp-power"))
        depois = [f["name"] for f in await wp.carregar_fases(rede=REDE_INCUMBENTE)]
        assert "fase_custom" not in depois

    async def test_password_errada_da_403_e_nao_apaga_nada(self, mundo):
        bd, repor = mundo
        antes = _fases(bd, REDE_INCUMBENTE)
        with pytest.raises(HTTPException) as erro:
            await repor.run_repor_workflow_ao_modelo(_corpo(repor, "errada"), POWER_ADMIN, _pedido("cmp-power"))
        assert erro.value.status_code == 403, "403 e nunca 401: um 401 desligaria a sessão"
        assert _fases(bd, REDE_INCUMBENTE) == antes
        assert not [a for a in bd.audit_logs.docs if a["action"] == "workflow_reposto_ao_modelo"]

    async def test_a_password_de_outro_utilizador_nao_serve(self, mundo):
        bd, repor = mundo
        for u in bd.users.docs:
            if u["id"] == "u-admin-domus":
                u["password"] = hash_password("Outra-Password-1!")
        with pytest.raises(HTTPException) as erro:
            await repor.run_repor_workflow_ao_modelo(_corpo(repor, "Outra-Password-1!"), POWER_ADMIN, _pedido("cmp-power"))
        assert erro.value.status_code == 403

    async def test_depois_de_muitas_falhas_bloqueia_mesmo_com_a_password_certa(self, mundo):
        from services.portal_brute_force import MAX_TENTATIVAS

        bd, repor = mundo
        for _ in range(MAX_TENTATIVAS):
            with pytest.raises(HTTPException) as erro:
                await repor.run_repor_workflow_ao_modelo(_corpo(repor, "errada"), POWER_ADMIN, _pedido("cmp-power"))
            assert erro.value.status_code == 403
        with pytest.raises(HTTPException) as bloqueado:
            await repor.run_repor_workflow_ao_modelo(_corpo(repor), POWER_ADMIN, _pedido("cmp-power"))
        assert bloqueado.value.status_code == 429
        assert _fases(bd, REDE_INCUMBENTE), "bloqueado: nada foi apagado"

    async def test_o_travao_e_por_utilizador(self, mundo):
        from services.portal_brute_force import MAX_TENTATIVAS

        bd, repor = mundo
        for _ in range(MAX_TENTATIVAS):
            with pytest.raises(HTTPException):
                await repor.run_repor_workflow_ao_modelo(_corpo(repor, "errada"), POWER_ADMIN, _pedido("cmp-power"))
        # Outro utilizador não herda o bloqueio.
        r = await repor.run_repor_workflow_ao_modelo(_corpo(repor), CEO, _pedido("cmp-power"))
        assert r["reposto"] is True

    async def test_o_sucesso_limpa_o_contador(self, mundo):
        from services.portal_brute_force import MAX_TENTATIVAS

        bd, repor = mundo
        for _ in range(MAX_TENTATIVAS - 1):
            with pytest.raises(HTTPException):
                await repor.run_repor_workflow_ao_modelo(_corpo(repor, "errada"), POWER_ADMIN, _pedido("cmp-power"))
        await repor.run_repor_workflow_ao_modelo(_corpo(repor), POWER_ADMIN, _pedido("cmp-power"))
        assert not [t for t in bd.portal_login_attempts.docs if "confirmar_password" in str(t.get("_id"))]

    async def test_sem_password_e_400(self, mundo):
        from services.reauth_password import exigir_password_actual

        with pytest.raises(HTTPException) as erro:
            await exigir_password_actual(POWER_ADMIN, "")
        assert erro.value.status_code == 400

    async def test_durante_uma_personificacao_nao_passa(self, mundo):
        bd, repor = mundo
        personificado = {**POWER_ADMIN, "is_impersonated": True, "impersonated_by": "u-master"}
        with pytest.raises(HTTPException) as erro:
            await repor.run_repor_workflow_ao_modelo(_corpo(repor), personificado, _pedido("cmp-power"))
        assert erro.value.status_code == 403
        assert _fases(bd, REDE_INCUMBENTE)

    async def test_processos_numa_fase_que_o_modelo_nao_tem_impedem(self, mundo):
        bd, repor = mundo
        bd.processes.docs.extend([
            {"id": "p1", "status": "fase_custom", "network_id": REDE_INCUMBENTE, "company_id": "cmp-power"},
            {"id": "p2", "status": "fase_custom", "network_id": REDE_INCUMBENTE, "company_id": "cmp-power"},
            {"id": "p3", "status": "novo", "network_id": REDE_INCUMBENTE, "company_id": "cmp-power"},
        ])
        with pytest.raises(HTTPException) as erro:
            await repor.run_repor_workflow_ao_modelo(_corpo(repor), POWER_ADMIN, _pedido("cmp-power"))
        assert erro.value.status_code == 409
        assert erro.value.detail["fases_em_uso"] == [{"name": "fase_custom", "total": 2}]
        assert "fase_custom" in _fases(bd, REDE_INCUMBENTE), "nada foi apagado"

    async def test_processos_eliminados_ou_de_outra_rede_nao_impedem(self, mundo):
        bd, repor = mundo
        bd.processes.docs.extend([
            {"id": "p1", "status": "fase_custom", "network_id": REDE_INCUMBENTE, "company_id": "cmp-power", "is_deleted": True},
            {"id": "p2", "status": "fase_custom", "network_id": REDE_DOMUS, "company_id": "cmp-domus"},
        ])
        r = await repor.run_repor_workflow_ao_modelo(_corpo(repor), POWER_ADMIN, _pedido("cmp-power"))
        assert r["reposto"] is True

    async def test_modelo_vazio_recusa(self, mundo):
        bd, repor = mundo
        bd.workflow_statuses.docs[:] = [d for d in bd.workflow_statuses.docs if d.get("network_id")]
        with pytest.raises(HTTPException) as erro:
            await repor.run_repor_workflow_ao_modelo(_corpo(repor), POWER_ADMIN, _pedido("cmp-power"))
        assert erro.value.status_code == 409 and erro.value.detail == repor.ERRO_MODELO_VAZIO
        assert _fases(bd, REDE_INCUMBENTE)

    async def test_modelo_vazio_recusa_mesmo_sem_processos(self, mundo):
        """O 409 do modelo vazio não pode depender de haver processos (o caso da base nova)."""
        bd, repor = mundo
        bd.processes.docs.clear()
        bd.workflow_statuses.docs[:] = [d for d in bd.workflow_statuses.docs if d.get("network_id")]
        with pytest.raises(HTTPException) as erro:
            await repor.run_repor_workflow_ao_modelo(_corpo(repor), POWER_ADMIN, _pedido("cmp-power"))
        assert erro.value.detail == repor.ERRO_MODELO_VAZIO
        assert _fases(bd, REDE_INCUMBENTE)

    async def test_rede_que_ja_usa_o_modelo_nao_e_um_erro(self, mundo):
        bd, repor = mundo
        bd.workflow_statuses.docs[:] = [d for d in bd.workflow_statuses.docs if d.get("network_id") != REDE_INCUMBENTE]
        r = await repor.run_repor_workflow_ao_modelo(_corpo(repor), POWER_ADMIN, _pedido("cmp-power"))
        assert r["reposto"] is False

    async def test_sem_a_password_certa_nao_se_sabe_se_a_rede_tem_copia(self, mundo):
        """Sem oráculo: a password verifica-se ANTES de se dizer o estado."""
        bd, repor = mundo
        bd.workflow_statuses.docs[:] = [d for d in bd.workflow_statuses.docs if d.get("network_id") != REDE_INCUMBENTE]
        with pytest.raises(HTTPException) as erro:
            await repor.run_repor_workflow_ao_modelo(_corpo(repor, "errada"), POWER_ADMIN, _pedido("cmp-power"))
        assert erro.value.status_code == 403

    async def test_deixa_rasto_sem_a_password(self, mundo):
        bd, repor = mundo
        await repor.run_repor_workflow_ao_modelo(_corpo(repor), POWER_ADMIN, _pedido("cmp-power"))
        rasto = [a for a in bd.audit_logs.docs if a["action"] == "workflow_reposto_ao_modelo"]
        assert len(rasto) == 1 and rasto[0]["performed_by_id"] == "u-admin"
        assert rasto[0]["details"]["network_id"] == REDE_INCUMBENTE
        assert SENHA not in str(rasto[0])

    async def test_a_password_nao_vai_para_o_log(self, mundo, caplog):
        bd, repor = mundo
        with caplog.at_level(logging.DEBUG):
            with pytest.raises(HTTPException):
                await repor.run_repor_workflow_ao_modelo(_corpo(repor, "palavra-errada-xyz"), POWER_ADMIN, _pedido("cmp-power"))
            await repor.run_repor_workflow_ao_modelo(_corpo(repor), POWER_ADMIN, _pedido("cmp-power"))
        texto = "\n".join(r.getMessage() for r in caplog.records)
        assert SENHA not in texto and "palavra-errada-xyz" not in texto

    def test_a_password_nao_aparece_no_repr_do_corpo(self):
        from services.repor_ao_modelo import ReporAoModeloIn

        assert SENHA not in repr(ReporAoModeloIn(password=SENHA))


# ════════════════════════════════════════════════════════════════════
#  A REDE
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestARede:
    async def test_um_admin_nao_repoe_a_rede_de_outro(self, mundo):
        bd, repor = mundo
        with pytest.raises(HTTPException) as erro:
            await repor.run_repor_workflow_ao_modelo(_corpo(repor, network_id=REDE_DOMUS), POWER_ADMIN, _pedido("cmp-power"))
        assert erro.value.status_code == 404
        assert _fases(bd, REDE_DOMUS), "a Domus ficou como estava"

    async def test_o_404_vem_antes_de_gastar_uma_tentativa_de_password(self, mundo):
        bd, repor = mundo
        with pytest.raises(HTTPException):
            await repor.run_repor_workflow_ao_modelo(_corpo(repor, "errada", network_id=REDE_DOMUS), POWER_ADMIN, _pedido("cmp-power"))
        assert not [t for t in bd.portal_login_attempts.docs if "confirmar_password" in str(t.get("_id"))]

    async def test_o_master_pode_pedir_outra_rede(self, mundo):
        bd, repor = mundo
        r = await repor.run_repor_workflow_ao_modelo(_corpo(repor, network_id=REDE_DOMUS), MASTER, _pedido("cmp-power"))
        assert r["reposto"] is True and r["network_id"] == REDE_DOMUS
        assert _fases(bd, REDE_DOMUS) == [] and _fases(bd, REDE_INCUMBENTE), "só a Domus"

    async def test_o_ceo_repoe_a_sua(self, mundo):
        bd, repor = mundo
        r = await repor.run_repor_workflow_ao_modelo(_corpo(repor), CEO, _pedido("cmp-power"))
        assert r["network_id"] == REDE_INCUMBENTE and r["reposto"] is True


# ════════════════════════════════════════════════════════════════════
#  FORMULÁRIO
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestFormulario:
    async def test_com_a_password_certa_apaga_so_o_da_rede(self, mundo):
        bd, repor = mundo
        r = await repor.run_repor_formulario_ao_modelo(_corpo(repor), POWER_ADMIN, _pedido("cmp-power"))
        assert r["reposto"] is True
        assert _formularios(bd) == {"modelo", REDE_DOMUS}

    async def test_depois_de_repor_a_rede_le_o_modelo(self, mundo):
        from services.form_config_scope import ler_documento

        bd, repor = mundo
        await repor.run_repor_formulario_ao_modelo(_corpo(repor), POWER_ADMIN, _pedido("cmp-power"))
        doc = await ler_documento(REDE_INCUMBENTE)
        assert doc["fields"] == [{"field_key": "modelo"}]

    async def test_password_errada_nao_apaga(self, mundo):
        bd, repor = mundo
        with pytest.raises(HTTPException) as erro:
            await repor.run_repor_formulario_ao_modelo(_corpo(repor, "errada"), POWER_ADMIN, _pedido("cmp-power"))
        assert erro.value.status_code == 403
        assert _formularios(bd) == {"modelo", REDE_INCUMBENTE, REDE_DOMUS}

    async def test_rede_sem_formulario_proprio_nao_e_erro(self, mundo):
        bd, repor = mundo
        bd.form_config.docs[:] = [d for d in bd.form_config.docs if d.get("network_id") != REDE_INCUMBENTE]
        r = await repor.run_repor_formulario_ao_modelo(_corpo(repor), POWER_ADMIN, _pedido("cmp-power"))
        assert r["reposto"] is False and "modelo" in _formularios(bd)

    async def test_um_admin_nao_repoe_o_formulario_de_outra_rede(self, mundo):
        bd, repor = mundo
        with pytest.raises(HTTPException) as erro:
            await repor.run_repor_formulario_ao_modelo(_corpo(repor, network_id=REDE_DOMUS), POWER_ADMIN, _pedido("cmp-power"))
        assert erro.value.status_code == 404
        assert REDE_DOMUS in _formularios(bd)

    async def test_deixa_rasto(self, mundo):
        bd, repor = mundo
        await repor.run_repor_formulario_ao_modelo(_corpo(repor), POWER_ADMIN, _pedido("cmp-power"))
        assert [a for a in bd.audit_logs.docs if a["action"] == "formulario_reposto_ao_modelo"]


# ════════════════════════════════════════════════════════════════════
#  HTTP — quem pode chamar
# ════════════════════════════════════════════════════════════════════
class TestRotas:
    @pytest.fixture
    def cliente(self, mundo):
        import routes.repor_ao_modelo as rota
        import services.admin_workflow as aw

        bd, repor = mundo
        atual = {"user": POWER_ADMIN}
        app = FastAPI()
        app.include_router(rota.router)
        app.dependency_overrides[get_current_user] = lambda: atual["user"]
        with tenant_db(bd, aw):
            c = TestClient(app, raise_server_exceptions=False)
            c.definir_utilizador = lambda u: atual.update(user=u)
            yield c, bd

    CAMINHOS = ["/admin/workflow-statuses/reset-to-model", "/admin/form-config/reset-to-model"]

    @pytest.mark.parametrize("caminho", CAMINHOS)
    def test_um_consultor_nao_pode(self, cliente, caminho):
        c, bd = cliente
        c.definir_utilizador(CONSULTOR)
        r = c.post(caminho, json={"password": SENHA})
        assert r.status_code == 403
        assert _fases(bd, REDE_INCUMBENTE) and REDE_INCUMBENTE in _formularios(bd)

    @pytest.mark.parametrize("caminho", CAMINHOS)
    def test_sem_corpo_ou_sem_password_e_422(self, cliente, caminho):
        c, _ = cliente
        assert c.post(caminho).status_code == 422
        assert c.post(caminho, json={}).status_code == 422
        assert c.post(caminho, json={"password": ""}).status_code == 422

    @pytest.mark.parametrize("caminho", CAMINHOS)
    def test_campos_a_mais_sao_recusados(self, cliente, caminho):
        c, _ = cliente
        assert c.post(caminho, json={"password": SENHA, "network_id_extra": "x"}).status_code == 422

    def test_o_workflow_repoe_pela_rota_com_a_password_certa(self, cliente):
        c, bd = cliente
        r = c.post("/admin/workflow-statuses/reset-to-model", json={"password": SENHA})
        assert r.status_code == 200, r.text
        assert r.json()["reposto"] is True and _fases(bd, REDE_INCUMBENTE) == []

    def test_o_workflow_com_password_errada_da_403(self, cliente):
        c, bd = cliente
        r = c.post("/admin/workflow-statuses/reset-to-model", json={"password": "errada"})
        assert r.status_code == 403 and _fases(bd, REDE_INCUMBENTE)

    def test_o_formulario_repoe_pela_rota(self, cliente):
        c, bd = cliente
        r = c.post("/admin/form-config/reset-to-model", json={"password": SENHA})
        assert r.status_code == 200, r.text
        assert REDE_INCUMBENTE not in _formularios(bd)

    def test_o_formulario_com_password_errada_da_403(self, cliente):
        c, bd = cliente
        r = c.post("/admin/form-config/reset-to-model", json={"password": "errada"})
        assert r.status_code == 403 and REDE_INCUMBENTE in _formularios(bd)


# ════════════════════════════════════════════════════════════════════
#  GUARDAS SOBRE O CÓDIGO
# ════════════════════════════════════════════════════════════════════
class TestGuardas:
    def _funcao(self, nome):
        import services.repor_ao_modelo as repor

        arvore = ast.parse(inspect.getsource(repor))
        return next(n for n in ast.walk(arvore) if isinstance(n, ast.AsyncFunctionDef) and n.name == nome)

    @pytest.mark.parametrize("nome", ["run_repor_workflow_ao_modelo", "run_repor_formulario_ao_modelo"])
    def test_a_password_valida_se_antes_de_qualquer_escrita(self, nome):
        funcao = self._funcao(nome)
        chamadas = [
            (n.lineno, ast.unparse(n.func)) for n in ast.walk(funcao) if isinstance(n, ast.Call)
        ]
        pw = [ln for ln, f in chamadas if f == "exigir_password_actual"]
        escritas = [ln for ln, f in chamadas if f.endswith((".delete_many", ".delete_one"))]
        assert pw and escritas and min(pw) < min(escritas)

    @pytest.mark.parametrize("nome", ["run_repor_workflow_ao_modelo", "run_repor_formulario_ao_modelo"])
    def test_o_filtro_de_apagar_leva_sempre_a_rede(self, nome):
        funcao = self._funcao(nome)
        apagar = [
            n for n in ast.walk(funcao)
            if isinstance(n, ast.Call) and ast.unparse(n.func).endswith((".delete_many", ".delete_one"))
        ]
        assert len(apagar) == 1
        assert "CAMPO_REDE: rede" in ast.unparse(apagar[0].args[0])

    def test_as_rotas_exigem_papel_e_limitam(self):
        import routes.repor_ao_modelo as rota

        codigo = inspect.getsource(rota)
        for nome in ("reset_workflow_to_model", "reset_form_config_to_model"):
            fonte = inspect.getsource(getattr(rota, nome))
            assert "PAPEIS_QUE_EDITAM_O_WORKFLOW" in fonte
            assert "response: Response" in fonte
            posicao = codigo.index(f"async def {nome}")
            assert "@limiter.limit" in codigo[posicao - 200:posicao]

    def test_o_router_esta_registado_na_aplicacao(self):
        import server

        caminhos = {r.path for r in server.app.routes}
        assert "/api/admin/workflow-statuses/reset-to-model" in caminhos
        assert "/api/admin/form-config/reset-to-model" in caminhos
