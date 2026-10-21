"""
Leitura do Log da IA de um processo (`GET /processes/{id}/ai-log`).

A fronteira de rede é do router (`exigir_processo_no_ambito`: 404 igual ao de «não
existe»); aqui aplica-se a regra de visibilidade dos DOCUMENTOS — o log traz nomes de
ficheiros e categorias, tal como a pasta de documentos, por isso um processo ainda por
indexar só o vê quem veria os seus documentos. Devolve também ``pode_reanalisar``, a
resposta da MESMA função que as rotas de IA manual usam para recusar: o ecrã não calcula
a permissão, mostra o botão a quem o servidor autoriza.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from services.document_ai_access import pode_usar_ia_no_processo
from services.document_visibility import assert_can_view_process_documents_by_id
from services.process_ai_log import ESTADOS, listar_accoes_ia


async def run_get_process_ai_log(
    request,
    process_id: str,
    user: dict,
    *,
    pagina: int = 1,
    por_pagina: int = 30,
    estado: Optional[str] = None,
) -> dict:
    if estado is not None and estado not in ESTADOS:
        raise HTTPException(status_code=400, detail="Estado inválido")
    processo = await assert_can_view_process_documents_by_id(user, process_id)
    pagina_do_log = await listar_accoes_ia(
        process_id, pagina=pagina, por_pagina=por_pagina, estado=estado
    )
    pagina_do_log["pode_reanalisar"] = bool(
        processo and await pode_usar_ia_no_processo(request, user, processo)
    )
    return pagina_do_log
