"""«Ver documento» na pesquisa avançada do Index: os bytes de UM documento de um processo (Out 2026).

`GET /api/index/documents/{document_id}/content`. O endpoint de pré-visualização das leads
(`/financial-validation/lead/{id}/files/{file_id}/content`) resolve ficheiros que um PARCEIRO enviou
para uma lead (`db.documents`, por cliente); os resultados da pesquisa são `document_metadata` de um
PROCESSO. São registos diferentes, com donos diferentes — por isso este endpoint é irmão e não o mesmo,
e partilha com aquele só o que é de facto comum (`previsualizacao_de_ficheiros`: tipos, tecto, blocos).

REGRAS QUE NÃO SE PODEM PERDER
------------------------------
1. **O id é do documento, a chave sai do REGISTO** — nunca do pedido. Um registo com a chave
   envenenada (fora da pasta deste caso) não abre o bucket: a mesma guarda de posse do comprovativo
   (raiz documental + pasta do processo/cliente, por segmento).
2. **Só o que a pesquisa pode mostrar**: documentos já analisados como recibo, declaração de efetividade
   ou extrato. A identificação (cartão de cidadão, passaporte) nunca sai por aqui, nem um ficheiro por
   analisar — o atalho serve a pesquisa e não é um explorador de ficheiros.
3. **A fronteira é a do PROCESSO** (dono + redes convidadas; Master na vista «Sistema»), e a recusa é
   sempre **404 igual ao de «não existe»**: um id de outra rede não se distingue de um inexistente. Só
   DEPOIS vem a visibilidade dos documentos do processo (403), que já só diz respeito a quem o vê.
4. Um original `purgado` serve o PDF limpo que o substituiu (o `s3_path` já aponta para ele) e o tipo
   decide-se pela CHAVE, não pelo nome antigo.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException

from database import db
from services.document_visibility import assert_can_view_process_documents
from services.index_ai import TIPO_DECLARACAO, TIPO_EXTRATO, TIPO_RECIBO
from services.previsualizacao_de_ficheiros import servir_ficheiro_do_s3
from services.role_scope import fronteira_levantada
from services.tenant_network import processo_no_ambito, resolve_tenant_scope

logger = logging.getLogger(__name__)

ERRO_NAO_ENCONTRADO = "Documento não encontrado."
#: Os únicos tipos de ficheiro que este atalho serve (os que a pesquisa por documento devolve).
TIPOS_QUE_A_PESQUISA_MOSTRA = frozenset({TIPO_RECIBO, TIPO_EXTRATO, TIPO_DECLARACAO})


def _texto(valor) -> str:
    return str(valor).strip() if valor not in (None, "") else ""


async def _processo_no_ambito_ou_404(process_id: str, user: dict) -> dict:
    """O processo (documento inteiro), se existe, está vivo e é do âmbito de quem pede; senão 404."""
    processo = await db.processes.find_one({"id": process_id, "is_deleted": {"$ne": True}}, {"_id": 0})
    if not processo:
        raise HTTPException(status_code=404, detail=ERRO_NAO_ENCONTRADO)
    if not fronteira_levantada(user):
        scope = await resolve_tenant_scope(user)
        if not processo_no_ambito(processo, scope):
            logger.warning("[INDEX] %s pediu um documento do processo %s, fora da sua rede.", (user or {}).get("id"), process_id)
            raise HTTPException(status_code=404, detail=ERRO_NAO_ENCONTRADO)
    return processo


async def run_conteudo_do_documento(user: dict, document_id: str):
    """Os bytes do documento, em `inline`, para o ecrã o mostrar sem sair da pesquisa."""
    documento: Optional[dict] = await db.document_metadata.find_one(
        {"id": _texto(document_id)},
        {"_id": 0, "id": 1, "process_id": 1, "s3_path": 1, "filename": 1, "index_facts.tipo": 1},
    )
    tipo = ((documento or {}).get("index_facts") or {}).get("tipo")
    if not documento or tipo not in TIPOS_QUE_A_PESQUISA_MOSTRA or not documento.get("s3_path"):
        raise HTTPException(status_code=404, detail=ERRO_NAO_ENCONTRADO)

    processo = await _processo_no_ambito_ou_404(_texto(documento.get("process_id")), user)
    await assert_can_view_process_documents(user, processo)

    # A mesma guarda de posse do comprovativo: a chave tem de estar numa pasta deste caso.
    from services.financial_validation import _exigir_posse_do_comprovativo

    await _exigir_posse_do_comprovativo(documento["s3_path"], "process", processo, processo.get("client_id"))

    return await servir_ficheiro_do_s3(
        documento["s3_path"], documento.get("filename") or documento["s3_path"].rsplit("/", 1)[-1],
        referencia=_texto(document_id), tipo_pelo=documento["s3_path"],
    )


__all__ = ["TIPOS_QUE_A_PESQUISA_MOSTRA", "run_conteudo_do_documento"]
