"""`pode_ver_documentos` no detalhe do processo: a MESMA guarda das rotas de documentos, calculada ao servir.

Sem ela o ecrã pedia `/documents/portal-requests/{id}` a um utilizador que não pode ler os documentos
(processo por indexar e não atribuído) e levava o 403 por desenho. Aqui afirma-se o que o campo diz
em cada caso — e que uma falha da pergunta deixa o campo por preencher (nunca um `False` por erro).
"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from services import process_detail
from tests.unit.helpers_fonte import codigo_sem_comentarios

GUARDA = "services.document_visibility.assert_can_view_process_documents"


@pytest.mark.asyncio
async def test_permitido_diz_true():
    processo = {"id": "p"}
    with patch(GUARDA, AsyncMock(return_value=None)):
        await process_detail.anexar_permissao_de_documentos(processo, {"id": "u"})
    assert processo["pode_ver_documentos"] is True


@pytest.mark.asyncio
async def test_recusado_diz_false_e_nao_levanta():
    processo = {"id": "p"}
    with patch(GUARDA, AsyncMock(side_effect=HTTPException(status_code=403, detail="x"))):
        await process_detail.anexar_permissao_de_documentos(processo, {"id": "u"})
    assert processo["pode_ver_documentos"] is False


@pytest.mark.asyncio
async def test_falha_da_pergunta_deixa_o_campo_por_preencher():
    # Um `False` por erro tiraria os pedidos a quem os pode ver por um soluço.
    processo = {"id": "p", "pode_ver_documentos": True}
    with patch(GUARDA, AsyncMock(side_effect=RuntimeError("bd em baixo"))):
        await process_detail.anexar_permissao_de_documentos(processo, {"id": "u"})
    assert "pode_ver_documentos" not in processo


def test_o_detalhe_chama_a_pergunta():
    fonte = codigo_sem_comentarios(
        __import__("inspect").getsource(process_detail.run_get_process_detail)
    )
    assert "anexar_permissao_de_documentos(process, user)" in fonte
