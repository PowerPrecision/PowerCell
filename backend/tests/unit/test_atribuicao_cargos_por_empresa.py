"""Gestão de Atribuições: o Index (e os outros cargos) dados POR EMPRESA aparecem (Nov 2026).

O caso real (Larisa Dordea): 20 ficheiros à espera da Indexação, ninguém
sabia a que Index o processo estava, e na Gestão de Atribuições — mesmo com
o Master — não apareciam os utilizadores Index nem todos os atribuíveis.

Duas causas, cada uma com o seu ataque:

1. As listas perguntavam só a `users.role` / `additional_roles`. Quem tinha o
   cargo na grelha de acessos por empresa (UCR, o perfil efectivo) trabalhava
   como Index mas não existia para a atribuição — nem para a automática.
2. Um processo SEM carimbo de rede tinha alcance vazio: o Master não podia
   atribuir ninguém (só via quem já lá estava).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from services.assignment_network_guard import redes_permitidas
from services.tenant_network import TenantScope
from tests.unit.helpers_tenant import (
    ANA,
    BRUNO,
    REDE_DOMUS,
    REDE_INCUMBENTE,
    db_tenant,  # noqa: F401  (fixture)
    rede_de_omissao_incumbente,  # noqa: F401  (fixture)
    tenant_db as _tenant_db,
)

MASTER = {"id": "u-master", "name": "Master", "email": "m@sistema.pt", "role": "master"}
#: Consultora na conta, mas Index na Precision (só no UCR).
IRIS = {"id": "u-iris", "name": "Iris", "email": "iris@precision.pt", "role": "consultor"}
#: Index pelo alias legado `index`.
LEGADO = {"id": "u-idx-legado", "name": "Index Antigo", "email": "idx@precision.pt", "role": "index"}
#: Index da Domus (outra rede) — nunca entra num processo da Power.
DINA = {"id": "u-dina", "name": "Dina", "email": "dina@domus.pt", "role": "indexacao"}
#: Ex-Index: o UCR foi apagado. Não pode voltar a aparecer como Index.
VELHA = {"id": "u-velha", "name": "Velha", "email": "velha@precision.pt", "role": "admin"}


@pytest.fixture
def casa(db_tenant):  # noqa: F811
    db_tenant.user_company_roles.docs.extend([
        {"user_id": "u-iris", "company_id": "cmp-precision", "company_name": "Precision Crédito",
         "role": "consultor", "is_default": True},
        {"user_id": "u-iris", "company_id": "cmp-power", "company_name": "Power Real Estate",
         "role": "indexacao", "is_default": False},
        {"user_id": "u-idx-legado", "company_id": "cmp-precision",
         "company_name": "Precision Crédito", "role": "index", "is_default": True},
        {"user_id": "u-dina", "company_id": "cmp-domus", "company_name": "Domus",
         "role": "indexacao", "is_default": True},
        {"user_id": "u-velha", "company_id": "cmp-precision", "company_name": "Precision Crédito",
         "role": "indexacao", "is_default": True, "is_deleted": True},
    ])
    empresa = {"u-ana": "Power Real Estate", "u-bruno": "Domus", "u-iris": "Precision Crédito", "u-idx-legado": "Precision Crédito",
               "u-dina": "Domus", "u-velha": "Precision Crédito"}
    for u in (ANA, BRUNO, MASTER, IRIS, LEGADO, DINA, VELHA):
        db_tenant.users.docs.append({
            **u, "is_active": True, **({"company": empresa[u["id"]]} if u["id"] in empresa else {}),
        })
    # O processo legado da Power: nunca recebeu carimbo de rede.
    db_tenant.processes.docs.append(
        {"id": "p-legado", "client_name": "Larisa", "status": "novo"},
    )
    return db_tenant


def _ctx(fake_db):
    from services import (
        admin_users_scope,
        assignment_network_guard,
        process_assignment,
        process_staff_assignment,
        role_ucr,
        users_api_list,
    )

    return _tenant_db(
        fake_db, assignment_network_guard, process_staff_assignment,
        admin_users_scope, role_ucr, users_api_list, process_assignment,
    )


class TestOsCargosDadosPorEmpresa:

    @pytest.mark.asyncio
    async def test_o_Index_so_no_UCR_aparece_na_lista_do_Master(self, casa):
        from services.users_api_list import run_get_users

        with _ctx(casa):
            lista = await run_get_users(None, MASTER, for_assignment=True)

        por_id = {u["id"]: u for u in lista}
        assert "u-iris" in por_id
        # A interface põe-na no Select do Index por estes papéis, não pelo `role`.
        assert "indexacao" in por_id["u-iris"]["company_roles"]

    @pytest.mark.asyncio
    async def test_o_pedido_de_indexadores_traz_o_UCR_e_o_alias_legado(self, casa):
        from services.users_api_list import run_get_users

        with _ctx(casa):
            lista = await run_get_users("indexacao", MASTER, for_assignment=True)

        ids = {u["id"] for u in lista}
        assert {"u-iris", "u-idx-legado"} <= ids

    @pytest.mark.asyncio
    async def test_um_UCR_apagado_nao_conta(self, casa):
        from services.users_api_list import run_get_users

        with _ctx(casa):
            lista = await run_get_users("indexacao", MASTER, for_assignment=True)

        assert "u-velha" not in {u["id"] for u in lista}

    @pytest.mark.asyncio
    async def test_a_atribuicao_automatica_encontra_o_Index_do_UCR(self, casa):
        from services import network_triage
        from services.process_assignment import _indexadores_da_equipa

        with _ctx(casa), patch.object(network_triage, "user_ids_da_rede", _sem_limite):
            pool = await _indexadores_da_equipa({"id": "p-power"})

        assert {"u-iris", "u-idx-legado"} <= {u["id"] for u in pool}

    @pytest.mark.asyncio
    async def test_quem_tem_o_Index_no_UCR_e_indexador_para_a_fila(self, casa):
        from services.role_ucr import PAPEIS_DO_INDEX, tem_papel

        with _ctx(casa):
            assert await tem_papel("u-iris", PAPEIS_DO_INDEX) is True
            assert await tem_papel("u-velha", PAPEIS_DO_INDEX) is False
            assert await tem_papel("u-ana", PAPEIS_DO_INDEX) is False


async def _sem_limite(_rede):
    return None


class TestOProcessoSemCarimboDeRede:

    def test_o_alcance_e_a_rede_de_omissao(self, rede_de_omissao_incumbente):  # noqa: F811
        assert redes_permitidas(TenantScope(sem_fronteira=True), {"id": "p"}) == {REDE_INCUMBENTE}

    def test_sem_rede_de_omissao_configurada_nao_inventa_nenhuma(self, monkeypatch):
        monkeypatch.delenv("TENANT_DEFAULT_NETWORK_ID", raising=False)
        assert redes_permitidas(TenantScope(sem_fronteira=True), {"id": "p"}) == set()

    @pytest.mark.asyncio
    async def test_o_Master_ve_a_equipa_da_rede_dona_e_nao_a_Domus(
        self, casa, rede_de_omissao_incumbente,  # noqa: F811
    ):
        from services.users_api_list import run_get_users

        with _ctx(casa):
            lista = await run_get_users(None, MASTER, for_assignment=True, process_id="p-legado")

        ids = {u["id"] for u in lista}
        assert {"u-ana", "u-iris", "u-idx-legado"} <= ids
        assert "u-dina" not in ids and "u-bruno" not in ids
        assert REDE_DOMUS  # a outra rede existe no cenário
