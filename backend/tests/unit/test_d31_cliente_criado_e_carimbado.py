"""
D-31 — `POST /clients` carimba o cliente na escrita.

Antes, o cliente criado à mão nascia por carimbar. Com o pedido por id
fechado à rede isso deixava de ser inofensivo: um utilizador de uma rede
que não seja a de omissão criava uma ficha que só o grupo incumbente via.
Corrigir só a leitura torna a correcção invisível ao trabalho novo — a lição
do `assigned_to`.
"""
from __future__ import annotations

import contextlib
from unittest.mock import patch

import pytest

from models.client import ClientCreate
from tests.unit.helpers_tenant import (  # noqa: F401
    REDE_DOMUS,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    import services.client_crud as cc
    import services.client_uniqueness as cu

    semear(fake_async_db)
    fake_async_db.clients.docs.clear()
    with contextlib.ExitStack() as pilha:
        pilha.enter_context(tenant_db(fake_async_db, cc, cu))
        pilha.enter_context(patch.object(cc.s3_service, "ensure_client_folder_mapping",
                                         return_value={"success": False}))
        yield fake_async_db, cc


def _dados():
    return ClientCreate(nome="Maria Nova", email="maria@exemplo.pt", skip_welcome_email=True)


@pytest.mark.asyncio
async def test_o_cliente_criado_leva_a_rede_da_empresa_activa(mundo):
    db, cc = mundo
    user = {"id": "u-bruno", "email": "b@domus.pt", "name": "Bruno", "role": "diretor",
            "effective_role": "diretor", "company": "Domus", "active_company_id": "cmp-domus"}
    await cc.run_create_client(_dados(), user)
    gravado = db.clients.docs[0]
    assert gravado["network_id"] == REDE_DOMUS
    assert gravado["company_id"] == "cmp-domus"


@pytest.mark.asyncio
async def test_sem_contexto_de_empresa_nao_se_carimba(mundo):
    """Carimbar a rede errada é permanente — sem contexto, fica por carimbar."""
    db, cc = mundo
    user = {"id": "u-x", "email": "x@x.pt", "name": "X", "role": "diretor", "effective_role": "diretor"}
    await cc.run_create_client(_dados(), user)
    gravado = db.clients.docs[0]
    assert "network_id" not in gravado
    assert "company_id" not in gravado


@pytest.mark.asyncio
async def test_o_cliente_carimbado_abre_ao_criador_pelo_pedido_por_id(mundo):
    """Fim a fim: o que a Domus cria, a Domus abre; a Power não."""
    from services import by_id_scope as guard

    db, cc = mundo
    user = {"id": "u-bruno", "email": "b@domus.pt", "name": "Bruno", "role": "diretor",
            "effective_role": "diretor", "company": "Domus", "active_company_id": "cmp-domus"}
    resposta = await cc.run_create_client(_dados(), user)
    with patch.object(guard, "db", db):
        assert await guard.cliente_no_ambito(resposta.id, user) is True
        ana = {"id": "u-ana", "role": "diretor", "effective_role": "diretor"}
        assert await guard.cliente_no_ambito(resposta.id, ana) is False
