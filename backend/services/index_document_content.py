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
5. **`?download=true` é o MESMO caminho com `Content-Disposition: attachment`** (Out 2026): mesma fronteira,
   mesma visibilidade, mesma posse da chave, mesmos três tipos — nada se afrouxa para descarregar. Serve o que
   o registo diz (o original; o PDF limpo depois de o original ser purgado). Uma descarga deixa RASTO no trilho de
   auditoria (só ids e o papel efectivo, nunca o nome do ficheiro) e esse rasto nunca faz a descarga falhar:
   levar para casa o documento de um cliente é mais do que olhar para ele.
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


async def _auditar_descarga(user: dict, processo: dict, document_id: str, request=None) -> None:
    """Rasto SÓ com ids e o papel efectivo. Nunca levanta (observa, não intercepta)."""
    try:
        from services.audit_trail_service import log_audit_event
        from services.tenant_access_context import resolver_papel_efectivo

        papel = await resolver_papel_efectivo(user, request)
        await log_audit_event(
            process_id=processo["id"], user=user, action="Descarregou um documento (pesquisa do Index)",
            field="documento", request=request,
            metadata={"origem": "index", "document_id": document_id, "papel_efectivo": papel},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[INDEX] Auditoria da descarga não gravada: %s", type(exc).__name__)


async def run_conteudo_do_documento(user: dict, document_id: str, *, descarregar: bool = False, request=None):
    """Os bytes do documento: `inline` para o ecrã o mostrar sem sair da pesquisa, ou `attachment` (`descarregar`)."""
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

    resposta = await servir_ficheiro_do_s3(
        documento["s3_path"], documento.get("filename") or documento["s3_path"].rsplit("/", 1)[-1],
        referencia=_texto(document_id), tipo_pelo=documento["s3_path"], descarregar=descarregar,
    )
    if descarregar:
        # depois de o ficheiro existir (um 404/503/413 não é uma descarga) e antes de os bytes saírem
        await _auditar_descarga(user, processo, _texto(document_id), request)
    return resposta


async def run_conteudo_do_ficheiro_do_processo(
    user: dict, process_id: str, document_id: str, *, descarregar: bool = False, request=None
):
    """Os bytes de UM ficheiro da bancada de um processo (qualquer tipo que o Index lista), para ver ou descarregar.

    `GET /api/index/processes/{process_id}/files/{document_id}/content`. É o «Ver documento» e o «Download» de cada
    linha da aba Documentos: ao contrário do atalho da pesquisa (só recibo/extrato/declaração), a bancada lista
    TODO o dossier do processo — a identificação incluída, que o Index precisa de abrir para limpar —, por isso
    aqui não há filtro de tipo. **O resto da parede é a mesma**: o processo tem de ser do âmbito (404 uniforme), o
    ficheiro tem de ser DESSE processo (um `document_id` de outro processo é 404, não 403: não se confirma que
    existe), visibilidade dos documentos, posse da chave S3 por segmento, tecto e rasto de auditoria na descarga.
    """
    documento: Optional[dict] = await db.document_metadata.find_one(
        {"id": _texto(document_id), "process_id": _texto(process_id), "file_state": {"$ne": "purgado"}},
        {"_id": 0, "id": 1, "process_id": 1, "s3_path": 1, "filename": 1},
    )
    processo = await _processo_no_ambito_ou_404(_texto(process_id), user)
    if not documento or not documento.get("s3_path"):
        raise HTTPException(status_code=404, detail=ERRO_NAO_ENCONTRADO)
    await assert_can_view_process_documents(user, processo)

    from services.financial_validation import _exigir_posse_do_comprovativo

    await _exigir_posse_do_comprovativo(documento["s3_path"], "process", processo, processo.get("client_id"))

    resposta = await servir_ficheiro_do_s3(
        documento["s3_path"], documento.get("filename") or documento["s3_path"].rsplit("/", 1)[-1],
        referencia=_texto(document_id), tipo_pelo=documento["s3_path"], descarregar=descarregar,
    )
    if descarregar:
        await _auditar_descarga(user, processo, _texto(document_id), request)
    return resposta


__all__ = ["TIPOS_QUE_A_PESQUISA_MOSTRA", "run_conteudo_do_documento", "run_conteudo_do_ficheiro_do_processo"]
