"""Configurações do sistema por empresa: Admin vê todas, CEO só as dele.

O QUE CORREU MAL
================
`GET /system-config`, `PATCH /system-config/{secção}` e `GET
/system-config/reveal-secrets` estavam em `require_roles([ADMIN, CEO])` —
que autoriza o VERBO — e o `company_id` era um **parâmetro livre** da
query string. Um CEO da Domus (ilha) lia e ESCREVIA a configuração da
Power, com o nome do bucket, o remetente de email e o resto. E o
`/reveal-secrets` nem sequer tinha `company_id`: devolvia sempre as chaves
da configuração GLOBAL (AWS, SMTP, IA) a qualquer CEO.

A decisão de produto (Out 2026): o Admin acede às definições de todas as
empresas do CRM **e à global**; o CEO **só às empresas dele (UCR)** — nunca
à global, nem o da rede principal (revisto: a versão inicial admitia o CEO
da rede de omissão, e os testes que o afirmavam foram INVERTIDOS).

DUAS PERGUNTAS, NÃO UMA
=======================
1. *Esta EMPRESA é minha para configurar?* — o `company_id` pedido.
2. *A configuração GLOBAL (`default`) é minha?* — não é uma empresa, é a
   infraestrutura partilhada (bucket, SMTP do sistema, chave de IA). Só o
   ADMIN.

`TestAExploracao` é o ataque, escrito para morder primeiro.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import (  # noqa: F401  (fixture)
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

ADMIN = {"id": "u-admin", "name": "Admin", "email": "admin@x.pt", "role": "admin"}
CEO_POWER = {"id": "u-ceo-power", "name": "CEO Power", "email": "ceo@power.pt", "role": "ceo"}
CEO_DOMUS = {"id": "u-ceo-domus", "name": "CEO Domus", "email": "ceo@domus.pt", "role": "ceo"}
CONSULTOR = {"id": "u-consultor", "name": "Cons", "email": "c@power.pt", "role": "consultor"}

UCRS_EXTRA = [
    {"user_id": "u-admin", "company_id": "cmp-power", "company_name": "Power Real Estate",
     "role": "admin", "is_default": True},
    {"user_id": "u-ceo-power", "company_id": "cmp-power", "company_name": "Power Real Estate",
     "role": "ceo", "is_default": True},
    {"user_id": "u-ceo-domus", "company_id": "cmp-domus", "company_name": "Domus",
     "role": "ceo", "is_default": True},
    {"user_id": "u-consultor", "company_id": "cmp-power", "company_name": "Power Real Estate",
     "role": "consultor", "is_default": True},
]


@pytest.fixture
def mundo(fake_async_db):
    """Três empresas, duas redes, e uma configuração própria já gravada."""
    import services.system_config as core
    import services.system_config_scope as ambito

    semear(fake_async_db)
    fake_async_db.user_company_roles.docs.extend(dict(u) for u in UCRS_EXTRA)
    fake_async_db.system_config.docs.append({
        "_id": "main",
        "company_id": "default",
        "settings": {"company_name": "Global"},
    })
    fake_async_db.system_config.docs.append({
        "_id": "company:cmp-domus",
        "company_id": "cmp-domus",
        "settings": {"company_name": "Domus"},
        "storage": {"provider": "aws_s3", "aws_secret_access_key": "SEGREDO-DA-DOMUS"},
    })
    core._config_cache.clear()
    # Cada módulo da cadeia que faz `from database import db` no topo tem a
    # SUA referência: sem `ambito` aqui o teste passava ou falhava conforme a
    # ordem de recolha (a bateria de integração corre antes).
    with tenant_db(fake_async_db, core, ambito):
        yield fake_async_db
    core._config_cache.clear()


def _ids_de_config(db):
    return {d["_id"] for d in db.system_config.docs}


# ════════════════════════════════════════════════════════════════════
#  O ATAQUE
# ════════════════════════════════════════════════════════════════════
class TestAExploracao:
    """Cada um destes passava antes deste lote."""

    @pytest.mark.asyncio
    async def test_um_CEO_nao_le_a_configuracao_de_outra_empresa(self, mundo, rede_de_omissao_incumbente):
        from routes.system_config import get_config

        with pytest.raises(HTTPException) as exc:
            await get_config(request=None, company_id="cmp-domus", user=CEO_POWER)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_um_CEO_nao_ESCREVE_na_configuracao_de_outra_empresa(self, mundo, rede_de_omissao_incumbente):
        from routes.system_config import update_config

        antes = [dict(d) for d in mundo.system_config.docs]
        with pytest.raises(HTTPException) as exc:
            await update_config(
                section="storage",
                data={"provider": "none"},
                request=None,
                company_id="cmp-domus",
                user=CEO_POWER,
            )
        assert exc.value.status_code == 404
        assert mundo.system_config.docs == antes, "a recusa não pode ter deixado rasto"

    @pytest.mark.asyncio
    async def test_um_CEO_nao_revela_os_segredos_de_outra_empresa(self, mundo, rede_de_omissao_incumbente):
        from routes.system_config import reveal_secrets

        with pytest.raises(HTTPException) as exc:
            await reveal_secrets(section="storage", request=None, company_id="cmp-domus", user=CEO_POWER)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_um_CEO_nao_cria_configuracao_para_um_id_inventado(self, mundo, rede_de_omissao_incumbente):
        """`get_system_config` CRIA a cópia da global para qualquer id."""
        from routes.system_config import get_config

        antes = _ids_de_config(mundo)
        with pytest.raises(HTTPException):
            await get_config(request=None, company_id="empresa-inventada", user=CEO_POWER)
        assert _ids_de_config(mundo) == antes

    @pytest.mark.asyncio
    @pytest.mark.parametrize("ceo", [CEO_DOMUS, CEO_POWER], ids=["ilha", "rede_principal"])
    async def test_nenhum_CEO_toca_na_configuracao_GLOBAL(self, mundo, rede_de_omissao_incumbente, ceo):
        """A global é a infra partilhada (bucket, SMTP do sistema, IA) e tem
        um único dono: o ADMIN. Nem o CEO da rede principal."""
        from routes.system_config import get_config, reveal_secrets, update_config

        antes = [dict(d) for d in mundo.system_config.docs]
        with pytest.raises(HTTPException) as exc:
            await get_config(request=None, company_id="default", user=ceo)
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException) as exc:
            await reveal_secrets(section="storage", request=None, company_id="default", user=ceo)
        assert exc.value.status_code == 403
        with pytest.raises(HTTPException) as exc:
            await update_config(
                section="storage", data={"provider": "none"},
                request=None, company_id="default", user=ceo,
            )
        assert exc.value.status_code == 403
        assert mundo.system_config.docs == antes

    @pytest.mark.asyncio
    async def test_nenhum_CEO_usa_as_rotas_so_globais(self, mundo, rede_de_omissao_incumbente):
        from routes.system_config import (
            complete_setup,
            list_system_email_configs,
            test_service_connection,
        )

        for chamada in (
            lambda: complete_setup(request=None, user=CEO_DOMUS),
            lambda: list_system_email_configs(request=None, user=CEO_DOMUS),
            lambda: test_service_connection(service="email", request=None, user=CEO_DOMUS),
            lambda: complete_setup(request=None, user=CEO_POWER),
            lambda: list_system_email_configs(request=None, user=CEO_POWER),
            lambda: test_service_connection(service="email", request=None, user=CEO_POWER),
        ):
            with pytest.raises(HTTPException) as exc:
                await chamada()
            assert exc.value.status_code == 403

    @pytest.mark.asyncio
    @pytest.mark.parametrize("nome", [
        "get_system_email_config",
        "update_system_email_config",
        "delete_system_email_config",
        "test_system_email_config",
    ])
    async def test_as_rotas_de_email_do_sistema_por_proposito_tambem(
        self, mundo, rede_de_omissao_incumbente, nome
    ):
        import routes.system_config as rotas
        from services.system_config_system_emails import (
            SystemEmailConfigCreate,
            SystemEmailConfigUpdate,
        )

        extra = {"update_system_email_config": {"payload": SystemEmailConfigUpdate()}}.get(nome, {})
        with pytest.raises(HTTPException) as exc:
            await getattr(rotas, nome)(purpose="DOCUMENTS", request=None, user=CEO_DOMUS, **extra)
        assert exc.value.status_code == 403

        with pytest.raises(HTTPException) as exc:
            await rotas.create_system_email_config(
                payload=SystemEmailConfigCreate(
                    purpose="DOCUMENTS", host="h", user="u", password="p",
                ),
                request=None,
                user=CEO_DOMUS,
            )
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_a_listagem_nao_denuncia_empresas_de_outras_redes(self, mundo, rede_de_omissao_incumbente):
        from routes.system_config import get_available_companies

        res = await get_available_companies(request=None, user=CONSULTOR)
        ids = {c["company_id"] for c in res["companies"]}
        assert "cmp-domus" not in ids
        assert "Domus" not in str(res)

    @pytest.mark.asyncio
    async def test_o_export_permission_nao_cria_configuracao_para_um_id_inventado(
        self, mundo, rede_de_omissao_incumbente
    ):
        from routes.system_config import get_excel_export_permission

        antes = _ids_de_config(mundo)
        with pytest.raises(HTTPException) as exc:
            await get_excel_export_permission(request=None, company_id="cmp-domus", user=CONSULTOR)
        assert exc.value.status_code == 404
        assert _ids_de_config(mundo) == antes


# ════════════════════════════════════════════════════════════════════
#  A CONTRAPROVA — o que NÃO pode deixar de funcionar
# ════════════════════════════════════════════════════════════════════
class TestAContraprova:
    @pytest.mark.asyncio
    async def test_o_ADMIN_le_a_configuracao_de_TODAS_as_empresas(self, mundo, rede_de_omissao_incumbente):
        """O admin só tem UCR na Power — e tem de chegar à Domus."""
        from routes.system_config import get_config

        for company_id in ("default", "cmp-power", "cmp-precision", "cmp-domus"):
            res = await get_config(request=None, company_id=company_id, user=ADMIN)
            assert "config" in res, company_id

    @pytest.mark.asyncio
    async def test_o_ADMIN_escreve_na_configuracao_de_outra_empresa(self, mundo, rede_de_omissao_incumbente):
        from routes.system_config import update_config

        res = await update_config(
            section="storage", data={"provider": "none"},
            request=None, company_id="cmp-domus", user=ADMIN,
        )
        assert res["success"] is True
        doc = next(d for d in mundo.system_config.docs if d["_id"] == "company:cmp-domus")
        assert doc["storage"]["provider"] == "none"

    @pytest.mark.asyncio
    async def test_o_ADMIN_tambem_nao_inventa_empresas(self, mundo, rede_de_omissao_incumbente):
        from routes.system_config import get_config

        antes = _ids_de_config(mundo)
        with pytest.raises(HTTPException) as exc:
            await get_config(request=None, company_id="empresa-inventada", user=ADMIN)
        assert exc.value.status_code == 404
        assert _ids_de_config(mundo) == antes

    @pytest.mark.asyncio
    async def test_o_CEO_le_e_escreve_na_PROPRIA_empresa(self, mundo, rede_de_omissao_incumbente):
        from routes.system_config import get_config, update_config

        res = await get_config(request=None, company_id="cmp-power", user=CEO_POWER)
        assert "config" in res
        res = await update_config(
            section="settings", data={"company_name": "Power SA"},
            request=None, company_id="cmp-power", user=CEO_POWER,
        )
        assert res["success"] is True

    @pytest.mark.asyncio
    async def test_o_CEO_da_ilha_le_a_SUA_empresa(self, mundo, rede_de_omissao_incumbente):
        from routes.system_config import get_config

        res = await get_config(request=None, company_id="cmp-domus", user=CEO_DOMUS)
        assert "config" in res

    @pytest.mark.asyncio
    async def test_so_as_empresas_DELE_a_mesma_rede_nao_chega(self, mundo, rede_de_omissao_incumbente):
        """Decisão do dono do produto: UCR, não rede. A Precision é da mesma
        rede da Power e o CEO da Power NÃO configura a Precision."""
        from routes.system_config import get_config

        with pytest.raises(HTTPException) as exc:
            await get_config(request=None, company_id="cmp-precision", user=CEO_POWER)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_o_ADMIN_mantem_a_global_e_os_segredos_dela(self, mundo, rede_de_omissao_incumbente):
        """A contraprova: retirar a global ao CEO não pode tirá-la ao dono."""
        from routes.system_config import get_config, reveal_secrets

        res = await get_config(request=None, company_id="default", user=ADMIN)
        assert "config" in res
        res = await reveal_secrets(section="storage", request=None, company_id="default", user=ADMIN)
        assert "secrets" in res

    @pytest.mark.asyncio
    async def test_a_regra_nao_depende_da_rede_de_omissao_estar_declarada(self, mundo, monkeypatch):
        """Antes, sem `TENANT_DEFAULT_NETWORK_ID` (dev/CI) o CEO ganhava a
        global. Agora a regra é a mesma com ou sem a variável."""
        from routes.system_config import get_config

        monkeypatch.delenv("TENANT_DEFAULT_NETWORK_ID", raising=False)
        for ceo in (CEO_DOMUS, CEO_POWER):
            with pytest.raises(HTTPException) as exc:
                await get_config(request=None, company_id="default", user=ceo)
            assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_o_reveal_devolve_os_segredos_DA_EMPRESA_pedida_e_nao_os_da_global(
        self, mundo, rede_de_omissao_incumbente
    ):
        """Antes o endpoint nem tinha `company_id`: mostrava sempre a global,
        enquanto o formulário mostrava os campos da empresa."""
        from routes.system_config import reveal_secrets

        res = await reveal_secrets(section="storage", request=None, company_id="cmp-domus", user=ADMIN)
        assert res["secrets"].get("aws_secret_access_key") == "SEGREDO-DA-DOMUS"

    @pytest.mark.asyncio
    async def test_a_listagem_do_ADMIN_traz_todas_as_empresas_do_CRM(self, mundo, rede_de_omissao_incumbente):
        from routes.system_config import get_available_companies

        res = await get_available_companies(request=None, user=ADMIN)
        ids = {c["company_id"] for c in res["companies"]}
        assert ids == {"default", "cmp-power", "cmp-precision", "cmp-domus"}
        nomes = {c["company_id"]: c["company_name"] for c in res["companies"]}
        assert nomes["cmp-domus"] == "Domus"

    @pytest.mark.asyncio
    async def test_a_listagem_do_CEO_traz_so_as_dele(self, mundo, rede_de_omissao_incumbente):
        from routes.system_config import get_available_companies

        res = await get_available_companies(request=None, user=CEO_POWER)
        assert {c["company_id"] for c in res["companies"]} == {"cmp-power"}, "o CEO nunca vê a global"

        res = await get_available_companies(request=None, user=CEO_DOMUS)
        assert {c["company_id"] for c in res["companies"]} == {"cmp-domus"}

    @pytest.mark.asyncio
    async def test_um_consultor_ve_so_a_propria_empresa_na_listagem(self, mundo, rede_de_omissao_incumbente):
        from routes.system_config import get_available_companies

        res = await get_available_companies(request=None, user=CONSULTOR)
        assert {c["company_id"] for c in res["companies"]} == {"cmp-power"}

    @pytest.mark.asyncio
    async def test_o_export_permission_mantem_se_para_a_propria_empresa_e_para_a_global(
        self, mundo, rede_de_omissao_incumbente
    ):
        """Os botões de exportação de TODOS os perfis dependem disto."""
        from routes.system_config import get_excel_export_permission

        for company_id in ("default", "cmp-power"):
            res = await get_excel_export_permission(request=None, company_id=company_id, user=CONSULTOR)
            assert "allow_excel_export" in res, company_id


# ════════════════════════════════════════════════════════════════════
#  A LIGAÇÃO — apagar a guarda de um handler tem de partir um teste
# ════════════════════════════════════════════════════════════════════
ROTAS = Path(__file__).resolve().parents[2] / "routes" / "system_config.py"

#: Handlers que NÃO precisam da guarda, e porquê. Escritas, de propósito:
#: um handler novo sem guarda e sem entrada aqui faz o teste falhar.
SEM_GUARDA = {
    "get_config_fields": "devolve o esquema estático dos campos, sem dados de nenhuma empresa",
    "get_storage_info": "devolve só o fornecedor configurado, a todos os perfis, sem segredos",
    "reset_cache": "restrito a ADMIN (require_roles) e só limpa a cache, não lê nem escreve dados",
}


#: As funções que resolvem o âmbito. Nenhuma delas pode ser contornada
#: por um handler: `exigir_*` e `listar_*` não resolvem o utilizador.
GUARDAS = {
    "resolver_empresa_pedida",
    "resolver_configuracao_global",
    "resolver_empresa_para_leitura",
    "carregar_ambito_de_configuracao",
}


def _handlers():
    arvore = ast.parse(ROTAS.read_text(encoding="utf-8"))
    for no in arvore.body:
        if isinstance(no, ast.AsyncFunctionDef) and any(
            isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
            and isinstance(d.func.value, ast.Name) and d.func.value.id == "router"
            for d in no.decorator_list
        ):
            yield no


class TestAGuardaEstaLigada:
    def test_o_inventario_le_mesmo_as_rotas(self):
        nomes = {h.name for h in _handlers()}
        assert {"get_config", "update_config", "reveal_secrets"} <= nomes
        assert len(nomes) >= 15

    def test_todo_handler_resolve_o_ambito_ou_esta_na_lista_escrita(self):
        em_falta = []
        for h in _handlers():
            if h.name in SEM_GUARDA:
                continue
            fonte = ast.unparse(h)
            if not any(guarda + "(" in fonte for guarda in GUARDAS):
                em_falta.append(h.name)
        assert not em_falta, (
            f"handlers de /system-config sem guarda de âmbito: {em_falta}. "
            f"Ou chamam uma de {sorted(GUARDAS)}, ou entram em SEM_GUARDA "
            "com o motivo."
        )

    def test_a_lista_de_excepcoes_nao_tem_entradas_mortas(self):
        nomes = {h.name for h in _handlers()}
        assert set(SEM_GUARDA) <= nomes

    def test_quem_resolve_o_ambito_recebe_o_request(self):
        """Sem `request` o papel efectivo (X-Active-Role) não se resolve."""
        sem_request = []
        for h in _handlers():
            if h.name in SEM_GUARDA:
                continue
            if "request" not in {a.arg for a in h.args.args}:
                sem_request.append(h.name)
        assert not sem_request, sem_request

    def test_a_contraprova_do_inventario_morde(self):
        """O leitor distingue um handler guardado de um que não o é."""
        guardado = ast.parse(
            "async def a(request, user):\n    await resolver_empresa_pedida(user, request, 'x')"
        ).body[0]
        nu = ast.parse("async def b(request, user):\n    return 1").body[0]
        assert "resolver_empresa_pedida" in ast.unparse(guardado)
        assert "resolver_empresa_pedida" not in ast.unparse(nu)

    def test_as_rotas_so_globais_estao_fechadas_ao_CEO_logo_na_porta(self):
        """Não basta a guarda dentro: a porta (`require_roles`) também diz ADMIN."""
        so_admin = {
            "test_service_connection", "complete_setup", "list_system_email_configs",
            "get_system_email_config", "create_system_email_config",
            "update_system_email_config", "delete_system_email_config",
            "test_system_email_config",
        }
        vistos = set()
        for h in _handlers():
            if h.name in so_admin:
                fonte = ast.unparse(h)
                assert "UserRole.CEO" not in fonte, h.name
                assert "UserRole.ADMIN" in fonte, h.name
                vistos.add(h.name)
        assert vistos == so_admin

    def test_o_reveal_aceita_company_id(self):
        from routes.system_config import reveal_secrets

        assert "company_id" in inspect.signature(reveal_secrets).parameters
