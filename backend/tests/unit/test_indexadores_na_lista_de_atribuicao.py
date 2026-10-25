"""A gestão vê os indexadores da REDE na lista de atribuição, mesmo com uma empresa escolhida (Out 2026).

O QUE O CLIENTE VIU
===================
O CEO e o Diretor não encontravam os utilizadores do Index ao atribuir um processo. A dropdown segue a
EMPRESA do cabeçalho (P5) e as contas do Index estão noutra empresa da rede ou sem empresa nenhuma (a
vista «Sistema»): ficavam de fora, embora a atribuição automática as escolha no pool da rede e o servidor
aceite gravá-las.

O ataque, escrito primeiro: o Diretor da Precision pede a lista de atribuição com a Precision escolhida;
os indexadores da Power (mesma rede) e o indexador sem empresa (pilha da rede de omissão) têm de lá estar.
As contraprovas: o indexador da Domus (outra rede) nunca aparece, e os CONSULTORES continuam a seguir a
empresa (o alargamento é só do Index).
"""
from __future__ import annotations

import pytest

from tests.unit.helpers_tenant import (  # noqa: F401
    REDE_INCUMBENTE,
    db_tenant,  # noqa: F401  (fixture)
    por_id,
    tenant_db as _tenant_db,
)

DIRETOR_PRECISION = {
    "id": "u-dir", "name": "Dir", "email": "dir@x.pt", "role": "diretor", "effective_role": "diretor",
    "vista_empresa_id": "cmp-precision",
}
DIRETOR_DOMUS = {
    "id": "u-dir-domus", "name": "Dir Domus", "email": "dd@x.pt", "role": "diretor",
    "effective_role": "diretor", "vista_empresa_id": "cmp-domus",
}


def _pessoa(uid, role, empresa_id, empresa_nome):
    return {
        "id": uid, "name": uid, "email": f"{uid}@x.pt", "role": role, "is_active": True,
        "company": empresa_nome,
    }, {
        "user_id": uid, "company_id": empresa_id, "company_name": empresa_nome,
        "role": role, "is_default": True,
    }


@pytest.fixture
def equipas(db_tenant, monkeypatch):  # noqa: F811
    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
    db_tenant.user_company_roles.docs.clear()
    for doc, ucr in [
        _pessoa("u-dir", "diretor", "cmp-precision", "Precision Crédito"),
        _pessoa("u-dir-domus", "diretor", "cmp-domus", "Domus"),
        _pessoa("u-cons-precision", "consultor", "cmp-precision", "Precision Crédito"),
        _pessoa("u-cons-power", "consultor", "cmp-power", "Power Real Estate"),
        _pessoa("u-idx-power", "indexacao", "cmp-power", "Power Real Estate"),
        _pessoa("u-idx-domus", "indexacao", "cmp-domus", "Domus"),
    ]:
        db_tenant.users.docs.append(doc)
        db_tenant.user_company_roles.docs.append(ucr)
    # Conta do Index sem empresa nenhuma — a vista «Sistema». É da rede de omissão.
    db_tenant.users.docs.append(
        {"id": "u-idx-sistema", "name": "Index Sistema", "email": "idx@sistema.pt",
         "role": "indexacao", "is_active": True}
    )
    # Um admin sem empresa nunca entra numa lista de atribuição, alargada ou não.
    db_tenant.users.docs.append(
        {"id": "u-admin-sistema", "name": "Admin", "email": "a@sistema.pt", "role": "admin", "is_active": True}
    )
    return db_tenant


def _ctx(fake_db):
    from services import admin_users, admin_users_scope, users_api_list

    return _tenant_db(fake_db, admin_users_scope, users_api_list, admin_users)


@pytest.mark.asyncio
async def test_o_ataque_a_gestao_ve_os_indexadores_da_rede(equipas):
    from services.users_api_list import run_get_staff_users

    with _ctx(equipas):
        lista = await run_get_staff_users(dict(DIRETOR_PRECISION))

    ids = por_id(lista)
    assert "u-idx-power" in ids
    assert "u-idx-sistema" in ids


@pytest.mark.asyncio
async def test_o_pedido_so_do_index_tambem_os_traz(equipas):
    """O detalhe do processo pede `role=indexacao` à parte: a mesma regra."""
    from services.users_api_list import run_get_users

    with _ctx(equipas):
        lista = await run_get_users("indexacao", dict(DIRETOR_PRECISION), for_assignment=True)

    assert por_id(lista) == {"u-idx-power", "u-idx-sistema"}


@pytest.mark.asyncio
async def test_contraprova_o_indexador_de_outra_rede_nunca_aparece(equipas):
    from services.users_api_list import run_get_staff_users

    with _ctx(equipas):
        lista = await run_get_staff_users(dict(DIRETOR_PRECISION))

    assert "u-idx-domus" not in por_id(lista)


@pytest.mark.asyncio
async def test_contraprova_a_domus_nao_herda_a_pilha_da_rede_de_omissao(equipas):
    from services.users_api_list import run_get_staff_users

    with _ctx(equipas):
        lista = await run_get_staff_users(dict(DIRETOR_DOMUS))

    ids = por_id(lista)
    assert "u-idx-domus" in ids
    assert "u-idx-sistema" not in ids
    assert "u-idx-power" not in ids


@pytest.mark.asyncio
async def test_contraprova_os_consultores_continuam_a_seguir_a_empresa(equipas):
    from services.users_api_list import run_get_staff_users

    with _ctx(equipas):
        lista = await run_get_staff_users(dict(DIRETOR_PRECISION))

    ids = por_id(lista)
    assert "u-cons-precision" in ids
    assert "u-cons-power" not in ids
    assert "u-admin-sistema" not in ids


@pytest.mark.asyncio
async def test_um_filtro_de_outro_papel_nao_junta_indexadores(equipas):
    from services.users_api_list import run_get_users

    with _ctx(equipas):
        lista = await run_get_users("consultor", dict(DIRETOR_PRECISION), for_assignment=True)

    assert not {"u-idx-power", "u-idx-sistema"} & por_id(lista)


@pytest.mark.asyncio
async def test_a_listagem_que_nao_e_de_atribuicao_nao_alarga(equipas):
    """A lista de Utilizadores (QA-9) continua estrita à empresa escolhida."""
    from services.users_api_list import run_get_users

    with _ctx(equipas):
        lista = await run_get_users("indexacao", dict(DIRETOR_PRECISION), for_assignment=False)

    assert por_id(lista) == set()
