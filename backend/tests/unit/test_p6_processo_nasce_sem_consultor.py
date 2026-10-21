"""P6 — um processo novo NASCE sem consultor; a distribuição é manual.

O que a QA viu: o sistema atribuía o processo a um consultor sozinho, no momento de o criar. Eram dois
caminhos, ambos em `services/process_create.py`:

1. `apply_creator_role_assignment` carimbava como CONSULTOR quem criava com o perfil de consultor ou de
   diretor (o sistema «escolhia» o consultor por quem calhava a carregar no botão);
2. a Via Verde (`skip_index`) chamava `assign_to_least_busy_consultant` à nascença.

A atribuição que se mantém é a que alguém ESCOLHE (Atribuição / Sala de Triagem) e a da automação de
fase configurável depois da Index — não é criação. O intermediário que cria continua como mediador.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios, codigo_sem_comentarios


@pytest.mark.parametrize("papel", ["consultor", "diretor", "admin", "ceo", "master", "administrativo"])
def test_ninguem_cria_um_processo_com_consultor_a_nascenca(papel):
    from services.process_create import apply_creator_role_assignment

    doc: dict = {}
    apply_creator_role_assignment(doc, {"id": "u1", "name": "Ana", "role": papel, "effective_role": papel})
    assert not any("consultor" in chave or "consultant" in chave for chave in doc), doc


def test_o_perfil_efectivo_e_que_conta_e_nunca_da_consultor():
    """Um admin que veste o chapéu de consultor também não ganha o processo."""
    from services.process_create import apply_creator_role_assignment

    doc: dict = {}
    apply_creator_role_assignment(
        doc, {"id": "u1", "name": "Zé", "role": "admin", "effective_role": "consultor"},
    )
    assert doc == {}


def test_o_intermediario_que_cria_continua_como_mediador():
    from services.process_create import apply_creator_role_assignment

    doc: dict = {}
    apply_creator_role_assignment(doc, {"id": "u2", "name": "Rui", "effective_role": "intermediario"})
    assert doc["assigned_mediador_ids"] == ["u2"]
    assert not any("consultor" in chave for chave in doc)


@pytest.mark.asyncio
async def test_a_via_verde_nao_atribui_consultor_a_nascenca():
    from services import process_assignment
    from services.process_create import maybe_auto_assign_indexer_on_create

    escolher = AsyncMock(side_effect=AssertionError("a criação não escolhe consultor"))
    indexador = AsyncMock(side_effect=AssertionError("a Via Verde também não passa pelo Index"))
    doc = {"skip_index": True}
    with patch.object(process_assignment, "assign_to_least_busy_consultant", escolher), \
            patch.object(process_assignment, "assign_to_indexer", indexador):
        await maybe_auto_assign_indexer_on_create("p1", doc, is_lead=False, initial_status="novo")

    escolher.assert_not_called()
    indexador.assert_not_called()
    assert not any("consultor" in chave or "consultant" in chave for chave in doc)


@pytest.mark.asyncio
async def test_contraprova_o_processo_normal_continua_a_entrar_na_fila_do_index():
    """Sem a contraprova, apagar a função inteira também passava."""
    from services import process_assignment
    from services.process_create import maybe_auto_assign_indexer_on_create

    indexador = AsyncMock(return_value=(True, {"assigned": True, "assigned_indexacao_id": "i1", "indexacao_name": "Ind"}, "ok"))
    doc: dict = {}
    with patch.object(process_assignment, "assign_to_indexer", indexador):
        await maybe_auto_assign_indexer_on_create("p1", doc, is_lead=False, initial_status="novo")

    indexador.assert_awaited_once()
    assert doc["assigned_indexacao_id"] == "i1"


def test_guarda_de_fonte_o_modulo_de_criacao_nao_conhece_o_motor_de_consultores():
    from services import process_create

    import inspect

    fonte = codigo_sem_comentarios(inspect.getsource(process_create))
    assert "assign_to_least_busy_consultant" not in fonte
    assert "build_set_consultor_fields" not in fonte
    # …e a contraprova de que a guarda lê mesmo o módulo certo:
    assert "build_set_mediador_fields" in fonte
    assert "assign_to_indexer" in codigo_da_funcao_sem_comentarios(process_create.maybe_auto_assign_indexer_on_create)


def test_o_broadcast_de_criacao_nao_anuncia_consultor():
    from services.process_create import build_create_broadcast_names

    for papel in ("consultor", "diretor"):
        consultores, mediadores = build_create_broadcast_names({"name": "Ana", "role": papel})
        assert consultores == [] and mediadores == []
