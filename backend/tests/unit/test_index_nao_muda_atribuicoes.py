"""O Index não muda atribuições (decisão do Flavio, Out 2026).

O perfil `indexacao` vê o processo de um colega na vista normal, mas não mexe na equipa do processo:
nem pelo «Gerir» (`POST /processes/{id}/assign`), nem por «atribuir-me / remover-me». A única forma de
um indexador ficar com um processo é o «Atribuir a mim» do módulo Index (`/index/processes/{id}/assumir`),
com as regras próprias. Decide o perfil EFECTIVO: a mesma pessoa com o chapéu de consultor atribui-se.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from routes import processes as rotas

ROTAS_DE_ATRIBUICAO = ["/{process_id}/assign", "/{process_id}/assign-me", "/{process_id}/unassign-me"]


def _dependencias(dependant):
    for d in dependant.dependencies:
        yield d.call
        yield from _dependencias(d)


@pytest.mark.parametrize("caminho", ROTAS_DE_ATRIBUICAO)
def test_cada_rota_de_atribuicao_recusa_o_index(caminho):
    rota = next(r for r in rotas.router.routes if r.path.endswith(caminho) and "POST" in r.methods)
    assert rotas._nao_e_o_index in set(_dependencias(rota.dependant))


@pytest.mark.asyncio
async def test_o_index_leva_403():
    with patch.object(rotas, "get_effective_role_async", AsyncMock(return_value="indexacao")), \
            pytest.raises(HTTPException) as erro:
        await rotas._nao_e_o_index(MagicMock(), {"id": "u-idx", "role": "indexacao"})
    assert erro.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("papel", ["diretor", "ceo", "admin", "consultor", "intermediario", "administrativo"])
async def test_os_outros_perfis_passam(papel):
    utilizador = {"id": "u-1", "role": papel}
    with patch.object(rotas, "get_effective_role_async", AsyncMock(return_value=papel)):
        assert await rotas._nao_e_o_index(MagicMock(), utilizador) == utilizador


@pytest.mark.asyncio
async def test_decide_o_perfil_efectivo_e_nao_o_de_base():
    """Uma conta de base consultor a trabalhar como Index não atribui; o contrário atribui."""
    with patch.object(rotas, "get_effective_role_async", AsyncMock(return_value="indexacao")), \
            pytest.raises(HTTPException):
        await rotas._nao_e_o_index(MagicMock(), {"id": "u-1", "role": "consultor"})
    with patch.object(rotas, "get_effective_role_async", AsyncMock(return_value="consultor")):
        await rotas._nao_e_o_index(MagicMock(), {"id": "u-1", "role": "indexacao"})
