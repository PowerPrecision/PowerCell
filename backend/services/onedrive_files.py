"""`GET /onedrive/files/{client_name}` — fechado (Lote 7, D-19).

PORQUE É QUE ISTO DEIXOU DE LISTAR FICHEIROS
============================================
Esta função resolvia o processo por
``{"client_name": {"$regex": nome, "$options": "i"}}`` — **parcial e não
escapado** — e chamava `s3_storage.list_files` **sem** `s3_folder`,
protegida só por `Depends(get_current_user)`. Três defeitos numa linha:

1. **Sem guarda de visibilidade nenhuma.** Qualquer sessão autenticada
   (`indexacao`, `parceiro`, um consultor de outra rede) enumerava os
   documentos de um cliente escrevendo o nome dele no URL. O caminho
   canónico tem `assert_can_view_process_documents`; este não tinha nada.

2. **Regex parcial e não escapado.** `/onedrive/files/a` casava com o
   primeiro processo com um «a» no nome, e um parêntese no nome ia cru
   para o motor de regex — o defeito que o `run_auto_map_client_s3_folders`
   corrigiu com `re.escape`, aqui com outra porta.

3. **O recurso por NOME, sempre.** Sem `s3_folder`, o `list_files` toma o
   ramo legado mesmo para uma ficha correctamente mapeada pelo ID. Era a
   ÚNICA superfície do sistema a fazê-lo incondicionalmente: tinha a
   colisão da D-19 com força total, e apagar o recurso por nome partia-a
   por inteiro.

PORQUE É QUE NÃO SE ENDUREÇE — FECHA-SE
=======================================
Uma guarda de visibilidade não resolve o problema de fundo: **um nome não
é uma identidade.** Dois homónimos exactos continuariam a servir os
documentos de um deles, à escolha do Mongo, e é exactamente essa a D-19. O
caminho canónico existe e recebe um ID:

    GET /api/documents/client/{client_id}/files

410 e não 404 nem 405, pelo precedente do `POST /api/activities`: o
caminho `/onedrive/files` continua a existir para a listagem por pasta, e
um 405 lê-se como avaria de encaminhamento. A mensagem diz para onde ir.

A recusa é a PRIMEIRA instrução — não vai à base de dados. Se fosse
depois do `find_one`, um 410 para um nome existente e um 404 para um
inexistente distinguiam-se, e o endpoint continuava a responder à
pergunta «este cliente existe?» (é a regra da guarda do Portal: a ordem
das verificações é o que impede o código de resposta de virar oráculo).

Cobertura: `tests/unit/test_documentos_por_nome_de_cliente.py`.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException

logger = logging.getLogger(__name__)

MENSAGEM = (
    "Endpoint descontinuado: a listagem de documentos por NOME de cliente "
    "foi removida (um nome não identifica um cliente — dois homónimos "
    "partilhavam a resposta). Use GET /api/documents/client/{client_id}/files, "
    "que recebe o id e aplica a guarda de visibilidade do processo."
)


async def run_get_client_files_by_name(
    client_name: str,
    subfolder: str,
    user: dict,
):
    """Recusa com 410. Ver o cabeçalho do módulo."""
    logger.warning(
        "[ONEDRIVE-FILES] Tentativa de listagem por nome (410): user=%s",
        (user or {}).get("id"),
    )
    raise HTTPException(status_code=410, detail=MENSAGEM)
