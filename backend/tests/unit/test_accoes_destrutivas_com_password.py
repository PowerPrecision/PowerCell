"""
Acções destrutivas que exigem a password ACTUAL (reautenticação), além do «Repor ao Modelo».

  * eliminar uma empresa;
  * alterar o `network_id` de uma empresa (só quando a rede MUDA);
  * anonimização em lote (fora do ensaio).

O QUE SE GARANTE
  * o SERVIDOR exige a password — o modal do ecrã não é uma parede, o endpoint é chamável sem ele;
  * a ordem: autorização/404 → password (400/403/429) → estado. Sem a password o endpoint não diz nada
    sobre o estado do alvo (utilizadores só desta empresa, etc.);
  * password errada → 403 (nunca 401), NADA é escrito (nem os efeitos laterais que vêm antes, como a
    renomeação nos utilizadores), e a falha conta para o travão;
  * reenviar a MESMA rede não pede nada (o formulário manda o objecto inteiro);
  * `confirm_password` nunca chega à base de dados nem a um `repr`;
  * o ensaio (`dry_run`) da anonimização não pede password; o real pede.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from models.company import CompanyUpdate
from services.auth import get_current_user, hash_password
from tests.unit.helpers_tenant import (  # noqa: F401  (rede_de_omissao_incumbente é fixture)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

SENHA = "Segredo-Certo-9!"

MASTER = {"id": "u-master", "role": "master", "effective_role": "master", "name": "Master", "email": "m@p.pt"}
ADMIN = {"id": "u-admin", "role": "admin", "effective_role": "admin", "name": "Admin", "email": "a@p.pt"}
CEO = {"id": "u-ceo", "role": "ceo", "effective_role": "ceo", "name": "CEO", "email": "c@p.pt"}


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    import services.admin_helpers as helpers
    import services.companies_crud_api_mutate as mut
    import services.gdpr_api_mutate as gdpr
    import services.reauth_password as reauth
    import services.admin_users_scope as aus
    import services.user_management_scope as ums

    bd = semear(fake_async_db)
    bd.companies.docs.append({"id": "cmp-teste", "name": "Empresa Teste", "network_id": "rede_teste"})
    bd.user_company_roles.docs.extend([
        {"user_id": "u-master", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "master", "is_default": True},
        {"user_id": "u-admin", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "admin", "is_default": True},
    ])
    for u in (MASTER, ADMIN, CEO):
        bd.users.docs.append({"id": u["id"], "email": u["email"], "password": hash_password(SENHA), "is_active": True})
    with tenant_db(bd, helpers, mut, reauth, ums, aus, gdpr), \
            patch("services.auth.get_active_company_id_async", AsyncMock(return_value="cmp-power")):
        yield bd, mut, gdpr


def _empresa(bd, id_):
    return next(d for d in bd.companies.docs if d["id"] == id_)


def _rasto(bd, acao):
    return [a for a in bd.audit_logs.docs if a["action"] == acao]


# ════════════════════════════════════════════════════════════════════
#  Alterar o network_id
# ════════════════════════════════════════════════════════════════════
class TestAlterarARede:
    async def test_mudar_a_rede_sem_password_e_400_e_nada_muda(self, mundo):
        bd, mut, _ = mundo
        with pytest.raises(HTTPException) as erro:
            await mut.run_update_company("cmp-teste", CompanyUpdate(network_id="outra_rede"), actor=MASTER)
        assert erro.value.status_code == 400
        assert _empresa(bd, "cmp-teste")["network_id"] == "rede_teste"
        assert _rasto(bd, "company_network_changed") == []

    async def test_password_errada_e_403_e_nada_muda(self, mundo):
        bd, mut, _ = mundo
        with pytest.raises(HTTPException) as erro:
            await mut.run_update_company(
                "cmp-teste", CompanyUpdate(network_id="outra_rede", confirm_password="errada"), actor=MASTER,
            )
        assert erro.value.status_code == 403
        assert _empresa(bd, "cmp-teste")["network_id"] == "rede_teste"

    async def test_password_errada_nao_renomeia_utilizadores_nem_empresa(self, mundo):
        """A renomeação mexe nos utilizadores ANTES do `update_one`: a password tem de vir antes de tudo."""
        bd, mut, _ = mundo
        bd.users.docs.append({"id": "u-x", "company": "Empresa Teste", "email": "x@x.pt"})
        with pytest.raises(HTTPException):
            await mut.run_update_company(
                "cmp-teste",
                CompanyUpdate(name="Nome Novo", network_id="outra_rede", confirm_password="errada"),
                actor=MASTER,
            )
        assert next(u for u in bd.users.docs if u["id"] == "u-x")["company"] == "Empresa Teste"
        assert _empresa(bd, "cmp-teste")["name"] == "Empresa Teste"

    async def test_password_certa_muda_deixa_rasto_e_nao_grava_a_password(self, mundo):
        bd, mut, _ = mundo
        r = await mut.run_update_company(
            "cmp-teste", CompanyUpdate(network_id="outra_rede", confirm_password=SENHA), actor=MASTER,
        )
        assert r.network_id == "outra_rede"
        gravada = _empresa(bd, "cmp-teste")
        assert gravada["network_id"] == "outra_rede"
        assert "confirm_password" not in gravada and SENHA not in repr(gravada)
        [rasto] = _rasto(bd, "company_network_changed")
        assert rasto["details"]["rede_antiga"] == "rede_teste" and rasto["details"]["rede_nova"] == "outra_rede"
        assert SENHA not in repr(rasto)

    async def test_reenviar_a_mesma_rede_nao_pede_password(self, mundo):
        """O formulário manda o objecto inteiro: só a MUDANÇA é uma decisão sobre a fronteira."""
        bd, mut, _ = mundo
        await mut.run_update_company("cmp-teste", CompanyUpdate(network_id="rede_teste", name="Outro Nome"), actor=MASTER)
        assert _empresa(bd, "cmp-teste")["name"] == "Outro Nome"
        assert _rasto(bd, "company_network_changed") == []

    async def test_a_mesma_rede_com_espacos_tambem_nao_conta_como_mudanca(self, mundo):
        bd, mut, _ = mundo
        await mut.run_update_company("cmp-teste", CompanyUpdate(network_id="  rede_teste  ", is_active=True), actor=MASTER)

    async def test_sem_rede_para_sem_rede_nao_pede_password(self, mundo):
        """`None`, ausente e vazio são a mesma coisa (empresa isolada)."""
        bd, mut, _ = mundo
        bd.companies.docs.append({"id": "cmp-ilha", "name": "Ilha"})
        await mut.run_update_company("cmp-ilha", CompanyUpdate(network_id="", is_active=True), actor=MASTER)

    async def test_deixar_uma_rede_e_uma_mudanca(self, mundo):
        """Pôr a rede a vazio isola a empresa: redesenha a fronteira tanto como mudar de grupo."""
        bd, mut, _ = mundo
        with pytest.raises(HTTPException) as erro:
            await mut.run_update_company("cmp-teste", CompanyUpdate(network_id=""), actor=MASTER)
        assert erro.value.status_code == 400
        assert _empresa(bd, "cmp-teste")["network_id"] == "rede_teste"

    async def test_actualizar_outros_campos_nunca_pede_password(self, mundo):
        bd, mut, _ = mundo
        await mut.run_update_company("cmp-teste", CompanyUpdate(email="geral@teste.pt"), actor=MASTER)
        assert _empresa(bd, "cmp-teste")["email"] == "geral@teste.pt"

    async def test_um_perfil_local_continua_a_levar_403_de_permissao_primeiro(self, mundo):
        """A recusa de permissão vem ANTES da password: um Admin não gasta tentativas nem aprende nada."""
        bd, mut, _ = mundo
        with pytest.raises(HTTPException) as erro:
            await mut.run_update_company(
                "cmp-power", CompanyUpdate(network_id="outra", confirm_password=SENHA), actor=ADMIN,
            )
        assert erro.value.status_code == 403 and "Master" in erro.value.detail
        assert _empresa(bd, "cmp-power")["network_id"] == REDE_INCUMBENTE

    async def test_o_travao_conta_as_falhas_e_bloqueia_com_429(self, mundo):
        bd, mut, _ = mundo
        codigos = []
        for _ in range(9):
            try:
                await mut.run_update_company(
                    "cmp-teste", CompanyUpdate(network_id="outra_rede", confirm_password="errada"), actor=MASTER,
                )
            except HTTPException as e:
                codigos.append(e.status_code)
        assert codigos[0] == 403 and codigos[-1] == 429
        # Já bloqueado: nem a password CERTA passa.
        with pytest.raises(HTTPException) as erro:
            await mut.run_update_company(
                "cmp-teste", CompanyUpdate(network_id="outra_rede", confirm_password=SENHA), actor=MASTER,
            )
        assert erro.value.status_code == 429
        assert _empresa(bd, "cmp-teste")["network_id"] == "rede_teste"

    def test_o_campo_nao_vai_para_o_dump_nem_para_o_repr(self):
        m = CompanyUpdate(network_id="x", confirm_password="segredo-xyz")
        assert "confirm_password" not in m.model_dump(exclude_unset=True)
        assert "segredo-xyz" not in repr(m) and "segredo-xyz" not in str(m)
        assert m.confirm_password == "segredo-xyz"

    async def test_personificacao_nao_confirma(self, mundo):
        bd, mut, _ = mundo
        with pytest.raises(HTTPException) as erro:
            await mut.run_update_company(
                "cmp-teste", CompanyUpdate(network_id="outra_rede", confirm_password=SENHA),
                actor={**MASTER, "is_impersonated": True},
            )
        assert erro.value.status_code == 403
        assert _empresa(bd, "cmp-teste")["network_id"] == "rede_teste"


# ════════════════════════════════════════════════════════════════════
#  Eliminar uma empresa
# ════════════════════════════════════════════════════════════════════
class TestEliminarEmpresa:
    async def test_sem_password_e_400_e_a_empresa_fica(self, mundo):
        bd, mut, _ = mundo
        with pytest.raises(HTTPException) as erro:
            await mut.run_delete_company("cmp-teste", None, actor=MASTER)
        assert erro.value.status_code == 400
        assert _empresa(bd, "cmp-teste")

    async def test_password_errada_e_403_e_a_empresa_fica(self, mundo):
        bd, mut, _ = mundo
        with pytest.raises(HTTPException) as erro:
            await mut.run_delete_company("cmp-teste", "errada", actor=MASTER)
        assert erro.value.status_code == 403
        assert _empresa(bd, "cmp-teste")

    async def test_password_certa_elimina_e_deixa_rasto(self, mundo):
        bd, mut, _ = mundo
        r = await mut.run_delete_company("cmp-teste", SENHA, actor=MASTER)
        assert r["detail"] == "Empresa eliminada com sucesso"
        assert not [d for d in bd.companies.docs if d["id"] == "cmp-teste"]
        [rasto] = _rasto(bd, "company_deleted")
        assert rasto["entity_id"] == "cmp-teste" and rasto["details"]["company_name"] == "Empresa Teste"
        assert SENHA not in repr(rasto)

    async def test_sem_password_nao_ha_oraculo_do_estado(self, mundo):
        """Com utilizadores só desta empresa a eliminação é um 400 de ESTADO; sem a password não se chega lá."""
        bd, mut, _ = mundo
        bd.users.docs.append({"id": "u-so", "company": "Empresa Teste", "email": "so@x.pt", "name": "Só"})
        with pytest.raises(HTTPException) as erro:
            await mut.run_delete_company("cmp-teste", "errada", actor=MASTER)
        assert erro.value.status_code == 403 and "Só" not in str(erro.value.detail)
        with pytest.raises(HTTPException) as erro:
            await mut.run_delete_company("cmp-teste", SENHA, actor=MASTER)
        assert erro.value.status_code == 400 and "Só" in erro.value.detail
        assert _empresa(bd, "cmp-teste")
        assert _rasto(bd, "company_deleted") == []

    async def test_password_errada_nao_reatribui_utilizadores(self, mundo):
        """A eliminação reatribui utilizadores ANTES de apagar: a password tem de vir antes."""
        bd, mut, _ = mundo
        bd.users.docs.append({"id": "u-dois", "company": "Empresa Teste", "email": "d@x.pt", "name": "Dois"})
        bd.user_company_roles.docs.append(
            {"user_id": "u-dois", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "consultor"}
        )
        with pytest.raises(HTTPException):
            await mut.run_delete_company("cmp-teste", "errada", actor=MASTER)
        assert next(u for u in bd.users.docs if u["id"] == "u-dois")["company"] == "Empresa Teste"

    async def test_empresa_inexistente_continua_a_ser_404(self, mundo):
        _, mut, _ = mundo
        with pytest.raises(HTTPException) as erro:
            await mut.run_delete_company("nao-existe", SENHA, actor=MASTER)
        assert erro.value.status_code == 404


# ════════════════════════════════════════════════════════════════════
#  Anonimização em lote
# ════════════════════════════════════════════════════════════════════
class TestAnonimizacaoEmLote:
    @pytest.fixture
    def lote(self, mundo):
        bd, _, gdpr = mundo
        executar = AsyncMock(return_value={"processed": 3, "succeeded": 3})
        with patch.object(gdpr, "run_anonymization_batch", executar):
            yield gdpr, executar, bd

    async def test_real_sem_password_e_400_e_nao_executa(self, lote):
        gdpr, executar, bd = lote
        from services.gdpr_api_models import BatchAnonymizeRequest

        with pytest.raises(HTTPException) as erro:
            await gdpr.run_anonymize_batch(BatchAnonymizeRequest(dry_run=False), MASTER)
        assert erro.value.status_code == 400
        executar.assert_not_awaited()

    async def test_real_com_password_errada_e_403_e_nao_executa(self, lote):
        gdpr, executar, _ = lote
        from services.gdpr_api_models import BatchAnonymizeRequest

        with pytest.raises(HTTPException) as erro:
            await gdpr.run_anonymize_batch(BatchAnonymizeRequest(dry_run=False, password="errada"), MASTER)
        assert erro.value.status_code == 403
        executar.assert_not_awaited()

    async def test_real_com_password_certa_executa(self, lote):
        gdpr, executar, bd = lote
        from services.gdpr_api_models import BatchAnonymizeRequest

        r = await gdpr.run_anonymize_batch(BatchAnonymizeRequest(dry_run=False, password=SENHA), MASTER)
        assert r["success"] is True and r["processed"] == 3
        executar.assert_awaited_once()
        assert executar.await_args.kwargs["dry_run"] is False
        assert SENHA not in repr(bd.gdpr_audit.docs)

    async def test_o_ensaio_nao_pede_password(self, lote):
        """`dry_run` não altera nada: pedir a password aí ensinava a ignorá-la."""
        gdpr, executar, _ = lote
        from services.gdpr_api_models import BatchAnonymizeRequest

        r = await gdpr.run_anonymize_batch(BatchAnonymizeRequest(dry_run=True), MASTER)
        assert r["success"] is True
        executar.assert_awaited_once()

    async def test_por_omissao_e_ensaio(self, lote):
        from services.gdpr_api_models import BatchAnonymizeRequest

        assert BatchAnonymizeRequest().dry_run is True

    def test_a_password_nao_aparece_no_repr(self):
        from services.gdpr_api_models import BatchAnonymizeRequest

        assert "segredo-xyz" not in repr(BatchAnonymizeRequest(dry_run=False, password="segredo-xyz"))


# ════════════════════════════════════════════════════════════════════
#  HTTP — o endpoint é chamável sem o ecrã
# ════════════════════════════════════════════════════════════════════
class TestRotas:
    @pytest.fixture
    def cliente(self, mundo):
        import routes.companies_crud as rota_empresas
        import routes.gdpr as rota_gdpr
        import services.admin_workflow  # noqa: F401

        bd, _, gdpr = mundo
        atual = {"user": MASTER}
        app = FastAPI()
        app.include_router(rota_empresas.router)
        app.include_router(rota_gdpr.router)
        app.dependency_overrides[get_current_user] = lambda: atual["user"]
        executar = AsyncMock(return_value={"processed": 1, "succeeded": 1})
        with patch.object(gdpr, "run_anonymization_batch", executar):
            c = TestClient(app, raise_server_exceptions=False)
            c.definir_utilizador = lambda u: atual.update(user=u)
            c.executar = executar
            yield c, bd

    def test_delete_sem_corpo_e_400_e_nao_422(self, cliente):
        c, bd = cliente
        r = c.delete("/admin/companies/cmp-teste")
        assert r.status_code == 400, r.text
        assert _empresa(bd, "cmp-teste")

    def test_delete_com_password_errada_403(self, cliente):
        c, bd = cliente
        r = c.request("DELETE", "/admin/companies/cmp-teste", json={"password": "errada"})
        assert r.status_code == 403 and _empresa(bd, "cmp-teste")

    def test_delete_com_password_certa(self, cliente):
        c, bd = cliente
        r = c.request("DELETE", "/admin/companies/cmp-teste", json={"password": SENHA})
        assert r.status_code == 200, r.text
        assert not [d for d in bd.companies.docs if d["id"] == "cmp-teste"]

    def test_delete_so_o_master(self, cliente):
        c, bd = cliente
        c.definir_utilizador(ADMIN)
        r = c.request("DELETE", "/admin/companies/cmp-teste", json={"password": SENHA})
        assert r.status_code == 403 and _empresa(bd, "cmp-teste")

    def test_delete_recusa_campos_a_mais(self, cliente):
        c, _ = cliente
        assert c.request("DELETE", "/admin/companies/cmp-teste", json={"password": SENHA, "x": 1}).status_code == 422

    def test_put_da_rede_sem_password_400(self, cliente):
        c, bd = cliente
        r = c.put("/admin/companies/cmp-teste", json={"network_id": "outra_rede"})
        assert r.status_code == 400, r.text
        assert _empresa(bd, "cmp-teste")["network_id"] == "rede_teste"

    def test_put_da_rede_com_password_certa(self, cliente):
        c, bd = cliente
        r = c.put("/admin/companies/cmp-teste", json={"network_id": "outra_rede", "confirm_password": SENHA})
        assert r.status_code == 200, r.text
        assert _empresa(bd, "cmp-teste")["network_id"] == "outra_rede"
        assert "confirm_password" not in _empresa(bd, "cmp-teste")
        assert "confirm_password" not in r.text

    def test_batch_real_sem_password_400(self, cliente):
        c, _ = cliente
        r = c.post("/gdpr/batch", json={"dry_run": False})
        assert r.status_code == 400, r.text
        c.executar.assert_not_awaited()

    def test_batch_real_com_password_certa(self, cliente):
        c, _ = cliente
        r = c.post("/gdpr/batch", json={"dry_run": False, "password": SENHA})
        assert r.status_code == 200, r.text
        c.executar.assert_awaited_once()

    def test_batch_ensaio_sem_password(self, cliente):
        c, _ = cliente
        assert c.post("/gdpr/batch", json={}).status_code == 200

    def test_batch_so_o_master(self, cliente):
        c, _ = cliente
        c.definir_utilizador(ADMIN)
        assert c.post("/gdpr/batch", json={"dry_run": False, "password": SENHA}).status_code == 403
        c.executar.assert_not_awaited()


# ════════════════════════════════════════════════════════════════════
#  Inventário: nenhuma acção destrutiva fica sem password
# ════════════════════════════════════════════════════════════════════
RAIZ = Path(__file__).resolve().parents[2]


def _chamadas_de(caminho: str, funcao: str) -> set[str]:
    arvore = ast.parse((RAIZ / caminho).read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)) and no.name == funcao:
            return {ast.unparse(n.func) for n in ast.walk(no) if isinstance(n, ast.Call)}
    raise AssertionError(f"{funcao} não existe em {caminho}")


class TestInventario:
    #: (ficheiro, função) que TÊM de chamar `exigir_password_actual`. Uma acção destrutiva nova entra aqui.
    COM_PASSWORD = [
        ("services/repor_ao_modelo.py", "run_repor_workflow_ao_modelo"),
        ("services/repor_ao_modelo.py", "run_repor_formulario_ao_modelo"),
        ("services/companies_crud_api_mutate.py", "run_delete_company"),
        ("services/companies_crud_api_mutate.py", "run_update_company"),
        ("services/gdpr_api_mutate.py", "run_anonymize_batch"),
    ]

    @pytest.mark.parametrize("ficheiro,funcao", COM_PASSWORD)
    def test_chama_a_reautenticacao(self, ficheiro, funcao):
        assert "exigir_password_actual" in _chamadas_de(ficheiro, funcao), f"{funcao} deixou de exigir a password"

    def test_a_password_vem_antes_de_qualquer_escrita(self):
        """Na ordem do código: `exigir_password_actual` precede toda a escrita nas 4 funções destrutivas."""
        escritas = {"insert_one", "insert_many", "update_one", "update_many", "delete_one", "delete_many"}
        for ficheiro, funcao in self.COM_PASSWORD:
            arvore = ast.parse((RAIZ / ficheiro).read_text(encoding="utf-8"))
            no = next(n for n in ast.walk(arvore) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == funcao)
            chamadas = sorted(
                ((n.lineno, ast.unparse(n.func)) for n in ast.walk(no) if isinstance(n, ast.Call)),
            )
            linha_da_password = min(l for l, c in chamadas if c == "exigir_password_actual")
            antes = [c for l, c in chamadas if l < linha_da_password and c.rsplit(".", 1)[-1] in escritas]
            assert antes == [], f"{funcao}: escreve ({antes}) antes de pedir a password"

    def test_o_contraprova_o_detector_apanha_uma_escrita_antes(self):
        """Sem isto, a guarda acima passava por cegueira."""
        fonte = "async def f():\\n    await db.x.update_one({}, {})\\n    await exigir_password_actual(u, p)\\n"
        no = ast.parse(fonte.replace("\\n", "\n")).body[0]
        chamadas = sorted((n.lineno, ast.unparse(n.func)) for n in ast.walk(no) if isinstance(n, ast.Call))
        linha = min(l for l, c in chamadas if c == "exigir_password_actual")
        assert [c for l, c in chamadas if l < linha and c.endswith("update_one")]

    def test_as_rotas_levam_o_corpo_e_passam_a_password(self):
        rota = (RAIZ / "routes/companies_crud.py").read_text(encoding="utf-8")
        assert "ConfirmacaoPorPassword" in rota and "data.password if data else None" in rota
        assert "run_update_company(company_id, data, actor=user)" in rota

    def test_o_delete_e_o_batch_estao_limitados_e_declaram_response(self):
        """`@limiter.limit` sem `response: Response` rebenta o SUCESSO com 500."""
        import routes.companies_crud as rc
        import routes.gdpr as rg

        for funcao in (rc.delete_company, rg.anonymize_batch):
            params = inspect.signature(funcao).parameters
            assert "request" in params and "response" in params, funcao.__name__
