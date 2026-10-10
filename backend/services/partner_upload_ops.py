"""
====================================================================
PORTAL DO PARCEIRO — FICHEIROS: enviar, confirmar, descarregar (V1)
====================================================================
O parceiro envia documentos do cliente que gere. O ficheiro vai do
browser para o S3 por URL pré-assinado (o backend não o vê passar), e a
partir daí é tratado COM AS MESMAS REGRAS DO CRM (Bloco 2):

  * **Desvio inteligente** (`document_intake.planear_entrada`): processo
    por indexar → pasta `Index` + fila da IA; processo indexado (ou Via
    Verde) → a pasta pedida, sem IA. Uma lead (ainda sem processo) segue o
    caminho do onboarding do Portal: `Index` do cliente, sem fila — a fila
    só existe quando há processo a que a ligar.
  * **Quarentena de magic bytes** (`exigir_conteudo_valido`): tamanho e tipo
    REAIS lidos do objecto, nunca os que o browser declarou.
  * **Posse da chave ANTES de tocar no objecto** (Incidente P0): a chave
    vem do corpo do pedido e não é de confiança.
  * **Pedidos de documentos**: se o envio responde a um pedido, satisfaz-se
    pela contagem (`apply_portal_request_upload`), como no Portal do
    Cliente. É assim que parceiro e consultor falam — não há chat.

O QUE É DIFERENTE DO PORTAL DO CLIENTE
  * a autoria fica gravada como `partner:<id>` (e não `portal_client`):
    é o que faz o parceiro ver o que enviou e não ver o que a equipa juntou
    à mesma pasta (`ficheiro_e_visivel`);
  * a DESCARGA não recebe uma chave: recebe um `file_id`, e o servidor
    resolve-o dentro dos ficheiros visíveis daquele caso. Não há chave S3 a
    adulterar. A posse é verificada à mesma, também na leitura — um
    registo antigo com um `s3_path` envenenado deixa de ser servido sem
    ser preciso limpar a colecção;
  * o URL de descarga vale 15 minutos (o do cliente vale 1 hora).
====================================================================
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from database import db
from services.document_intake import (
    descreve_destino,
    descricao_para_o_utilizador,
    planear_entrada,
    registar_na_fila_da_ia,
)
from services.document_portal_counts import apply_portal_request_upload
from services.document_portal_request import clientes_do_processo
from services.partner_portal_read import (
    Caso,
    _consulta_de_pedidos,
    ficheiros_internos,
    resolver_caso,
)
from services.partner_visibility import ORIGEM_DO_PARCEIRO, autoria_do_parceiro
from services.portal_upload_ops import (
    assert_portal_file_key_e_do_cliente,
    run_generate_portal_upload_url,
)
from services.s3_content_quarantine import exigir_conteudo_valido
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)

VALIDADE_DO_URL_DE_DESCARGA_SEGUNDOS = 900
ERRO_PEDIDO_NAO_ENCONTRADO = "Pedido não encontrado."
ERRO_FICHEIRO_NAO_ENCONTRADO = "Ficheiro não encontrado."


class PartnerUploadUrlIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    filename: str = Field(..., min_length=1, max_length=255)
    content_type: Optional[str] = Field(None, max_length=100)
    #: A pasta que o parceiro PEDE; quem decide é o desvio inteligente.
    category: Optional[str] = Field(None, max_length=60)
    #: O pedido de documentos a que este ficheiro responde, se responder.
    request_id: Optional[str] = Field(None, max_length=80)


class PartnerConfirmUploadIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    file_key: str = Field(..., min_length=1, max_length=1024)
    original_filename: str = Field(..., min_length=1, max_length=255)
    category: Optional[str] = Field(None, max_length=60)
    request_id: Optional[str] = Field(None, max_length=80)


# ════════════════════════════════════════════════════════════════════
#  PEDIDOS
# ════════════════════════════════════════════════════════════════════
async def _pedido_do_caso(caso: Caso, request_id: str) -> dict:
    """O pedido, se for DESTE caso. 404 igual ao de inexistente."""
    consulta = {"$and": [{"id": request_id}, _consulta_de_pedidos(caso)]}
    pedido = await db.documents.find_one(consulta, {"_id": 0, "id": 1, "process_id": 1, "client_id": 1})
    if not pedido:
        raise HTTPException(status_code=404, detail=ERRO_PEDIDO_NAO_ENCONTRADO)
    return pedido


def _dados_para_o_portal(caso: Caso) -> dict:
    """A forma que as funções partilhadas do Portal esperam."""
    return {"process": caso.process, "client": caso.client, "client_id": caso.client_id}


# ════════════════════════════════════════════════════════════════════
#  1. URL DE ENVIO
# ════════════════════════════════════════════════════════════════════
async def run_partner_upload_url(partner: dict, case_id: str, data: PartnerUploadUrlIn) -> dict:
    caso = await resolver_caso(partner, case_id)
    if data.request_id:
        await _pedido_do_caso(caso, data.request_id)

    plano = planear_entrada(caso.process, data.category)
    resposta = await run_generate_portal_upload_url(
        {
            "filename": data.filename,
            "content_type": data.content_type or "application/octet-stream",
            "category": plano.categoria,
        },
        _dados_para_o_portal(caso),
        categoria_forcada=plano.categoria,
    )
    return {**resposta, "destino": descricao_para_o_utilizador(plano)}


# ════════════════════════════════════════════════════════════════════
#  2. CONFIRMAR
# ════════════════════════════════════════════════════════════════════
async def _guardar_ficheiro(
    caso: Caso,
    partner: dict,
    *,
    file_key: str,
    filename: str,
    categoria: str,
    tamanho: Optional[int],
    tipo: str,
    request_id: Optional[str],
    agora: str,
) -> str:
    """Grava o registo do ficheiro. Devolve o id do ficheiro."""
    autoria = autoria_do_parceiro(partner["id"])
    file_id = str(uuid.uuid4())
    client_id = caso.client_id
    process_id = caso.id if caso.e_processo else None

    if request_id:
        entrada = {
            "file_id": file_id,
            "filename": filename,
            "original_filename": filename,
            "s3_path": file_key,
            "file_size": tamanho,
            "content_type": tipo,
            "uploaded_at": agora,
            "uploaded_by": autoria,
        }
        campos = {
            "filename": filename,
            "original_filename": filename,
            "file_size": tamanho,
            "content_type": tipo,
            "s3_path": file_key,
            "storage_category": categoria,
            "uploaded_at": agora,
            "uploaded_by": autoria,
            "reviewed_by": autoria,
            "reviewed_at": agora,
        }
        if client_id:
            campos["client_id"] = client_id
        if process_id:
            campos["process_id"] = process_id

        consultas = [{"id": request_id, "process_id": process_id}] if process_id else [
            {"id": request_id, "client_id": client_id}
        ]
        if process_id and client_id:
            # Pedido do registo público ancorado só ao cliente: re-ancora-se
            # ao processo (e nunca "rouba" um pedido de outro processo).
            consultas.append({
                "id": request_id,
                "client_id": {"$in": clientes_do_processo(caso.process)},
                "$or": [{"process_id": None}, {"process_id": ""}, {"process_id": {"$exists": False}}],
            })
        for consulta in consultas:
            progresso = await apply_portal_request_upload(
                consulta, set_fields=campos, file_entry=entrada, now=agora
            )
            if progresso.get("matched"):
                return file_id
        # O pedido existia (verificado antes) mas deixou de casar entre a
        # verificação e a escrita — não se cria um envio solto em silêncio.
        raise HTTPException(status_code=409, detail="O pedido foi alterado. Tente novamente.")

    await db.documents.insert_one({
        "id": file_id,
        "process_id": process_id,
        "client_id": client_id,
        "filename": filename,
        "original_filename": filename,
        "category": categoria,
        "file_size": tamanho,
        "content_type": tipo,
        "s3_path": file_key,
        "status": "RECEIVED",
        "uploaded_at": agora,
        "uploaded_by": autoria,
        "source": ORIGEM_DO_PARCEIRO,
        "reviewed_by": autoria,
        "reviewed_at": agora,
    })
    return file_id


async def run_partner_confirm_upload(partner: dict, case_id: str, data: PartnerConfirmUploadIn) -> dict:
    caso = await resolver_caso(partner, case_id)

    # 1. POSSE ANTES DE TUDO (Incidente P0). Nem se sonda o objecto: um 403
    #    vs 400 sobre uma chave alheia seria um oráculo do bucket.
    assert_portal_file_key_e_do_cliente(data.file_key, process=caso.process, client=caso.client)

    # 2. O pedido (se houver) tem de ser deste caso — antes de gravar nada,
    #    para um pedido inválido não deixar um objecto órfão no bucket.
    if data.request_id:
        await _pedido_do_caso(caso, data.request_id)

    # 3. QUARENTENA: tamanho e tipo REAIS; reprovar apaga, falha de leitura
    #    é 503 e não apaga.
    veredicto = await exigir_conteudo_valido(data.file_key, filename=data.original_filename)
    tamanho = veredicto.tamanho
    tipo = veredicto.tipo_detectado or "application/octet-stream"

    # 4. DESVIO INTELIGENTE — as mesmas regras do CRM.
    plano = planear_entrada(caso.process, data.category)
    agora = datetime.now(timezone.utc).isoformat()

    file_id = await _guardar_ficheiro(
        caso, partner,
        file_key=data.file_key, filename=data.original_filename,
        categoria=plano.categoria,
        tamanho=tamanho, tipo=tipo, request_id=data.request_id, agora=agora,
    )

    # 5. Efeitos que NUNCA fazem falhar o envio (o ficheiro já está gravado).
    await _depois_de_guardar(caso, partner, plano, file_key=data.file_key, filename=data.original_filename)

    return {
        "success": True,
        "id": file_id,
        "filename": data.original_filename,
        "request_id": data.request_id,
        "destino": descricao_para_o_utilizador(plano),
    }


async def _depois_de_guardar(caso: Caso, partner: dict, plano, *, file_key: str, filename: str) -> None:
    from services.background_tasks import spawn_background_task

    nome_do_cliente = (caso.process or {}).get("client_name") or (caso.client or {}).get("nome") or "Cliente"

    # Fila da IA (só com processo): o ficheiro entra na estação de Indexação
    # e a categorização corre uma vez, em segundo plano.
    if plano.passa_pela_ia and caso.e_processo:
        try:
            await registar_na_fila_da_ia(
                process_id=caso.id, client_name=nome_do_cliente, s3_path=file_key,
                filename=file_key.split("/")[-1], origem="portal_parceiro",
            )
            conteudo = await asyncio.to_thread(s3_service.get_file_content, file_key)
            if conteudo:
                from services.document_auto_categorize import auto_categorize_document_background

                spawn_background_task(
                    auto_categorize_document_background(
                        process_id=caso.id, client_name=nome_do_cliente, s3_path=file_key,
                        filename=file_key.split("/")[-1], file_content=conteudo,
                    ),
                    name=f"partner-categorize:{caso.id}",
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[PARCEIRO] Falha a pôr %s na fila da IA: %s", file_key, exc)

    # Histórico do processo (honra o interruptor de rasto) e aviso à equipa.
    if caso.e_processo:
        try:
            from services.history import log_history

            await log_history(
                caso.id,
                user={"id": None, "name": f"{partner.get('name') or 'Parceiro'} (Parceiro)", "role": "partner_portal"},
                action="DOCUMENT_UPLOADED_BY_PARTNER",
                field="documento",
                old_value=None,
                new_value=f"{filename} [{descreve_destino(plano)}]",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[PARCEIRO] Falha a registar o histórico do envio: %s", exc)
        spawn_background_task(_avisar_a_equipa(caso, partner, filename), name=f"partner-upload-notify:{caso.id}")

    # A checklist pode ter ficado completa: o processo nasce (e herda o parceiro).
    if caso.client_id:
        try:
            from services.portal_onboarding_advance import _trigger_onboarding_check

            spawn_background_task(_trigger_onboarding_check(caso.client_id), name=f"onboarding-check:{caso.client_id}")
        except Exception as exc:  # noqa: BLE001
            logger.warning("[PARCEIRO] Falha a agendar a verificação de onboarding: %s", exc)
    if caso.e_processo:
        try:
            from services.portal_documents_notify import check_and_notify_documents_complete

            spawn_background_task(
                check_and_notify_documents_complete(caso.id, (caso.process or {}).get("company_id")),
                name=f"docs-complete-notify:{caso.id}",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[PARCEIRO] Falha a agendar o gatilho de documentação completa: %s", exc)

    try:
        from services.redis_cache import invalidate_stats_cache

        await invalidate_stats_cache()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[PARCEIRO] Falha a invalidar a cache de estatísticas: %s", exc)


async def _avisar_a_equipa(caso: Caso, partner: dict, filename: str) -> None:
    """Avisa quem está atribuído ao processo. O texto diz QUEM enviou: um
    aviso que dissesse «o cliente» mentiria sobre a origem do ficheiro."""
    try:
        from services.notification_service import send_notification_with_preference_check
        from services.portal_assigned_users import get_all_assigned_user_ids

        atribuicoes = await db.processes.find_one(
            {"id": caso.id},
            {"_id": 0, "assigned_consultor_id": 1, "assigned_consultor_ids": 1, "consultor_id": 1,
             "consultant_id": 1, "assigned_mediador_id": 1, "assigned_mediador_ids": 1, "mediador_id": 1,
             "assigned_indexacao_id": 1},
        ) or {}
        ids = get_all_assigned_user_ids(atribuicoes)
        referencia = (caso.process or {}).get("process_number") or caso.id[:8]
        cliente = (caso.process or {}).get("client_name") or "Cliente"
        for uid in ids:
            utilizador = await db.users.find_one({"id": uid}, {"_id": 0, "email": 1})
            if utilizador and utilizador.get("email"):
                await send_notification_with_preference_check(
                    utilizador["email"],
                    "Novo Documento do Parceiro",
                    f"O parceiro {partner.get('name') or ''} enviou '{filename}' no processo {referencia} ({cliente}).",
                    notification_type="document_upload",
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[PARCEIRO] Falha a avisar a equipa do envio em %s: %s", caso.id, exc)


# ════════════════════════════════════════════════════════════════════
#  3. DESCARREGAR
# ════════════════════════════════════════════════════════════════════
async def run_partner_download_url(partner: dict, case_id: str, file_id: str) -> dict:
    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="Serviço de armazenamento indisponível.")

    caso = await resolver_caso(partner, case_id)
    ficheiro = next((f for f in await ficheiros_internos(partner, caso) if f["id"] == file_id), None)
    if not ficheiro:
        raise HTTPException(status_code=404, detail=ERRO_FICHEIRO_NAO_ENCONTRADO)

    # A posse também na LEITURA: neutraliza um registo com um `s3_path`
    # envenenado sem ser preciso limpar a colecção.
    assert_portal_file_key_e_do_cliente(ficheiro["s3_path"], process=caso.process, client=caso.client)

    if not await asyncio.to_thread(s3_service.file_exists, ficheiro["s3_path"]):
        raise HTTPException(status_code=404, detail=ERRO_FICHEIRO_NAO_ENCONTRADO)
    url = s3_service.get_presigned_url(ficheiro["s3_path"], expiration=VALIDADE_DO_URL_DE_DESCARGA_SEGUNDOS)
    if not url:
        raise HTTPException(status_code=500, detail="Erro ao gerar o link de descarga.")
    return {
        "success": True,
        "url": url,
        "filename": ficheiro.get("filename"),
        "expires_in": VALIDADE_DO_URL_DE_DESCARGA_SEGUNDOS,
    }


__all__ = [
    "PartnerConfirmUploadIn",
    "PartnerUploadUrlIn",
    "VALIDADE_DO_URL_DE_DESCARGA_SEGUNDOS",
    "run_partner_confirm_upload",
    "run_partner_download_url",
    "run_partner_upload_url",
]
