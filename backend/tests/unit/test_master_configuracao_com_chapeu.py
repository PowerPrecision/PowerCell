"""A conta Master não perde a configuração do sistema por ter escolhido outro perfil (QA, Out 2026).

O QUE A QA VIU
  O Master recebia 403 ao abrir «Destinatários de Documentação» (e o resto das
  Configurações do Sistema). Reproduzido: o Master tem UCRs de Admin nas empresas e o
  seletor de contexto deixa-o trabalhar como Admin da Power. O `X-Active-Role: admin`
  fazia o servidor tratá-lo como Admin — e a configuração GLOBAL é «exclusiva do perfil
  Master». A mensagem de erro a um Master que é Master.

A REGRA
  * **Infraestrutura/configuração segue a CONTA**: a conta Master (`users.role`) acede à
    global e a todas as empresas, qualquer que seja o chapéu (`conta_master_passa`).
  * **Dados seguem o PERFIL ACTIVO** (inalterado, `test_hierarquia_de_perfis`): com o
    chapéu de Admin o Master vê o que um Admin vê.
  * Admin e CEO continuam sem a global (contraprova).
  * A flag é EXPLÍCITA e só está nas rotas de `system_config`; as outras ~100 rotas
    só-Master continuam a seguir o perfil activo.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import (  # noqa: F401  (fixture)
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

MASTER = {"id": "u-master", "name": "Master", "email": "m@x.pt", "role": "master"}
ADMIN = {"id": "u-admin", "name": "Admin", "email": "a@x.pt", "role": "admin"}
CEO = {"id": "u-ceo", "name": "CEO", "email": "c@x.pt", "role": "ceo"}

CHAPEU_DE_ADMIN = {"X-Active-Role": "admin", "X-Company-Id": "cmp-power"}


class Pedido:
    def __init__(self, cabecalhos=None):
        self.headers = cabecalhos or {}
        self.state = SimpleNamespace()


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    import services.system_config as core
    import services.system_config_scope as ambito

    semear(fake_async_db)
    fake_async_db.user_company_roles.docs.extend([
        {"user_id": "u-master", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "admin", "is_default": True},
        {"user_id": "u-admin", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "admin", "is_default": True},
        {"user_id": "u-ceo", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "ceo", "is_default": True},
    ])
    fake_async_db.system_config.docs.append({"_id": "main", "company_id": "default"})
    core._config_cache.clear()
    with tenant_db(fake_async_db, core, ambito):
        yield fake_async_db
    core._config_cache.clear()


@pytest.mark.asyncio
class TestOMasterComChapeuDeAdmin:
    async def test_le_a_configuracao_global(self, mundo):
        from routes.system_config import get_config

        r = await get_config(request=Pedido(CHAPEU_DE_ADMIN), company_id="default", user=MASTER)
        assert r is not None

    async def test_grava_na_configuracao_global(self, mundo):
        from routes.system_config import update_config

        r = await update_config(
            section="document_recipients", data={"enabled": True},
            request=Pedido(CHAPEU_DE_ADMIN), company_id="default", user=MASTER,
        )
        assert r is not None
        main = next(d for d in mundo.system_config.docs if d["_id"] == "main")
        assert main["document_recipients"]["enabled"] is True

    async def test_revela_segredos_da_global(self, mundo):
        from routes.system_config import reveal_secrets

        await reveal_secrets(section="storage", request=Pedido(CHAPEU_DE_ADMIN), company_id="default", user=MASTER)

    async def test_o_seletor_oferece_a_global_e_todas_as_empresas(self, mundo):
        from services.system_config_scope import carregar_ambito_de_configuracao, listar_empresas_configuraveis

        ambito = await carregar_ambito_de_configuracao(MASTER, Pedido(CHAPEU_DE_ADMIN))
        ids = {e["company_id"] for e in await listar_empresas_configuraveis(ambito)}
        assert {"default", "cmp-power", "cmp-domus", "cmp-precision"} <= ids

    async def test_a_guarda_de_papel_das_rotas_so_master_deixa_passar(self, mundo):
        from models.auth import UserRole
        from services.auth import require_roles

        verificar = require_roles([UserRole.MASTER], conta_master_passa=True)
        assert (await verificar(request=Pedido(CHAPEU_DE_ADMIN), user=MASTER)) is MASTER


@pytest.mark.asyncio
class TestContraprovas:
    async def test_um_Admin_verdadeiro_continua_sem_a_global(self, mundo):
        from routes.system_config import get_config

        with pytest.raises(HTTPException) as erro:
            await get_config(request=Pedido(), company_id="default", user=ADMIN)
        assert erro.value.status_code == 403

    async def test_um_CEO_continua_sem_a_global(self, mundo):
        from routes.system_config import get_config

        with pytest.raises(HTTPException) as erro:
            await get_config(request=Pedido(), company_id="default", user=CEO)
        assert erro.value.status_code == 403

    async def test_um_Admin_nao_ganha_nada_com_cabecalhos_de_master(self, mundo):
        from routes.system_config import get_config

        with pytest.raises(HTTPException) as erro:
            await get_config(
                request=Pedido({"X-Active-Role": "master"}), company_id="default", user=ADMIN,
            )
        assert erro.value.status_code == 403

    async def test_a_guarda_de_papel_sem_a_flag_continua_a_seguir_o_perfil_activo(self, mundo):
        """As outras rotas só-Master NÃO mudaram: com o chapéu de Admin, 403."""
        from models.auth import UserRole
        from services.auth import require_roles

        with pytest.raises(HTTPException) as erro:
            await require_roles([UserRole.MASTER])(request=Pedido(CHAPEU_DE_ADMIN), user=MASTER)
        assert erro.value.status_code == 403

    async def test_a_flag_nao_deixa_passar_quem_nao_e_conta_master(self, mundo):
        from models.auth import UserRole
        from services.auth import require_roles

        for utilizador in (ADMIN, CEO):
            with pytest.raises(HTTPException):
                await require_roles([UserRole.MASTER], conta_master_passa=True)(
                    request=Pedido(), user=utilizador,
                )


class TestInventario:
    def test_toda_a_guarda_de_papel_de_system_config_tem_a_flag(self):
        """Uma rota nova de `system_config` com `require_roles` à antiga voltava a dar
        403 ao Master com chapéu — e não dá erro em lado nenhum a quem a escreve."""
        fonte = (Path(__file__).resolve().parents[2] / "routes" / "system_config.py").read_text("utf-8")
        chamadas = [
            n for n in ast.walk(ast.parse(fonte))
            if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "require_roles"
        ]
        assert len(chamadas) >= 10, "o leitor tem de ler as guardas (contraprova)"
        sem_flag = [
            n.lineno for n in chamadas
            if not any(k.arg == "conta_master_passa"
                       and isinstance(k.value, ast.Constant) and k.value.value is True
                       for k in n.keywords)
        ]
        assert sem_flag == [], f"require_roles sem conta_master_passa=True nas linhas {sem_flag}"
