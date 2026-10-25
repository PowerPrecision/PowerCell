"""Registos de Clientes: a origem diz QUEM criou a ficha, não só «Criado pela Equipa» (Out 2026).

A ficha guardava só o EMAIL do autor (`created_by`) e a lista não o projectava: o ecrã só podia mostrar
a origem genérica. Agora o nome grava-se à nascença (`created_by_name`) e a lista resolve-o também para
as fichas antigas, a partir do email, num único pedido. Sem nome (conta apagada, sistema), nada se
inventa: o ecrã mantém «Criado pela Equipa».
"""
from __future__ import annotations

import contextlib
from unittest.mock import patch

import pytest

from models.client import ClientCreate
from tests.unit.helpers_tenant import (  # noqa: F401
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):  # noqa: F811
    import services.client_crud as cc
    import services.client_registered as cr
    import services.client_uniqueness as cu

    semear(fake_async_db)
    fake_async_db.clients.docs.clear()
    with contextlib.ExitStack() as pilha:
        pilha.enter_context(tenant_db(fake_async_db, cc, cu, cr))
        pilha.enter_context(patch.object(cc.s3_service, "ensure_client_folder_mapping",
                                         return_value={"success": False}))
        yield fake_async_db, cc, cr


@pytest.mark.asyncio
async def test_a_ficha_criada_pela_equipa_guarda_o_nome_de_quem_a_criou(mundo):
    db, cc, _ = mundo
    user = {"id": "u-ana", "email": "ana@power.pt", "name": "Ana Silva", "role": "diretor",
            "effective_role": "diretor", "active_company_id": "cmp-power"}
    await cc.run_create_client(
        ClientCreate(nome="Maria Nova", email="maria@exemplo.pt", fonte="staff_created",
                     skip_welcome_email=True),
        user,
    )
    gravado = db.clients.docs[0]
    assert gravado["created_by"] == "ana@power.pt"
    assert gravado["created_by_name"] == "Ana Silva"


@pytest.mark.asyncio
async def test_o_nome_gravado_manda(mundo):
    db, _, cr = mundo
    db.users.docs.append({"id": "u-x", "email": "ana@power.pt", "name": "Outro Nome"})
    nomes = await cr.nomes_dos_autores(
        [{"id": "c1", "created_by": "ana@power.pt", "created_by_name": "Ana Silva"}]
    )
    assert nomes == {"c1": "Ana Silva"}


@pytest.mark.asyncio
async def test_a_ficha_antiga_resolve_o_nome_pelo_email(mundo):
    db, _, cr = mundo
    db.users.docs.append({"id": "u-joao", "email": "joao@power.pt", "name": "João Silva"})
    nomes = await cr.nomes_dos_autores([
        {"id": "c1", "created_by": "joao@power.pt"},
        {"id": "c2", "created_by": " JOAO@power.pt "},
    ])
    assert nomes == {"c1": "João Silva", "c2": "João Silva"}


@pytest.mark.asyncio
async def test_sem_autor_conhecido_nao_se_inventa_nome(mundo):
    _, _, cr = mundo
    nomes = await cr.nomes_dos_autores([
        {"id": "c1", "created_by": "apagado@power.pt"},
        {"id": "c2"},
        {"id": "c3", "created_by": "sistema"},
    ])
    assert nomes == {}
