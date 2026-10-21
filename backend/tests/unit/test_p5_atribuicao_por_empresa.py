"""P5 — a dropdown de atribuição segue a EMPRESA do `X-Company-Id`, não a rede inteira.

O QUE A QA VIU
==============
Ao reatribuir um processo, um Diretor da Precision via na dropdown gente da Domus. A rede já estreitava
(Domus é uma ilha), mas a lista de atribuição ficou de fora do estreitamento por EMPRESA que a lista geral
de utilizadores ganhou no QA-9: «as dropdowns de atribuição mantêm o âmbito de rede». Numa instalação
em que as empresas partilham o `network_id` (a migração carimbou todas com a rede de omissão) a rede é a
fronteira errada para uma pergunta que é «quem está nesta empresa?».

O ataque, escrito primeiro: três empresas na MESMA rede; o Diretor da Precision pede a lista de atribuição
com `X-Company-Id = Precision` e não pode ver nem quem só trabalha na Domus nem quem só trabalha na Power.
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


def _pessoa(uid, role, empresa_id, empresa_nome, **extra):
    return {
        "id": uid, "name": uid, "email": f"{uid}@x.pt", "role": role, "is_active": True,
        "company": empresa_nome, **extra,
    }, {
        "user_id": uid, "company_id": empresa_id, "company_name": empresa_nome,
        "role": role, "is_default": True,
    }


@pytest.fixture
def mesma_rede(db_tenant, monkeypatch):  # noqa: F811
    """Power, Precision e Domus na MESMA rede (como a migração as deixou)."""
    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_INCUMBENTE)
    for empresa in db_tenant.companies.docs:
        empresa["network_id"] = REDE_INCUMBENTE
    db_tenant.user_company_roles.docs.clear()

    pessoas = [
        _pessoa("u-dir", "diretor", "cmp-precision", "Precision Crédito"),
        _pessoa("u-cons-precision", "consultor", "cmp-precision", "Precision Crédito"),
        _pessoa("u-cons-power", "consultor", "cmp-power", "Power Real Estate"),
        _pessoa("u-cons-domus", "consultor", "cmp-domus", "Domus"),
        _pessoa("u-carla", "consultor", "cmp-precision", "Precision Crédito"),
    ]
    for doc, ucr in pessoas:
        db_tenant.users.docs.append(doc)
        db_tenant.user_company_roles.docs.append(ucr)
    # A Carla trabalha também na Domus: é da Precision, tem de aparecer.
    db_tenant.user_company_roles.docs.append({
        "user_id": "u-carla", "company_id": "cmp-domus", "company_name": "Domus",
        "role": "consultor", "is_default": False,
    })
    # Conta antiga: só o NOME da empresa no próprio utilizador, sem UCR.
    db_tenant.users.docs.append(
        {"id": "u-legado-domus", "name": "Legado", "email": "l@x.pt", "role": "consultor",
         "is_active": True, "company": "Domus"}
    )
    # Sem empresa nenhuma: não é de ninguém.
    db_tenant.users.docs.append(
        {"id": "u-orfao", "name": "Orfao", "email": "o@x.pt", "role": "consultor", "is_active": True}
    )
    return db_tenant


def _ctx(fake_db):
    from services import admin_users, admin_users_scope, users_api_list

    return _tenant_db(fake_db, admin_users_scope, users_api_list, admin_users)


@pytest.mark.asyncio
async def test_o_ataque_o_diretor_da_precision_nao_ve_a_domus_nem_a_power(mesma_rede):
    from services.users_api_list import run_get_users

    with _ctx(mesma_rede):
        lista = await run_get_users(None, dict(DIRETOR_PRECISION), for_assignment=True)

    ids = por_id(lista)
    assert "u-cons-domus" not in ids
    assert "u-legado-domus" not in ids
    assert "u-cons-power" not in ids
    assert "u-orfao" not in ids


@pytest.mark.asyncio
async def test_contraprova_quem_trabalha_na_precision_aparece(mesma_rede):
    from services.users_api_list import run_get_users

    with _ctx(mesma_rede):
        lista = await run_get_users(None, dict(DIRETOR_PRECISION), for_assignment=True)

    # A Carla tem também um UCR na Domus, mas trabalha na Precision: aparece.
    assert por_id(lista) == {"u-dir", "u-cons-precision", "u-carla"}


@pytest.mark.asyncio
async def test_o_staff_endpoint_segue_a_mesma_regra(mesma_rede):
    from services.users_api_list import run_get_staff_users

    with _ctx(mesma_rede):
        lista = await run_get_staff_users(dict(DIRETOR_PRECISION))

    assert "u-cons-domus" not in por_id(lista)


@pytest.mark.asyncio
async def test_sem_cabecalho_vale_o_ambito_de_rede_de_sempre(mesma_rede):
    """O cabeçalho só estreita: sem ele (ou forjado) nada se alarga nem se esconde a mais."""
    from services.users_api_list import run_get_users

    sem_cabecalho = {k: v for k, v in DIRETOR_PRECISION.items() if k != "vista_empresa_id"}
    with _ctx(mesma_rede):
        lista = await run_get_users(None, sem_cabecalho, for_assignment=True)

    assert {"u-cons-precision", "u-cons-power", "u-cons-domus"} <= por_id(lista)


@pytest.mark.asyncio
async def test_um_cabecalho_forjado_nao_alarga(mesma_rede):
    from services.users_api_list import run_get_users

    forjado = {**DIRETOR_PRECISION, "vista_empresa_id": "cmp-inexistente"}
    with _ctx(mesma_rede):
        lista = await run_get_users(None, forjado, for_assignment=True)

    # Cai no âmbito normal de rede — nunca num âmbito mais largo do que o de quem pergunta.
    assert "u-cons-domus" in por_id(lista)  # a rede é a mesma neste cenário…
    assert "u-orfao" in por_id(lista)  # …e a pilha por carimbar é da rede de omissão


@pytest.mark.asyncio
async def test_quem_ja_esta_no_processo_nao_desaparece_da_lista(mesma_rede):
    """Uma colega de outra empresa já atribuída continua nas opções: senão gravar retira-a em silêncio."""
    from services.users_api_list import run_get_users

    mesma_rede.processes.docs.append({
        "id": "p-misto", "client_name": "Misto", "status": "novo",
        "company_id": "cmp-precision", "network_id": REDE_INCUMBENTE,
        "assigned_consultor_ids": ["u-cons-power"], "assigned_consultor_id": "u-cons-power",
    })
    with _ctx(mesma_rede):
        sem_processo = await run_get_users(None, dict(DIRETOR_PRECISION), for_assignment=True)
        com_processo = await run_get_users(
            None, dict(DIRETOR_PRECISION), for_assignment=True, process_id="p-misto",
        )

    assert "u-cons-power" not in por_id(sem_processo)
    assert "u-cons-power" in por_id(com_processo)
    assert "u-cons-domus" not in por_id(com_processo)
