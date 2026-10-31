"""
====================================================================
PORTAL DO PARCEIRO — ANULAR UM ENVIO (Out 2026)
====================================================================
O PEDIDO (dono do produto)
  «O parceiro quando se engana no documento não tem como anular e voltar a
  submeter.» O parceiro passa a poder ANULAR um ficheiro que ele próprio
  enviou; o caso volta a ficar como estava antes desse envio (um pedido
  cumprido só por esse ficheiro volta a pendente) e ele envia o correcto.

NADA SE APAGA (soft delete)
  * o registo em `db.documents`:
      - envio solto → `is_deleted: True`, `status: "eliminado"` e o rasto
        em `anulado` (quem, quando, de onde);
      - ficheiro dentro de um pedido → sai de `attached_files` e passa para
        `attached_files_anulados`; o estado do pedido recalcula-se com a
        MESMA regra de quando a equipa apaga (`rebuild_after_removal`);
  * o objecto no S3 NÃO se apaga: MOVE-SE (copiar → verificar → reapontar →
    só depois retirar a origem, a ordem de `partner_lead_files`) para
    `Documentação Clientes/_Anulados pelo parceiro/{caso}/{ficheiro}/`.
    Fica fora da pasta do processo — o separador Documentos, a bancada do
    Index e a recolha de ficheiros do S3 deixam de o ver sem ser preciso
    ensinar-lhes uma regra nova — mas DENTRO da raiz documental;
  * o registo de metadados (`document_metadata`) desliga-se do processo
    (`process_id: None`, sai da fila do Index) e guarda o processo de onde
    veio em `anulado.process_id`. Desligar é o que tira o ficheiro errado
    do motor financeiro e da análise, que lêem por `process_id`.

AS GUARDAS (pela ordem)
  1. o caso é deste parceiro (`resolver_caso`: 404 igual a inexistente);
  2. o ficheiro está entre os que ele VÊ no caso (404 igual);
  3. foi ELE que o enviou — o que a equipa ou o cliente juntaram não se
     anula daqui (403);
  4. POSSE da chave S3 (`assert_portal_file_key_e_do_cliente`: raiz
     documental + pasta do cliente), antes de tocar no objecto — o registo
     pode ter um `s3_path` envenenado;
  5. ainda dá para anular: o caso não expirou nem seguiu já associado, o
     comprovativo de uma lead que já passou à equipa não se retira, e o que
     a equipa já TRATOU (Index leu, revisão decidida, PDF limpo) também não
     — aí fala-se com a equipa (409, com o motivo).
====================================================================
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from database import db
from services.document_portal_revoke import rebuild_after_removal
from services.partner_drafts import e_comprovativo_de_pagamento
from services.partner_portal_read import Caso, ficheiros_internos, resolver_caso
from services.partner_visibility import autoria_do_parceiro
from services.portal_upload_ops import assert_portal_file_key_e_do_cliente
from services.s3_document_root import RAIZ, dentro_da_pasta
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)

#: Para onde vão os objectos anulados. Dentro da raiz documental, fora de
#: qualquer pasta de cliente.
PASTA_DOS_ANULADOS = f"{RAIZ}_Anulados pelo parceiro"

ERRO_FICHEIRO_NAO_ENCONTRADO = "Ficheiro não encontrado."
ERRO_NAO_FOI_O_PARCEIRO = "Só pode anular os ficheiros que o próprio enviou."
ERRO_CASO_FECHADO = "Este caso já não aceita alterações por aqui. Fale com o seu consultor."
ERRO_COMPROVATIVO_JA_SEGUIU = (
    "O comprovativo de pagamento já seguiu para a equipa e não pode ser anulado. "
    "Envie o correcto e explique na conversa com a equipa."
)
ERRO_JA_TRATADO = (
    "A equipa já tratou este documento e já não pode ser anulado. "
    "Envie o correcto e avise a equipa na conversa."
)
ERRO_CONCORRENCIA = "O documento foi alterado entretanto. Actualize a página e tente novamente."
ERRO_ARMAZENAMENTO = "Não foi possível anular o envio agora. Tente novamente dentro de momentos."

#: Estados da revisão da IA que ainda não são uma decisão da equipa.
_REVISAO_POR_DECIDIR = (None, "", "pending", "pending_review")


def ja_foi_tratado(meta: Optional[dict]) -> bool:
    """A equipa já fez alguma coisa com este ficheiro? (PURA)

    A categorização automática NÃO conta: corre sozinha logo a seguir ao
    envio. Conta o que alguém da equipa (ou o Index) decidiu a partir dele.
    """
    if not meta:
        return False
    if meta.get("index_facts"):
        return True
    if meta.get("ai_applied_fields") or meta.get("ai_reviewed_by"):
        return True
    if meta.get("ai_review_status") not in _REVISAO_POR_DECIDIR:
        return True
    if meta.get("file_state") in ("sanitizado", "purgado") or meta.get("is_clean_pdf"):
        return True
    return False


def chave_na_pasta_dos_anulados(caso_id: str, file_id: str, chave: str) -> str:
    """O destino de um objecto anulado: um por ficheiro, nunca sobrescreve outro."""
    nome = chave.rsplit("/", 1)[-1] or "ficheiro"
    seguro = "".join(c for c in str(file_id) if c.isalnum() or c in "-_") or "ficheiro"
    return f"{PASTA_DOS_ANULADOS}/{caso_id}/{seguro}/{nome}"


# ════════════════════════════════════════════════════════════════════
#  S3: mover sem perder (copiar → verificar → [reapontar] → retirar a origem)
# ════════════════════════════════════════════════════════════════════
async def _copiar_para_os_anulados(chave: str, destino: str) -> str:
    """Copia e verifica. Devolve ``"copiado"`` | ``"ausente"`` (a origem já não existe).

    Levanta 503 numa falha do S3 — e nesse caso NADA foi gravado.
    """
    from services.partner_lead_files import _copiar_e_verificar, _escolher_destino, _head

    if not dentro_da_pasta(destino, RAIZ.rstrip("/")):  # cinto e suspensórios
        raise HTTPException(status_code=500, detail=ERRO_ARMAZENAMENTO)
    estado, meta = await _head(chave)
    if estado == "ausente":
        return "ausente"
    if estado != "ok":
        raise HTTPException(status_code=503, detail=ERRO_ARMAZENAMENTO)
    escolha, final, ja_la_esta = await _escolher_destino(meta or {}, destino)
    if escolha != "ok" or not final:
        raise HTTPException(status_code=503, detail=ERRO_ARMAZENAMENTO)
    if not ja_la_esta and not await _copiar_e_verificar(chave, final, meta or {}):
        raise HTTPException(status_code=503, detail=ERRO_ARMAZENAMENTO)
    return final


async def _retirar_a_origem(chave: str) -> None:
    """Só depois de a base de dados já apontar para a cópia. Nunca levanta."""
    try:
        if not await asyncio.to_thread(s3_service.delete_file, chave):
            logger.warning("[PARCEIRO-ANULAR] %s copiado e reapontado, mas a origem ficou (repetir).", chave)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[PARCEIRO-ANULAR] Falha a retirar a origem %s: %s", chave, exc)


# ════════════════════════════════════════════════════════════════════
#  A OPERAÇÃO
# ════════════════════════════════════════════════════════════════════
async def run_partner_cancel_upload(partner: dict, case_id: str, file_id: str) -> dict:
    caso = await resolver_caso(partner, case_id)

    # 2. Entre os que ele vê (404 igual a inexistente: não é um directório de ids).
    ficheiro = next((f for f in await ficheiros_internos(partner, caso) if f["id"] == file_id), None)
    if not ficheiro:
        raise HTTPException(status_code=404, detail=ERRO_FICHEIRO_NAO_ENCONTRADO)

    # 3. Foi ele que o enviou.
    if str(ficheiro.get("uploaded_by") or "") != autoria_do_parceiro(partner["id"]):
        raise HTTPException(status_code=403, detail=ERRO_NAO_FOI_O_PARCEIRO)

    # 4. Posse da chave ANTES de tocar no objecto.
    chave = ficheiro["s3_path"]
    assert_portal_file_key_e_do_cliente(chave, process=caso.process, client=caso.client)

    # 5. Ainda dá para anular?
    if caso.esta_expirado or caso.esta_associada:
        raise HTTPException(status_code=409, detail=ERRO_CASO_FECHADO)
    if e_comprovativo_de_pagamento(ficheiro.get("category") or "") and not caso.e_rascunho:
        raise HTTPException(status_code=409, detail=ERRO_COMPROVATIVO_JA_SEGUIU)
    meta = await db.document_metadata.find_one({"s3_path": chave}, {"_id": 0})
    if ja_foi_tratado(meta):
        raise HTTPException(status_code=409, detail=ERRO_JA_TRATADO)

    documento = await db.documents.find_one(
        {"id": ficheiro["documento_id"], "is_deleted": {"$ne": True}}, {"_id": 0}
    )
    if not documento:
        raise HTTPException(status_code=404, detail=ERRO_FICHEIRO_NAO_ENCONTRADO)

    agora = datetime.now(timezone.utc).isoformat()
    rasto = {
        "por": autoria_do_parceiro(partner["id"]),
        "em": agora,
        "s3_path_original": chave,
        "process_id": caso.id if caso.e_processo else None,
        "case_id": caso.id,
    }

    # S3 primeiro (copiar e verificar): se falhar, nada foi gravado.
    if s3_service.is_configured():
        resultado = await _copiar_para_os_anulados(chave, chave_na_pasta_dos_anulados(caso.id, file_id, chave))
    else:
        resultado = "ausente"
    nova_chave = chave if resultado == "ausente" else resultado
    rasto["s3_path"] = nova_chave

    # Base de dados: o registo do envio.
    reaberto = False
    if ficheiro.get("e_anexo"):
        reaberto = await _anular_num_pedido(documento, ficheiro, nova_chave, rasto)
    else:
        await db.documents.update_one(
            {"id": documento["id"]},
            {"$set": {
                "is_deleted": True,
                "status": "eliminado",
                "s3_path": nova_chave,
                # O comprovativo anulado não pode libertar a lead (a marca é do ficheiro).
                "comprovativo_de_pagamento": False,
                "anulado": rasto,
                "updated_at": agora,
            }},
        )

    # Metadados: desliga-se do processo e sai da fila do Index.
    if meta:
        await db.document_metadata.update_one(
            {"s3_path": chave},
            {"$set": {
                "s3_path": nova_chave,
                "process_id": None,
                "in_index_queue": False,
                "is_deleted": True,
                "anulado": rasto,
            }},
        )

    if nova_chave != chave:
        await _retirar_a_origem(chave)

    await _depois_de_anular(caso, partner, ficheiro.get("filename") or "")
    return {
        "success": True,
        "id": file_id,
        "filename": ficheiro.get("filename"),
        "request_id": ficheiro.get("request_id"),
        # O ecrã diz ao parceiro que o pedido voltou a pendente.
        "pedido_reaberto": reaberto,
    }


async def _anular_num_pedido(documento: dict, ficheiro: dict, nova_chave: str, rasto: dict) -> bool:
    """Retira o ficheiro do pedido (para `attached_files_anulados`). Devolve se o pedido reabriu."""
    anexos = list(documento.get("attached_files") or [])
    chave = ficheiro["s3_path"]
    entrada = next(
        (a for a in anexos if isinstance(a, dict) and a.get("s3_path") == chave
         and (a.get("file_id") or f"{documento.get('id')}:{chave}") == ficheiro["id"]),
        None,
    )
    if entrada is None:
        raise HTTPException(status_code=409, detail=ERRO_CONCORRENCIA)

    estado = rebuild_after_removal(documento, removidos=[chave]) or {}
    # `rebuild_after_removal` retira TODAS as entradas com esta chave; aqui só sai esta.
    estado["attached_files"] = [a for a in anexos if a is not entrada]
    estado["uploaded_count"] = len(estado["attached_files"])
    anulados = list(documento.get("attached_files_anulados") or [])
    anulados.append({**entrada, "s3_path": nova_chave, "anulado": rasto})
    estado["attached_files_anulados"] = anulados
    # O comprovativo de um pedido conta pelos ficheiros em `attached_files` (`partner_drafts`):
    # tirar a entrada daqui chega para o anulado não libertar a lead.

    # Concorrência optimista: só se escreve se os anexos são os que se leram.
    r = await db.documents.update_one(
        {"id": documento["id"], "attached_files": anexos},
        {"$set": estado},
    )
    if not getattr(r, "matched_count", 0):
        raise HTTPException(status_code=409, detail=ERRO_CONCORRENCIA)
    return estado.get("status") == "REQUESTED" and str(documento.get("status") or "") in ("RECEIVED", "received")


async def _depois_de_anular(caso: Caso, partner: dict, filename: str) -> None:
    """Rasto e aviso à equipa. Nunca faz falhar a anulação (já está gravada)."""
    from services.background_tasks import spawn_background_task

    if not caso.e_processo:
        try:
            from services.partner_drafts import registar_actividade

            await registar_actividade(caso.id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[PARCEIRO-ANULAR] Falha a registar actividade em %s: %s", caso.id, exc)
        return
    try:
        from services.history import log_history

        await log_history(
            caso.id,
            user={"id": None, "name": f"{partner.get('name') or 'Parceiro'} (Parceiro)", "role": "partner_portal"},
            action="DOCUMENT_CANCELLED_BY_PARTNER",
            field="documento",
            old_value=filename,
            new_value=None,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[PARCEIRO-ANULAR] Falha a registar o histórico: %s", exc)
    spawn_background_task(_avisar_a_equipa(caso, partner, filename), name=f"partner-cancel-notify:{caso.id}")
    try:
        from services.redis_cache import invalidate_stats_cache

        await invalidate_stats_cache()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[PARCEIRO-ANULAR] Falha a invalidar a cache de estatísticas: %s", exc)


async def _avisar_a_equipa(caso: Caso, partner: dict, filename: str) -> None:
    try:
        from services.notification_service import send_notification_with_preference_check
        from services.portal_assigned_users import get_all_assigned_user_ids

        atribuicoes = await db.processes.find_one(
            {"id": caso.id},
            {"_id": 0, "assigned_consultor_id": 1, "assigned_consultor_ids": 1, "consultor_id": 1,
             "consultant_id": 1, "assigned_mediador_id": 1, "assigned_mediador_ids": 1, "mediador_id": 1,
             "assigned_indexacao_id": 1},
        ) or {}
        referencia = (caso.process or {}).get("process_number") or caso.id[:8]
        cliente = (caso.process or {}).get("client_name") or "Cliente"
        for uid in get_all_assigned_user_ids(atribuicoes):
            utilizador = await db.users.find_one({"id": uid}, {"_id": 0, "email": 1})
            if utilizador and utilizador.get("email"):
                await send_notification_with_preference_check(
                    utilizador["email"],
                    "Documento anulado pelo parceiro",
                    f"O parceiro {partner.get('name') or ''} anulou o envio de '{filename}' "
                    f"no processo {referencia} ({cliente}).",
                    notification_type="document_upload",
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[PARCEIRO-ANULAR] Falha a avisar a equipa em %s: %s", caso.id, exc)


__all__ = [
    "PASTA_DOS_ANULADOS",
    "chave_na_pasta_dos_anulados",
    "ja_foi_tratado",
    "run_partner_cancel_upload",
]
