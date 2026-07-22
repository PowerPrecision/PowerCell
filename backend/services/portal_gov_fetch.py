"""Scrapers Finanças / Segurança Social no Portal + MFA/jobs.

Extraído de `routes/portal.py`.
"""
from __future__ import annotations

import asyncio
import gc as _gc
import os
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from database import db
from services.portal_assigned_users import get_all_assigned_user_ids as _get_all_assigned_user_ids
from services.notification_service import send_notification_with_preference_check
from services.s3_storage import s3_service
from services.websocket_manager import manager, WSEventType, create_ws_message

logger = logging.getLogger(__name__)


async def _run_financas_background(nif: str, password: str, process_id: str, client_name: str, client_email: str, process: dict, scraper_job_id: str):
    """
    Background task para o scraper das Finanças.

    Executa o scraper pesado em background, atualiza o job na BD,
    envia emails e notifica a equipa quando termina.
    """
    # ── 1. Enviar email de início de processo ──
    try:
        await _send_portal_fetch_email(
            client_email, client_name, "financas", "started"
        )
    except Exception as e:
        logger.warning(f"[PORTAL-BG] Erro ao enviar email de início (Finanças): {e}")

    # ── 2. Invocar scraper ──
    try:
        result = await _run_financas_scraper(nif, password, process_id)

        if result.get("success"):
            docs_count = result.get("documents_count", 0)
            logger.info(
                f"[PORTAL-BG] Finanças: {docs_count} documentos obtidos para processo {process_id}"
            )

            # Atualizar job na BD
            await db.portal_scraper_jobs.update_one(
                {"id": scraper_job_id},
                {"$set": {
                    "status": "success",
                    "documents_count": docs_count,
                    "message": f"{docs_count} documento{'s' if docs_count != 1 else ''} obtido{'s' if docs_count != 1 else ''} do Portal das Finanças.",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }}
            )

            # Email de sucesso com documentos anexados
            try:
                docs_to_attach = result.get("documents", [])
                await _send_portal_fetch_email(
                    client_email, client_name, "financas", "success",
                    docs_count=docs_count,
                    attachments=docs_to_attach if docs_to_attach else None,
                )
            except Exception as e:
                logger.warning(f"[PORTAL-BG] Erro ao enviar email de sucesso (Finanças): {e}")

            # Notificar equipa via WebSocket
            await _notify_assigned_team_fetch(process, "Portal das Finanças", docs_count)
            try:
                await manager.broadcast_to_room(
                    f"process_{process_id}",
                    create_ws_message(WSEventType.DOCUMENT_UPLOADED, {
                        "process_id": process_id,
                        "source": "auto_financas",
                        "documents_count": docs_count,
                    })
                )
            except Exception as ws_err:
                logger.warning(f"[PORTAL-BG] Erro ao notificar via WebSocket: {ws_err}")

            # Libertar memória: limpar screenshot e documentos do result
            result.pop("screenshot_b64", None)
            result.pop("documents", None)
            _gc.collect()

        else:
            error_detail = result.get("error", "erro_desconhecido")
            logger.error(f"[PORTAL-BG] Erro do scraper Finanças: {error_detail}")

            # Determinar mensagem de erro
            if error_detail == "credenciais_invalidas":
                error_message = "As credenciais que introduziu estão incorretas. Verifique o seu NIF e password do Portal das Finanças."
                error_type = "credenciais_invalidas"
            elif error_detail == "mfa_requerido":
                error_message = "O portal requere verificação em 2 passos (Chave Móvel Digital). Introduza o código enviado para o seu telemóvel."
                error_type = "mfa_requerido"
            elif error_detail == "mfa_timeout":
                error_message = "O código de verificação não foi submetido a tempo. O scraper expirou após 2 minutos à espera do código SMS."
                error_type = "mfa_timeout"
            elif error_detail == "mfa_codigo_incorreto":
                error_message = "O código de verificação SMS introduzido parece estar incorreto. O login não foi concluído."
                error_type = "mfa_codigo_incorreto"
            elif error_detail == "mfa_error":
                error_message = "Erro ao processar o código de verificação. Tente novamente."
                error_type = "mfa_error"
            elif error_detail == "memory_error" or error_detail == "MemoryError":
                error_message = "O servidor não tem memória suficiente para executar a obtenção automática neste momento. Por favor, tente novamente mais tarde ou faça download manualmente."
                error_type = "scraper_unavailable"
            else:
                error_message = "O serviço de obtenção automática de documentos não está disponível de momento. Por favor, faça download manualmente do Portal das Finanças e envie os documentos através do botão de upload."
                error_type = "scraper_unavailable"

            # Atualizar job na BD
            await db.portal_scraper_jobs.update_one(
                {"id": scraper_job_id},
                {"$set": {
                    "status": "error",
                    "error_type": error_type,
                    "message": error_message,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }}
            )

            # Email de erro
            try:
                await _send_portal_fetch_email(
                    client_email, client_name, "financas", "error"
                )
            except Exception:
                pass

            # Notificar via WebSocket sobre o erro
            try:
                await manager.broadcast_to_room(
                    f"process_{process_id}",
                    create_ws_message(WSEventType.DOCUMENT_UPLOADED, {
                        "process_id": process_id,
                        "source": "auto_financas_error",
                        "error": error_type,
                    })
                )
            except Exception:
                pass

    except Exception as e:
        logger.error(f"[PORTAL-BG] Erro inesperado no scraper Finanças: {type(e).__name__}: {e}", exc_info=True)

        # Atualizar job na BD
        await db.portal_scraper_jobs.update_one(
            {"id": scraper_job_id},
            {"$set": {
                "status": "error",
                "error_type": "unexpected_error",
                "message": "Ocorreu um erro ao obter os documentos. Tente novamente mais tarde ou contacte o seu consultor.",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }}
        )

        try:
            await _send_portal_fetch_email(
                client_email, client_name, "financas", "error"
            )
        except Exception:
            pass


async def _run_seguranca_social_background(niss: str, password: str, process_id: str, client_name: str, client_email: str, process: dict, scraper_job_id: str):
    """
    Background task para o scraper da Segurança Social.

    Executa o scraper pesado em background, atualiza o job na BD,
    envia emails e notifica a equipa quando termina.
    """
    # ── 1. Enviar email de início de processo ──
    try:
        await _send_portal_fetch_email(
            client_email, client_name, "seguranca_social", "started"
        )
    except Exception as e:
        logger.warning(f"[PORTAL-BG] Erro ao enviar email de início (Seg. Social): {e}")

    # ── 2. Invocar scraper ──
    try:
        result = await _run_seguranca_social_scraper(niss, password, process_id)

        if result.get("success"):
            docs_count = result.get("documents_count", 0)
            logger.info(
                f"[PORTAL-BG] Seg. Social: {docs_count} documentos obtidos para processo {process_id}"
            )

            # Atualizar job na BD
            await db.portal_scraper_jobs.update_one(
                {"id": scraper_job_id},
                {"$set": {
                    "status": "success",
                    "documents_count": docs_count,
                    "message": f"{docs_count} documento{'s' if docs_count != 1 else ''} obtido{'s' if docs_count != 1 else ''} da Segurança Social.",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }}
            )

            # Email de sucesso com documentos anexados
            try:
                docs_to_attach = result.get("documents", [])
                await _send_portal_fetch_email(
                    client_email, client_name, "seguranca_social", "success",
                    docs_count=docs_count,
                    attachments=docs_to_attach if docs_to_attach else None,
                )
            except Exception as e:
                logger.warning(f"[PORTAL-BG] Erro ao enviar email de sucesso (Seg. Social): {e}")

            # Notificar equipa
            await _notify_assigned_team_fetch(process, "Segurança Social", docs_count)
            try:
                await manager.broadcast_to_room(
                    f"process_{process_id}",
                    create_ws_message(WSEventType.DOCUMENT_UPLOADED, {
                        "process_id": process_id,
                        "source": "auto_seguranca_social",
                        "documents_count": docs_count,
                    })
                )
            except Exception as ws_err:
                logger.warning(f"[PORTAL-BG] Erro ao notificar via WebSocket: {ws_err}")

            # Libertar memória: limpar screenshot e documentos do result
            result.pop("screenshot_b64", None)
            result.pop("documents", None)
            _gc.collect()

        else:
            error_detail = result.get("error", "erro_desconhecido")
            logger.error(f"[PORTAL-BG] Erro do scraper Seg. Social: {error_detail}")

            if error_detail == "credenciais_invalidas":
                error_message = "As credenciais que introduziu estão incorretas. Verifique o seu NISS e password da Segurança Social."
                error_type = "credenciais_invalidas"
            elif error_detail == "mfa_requerido":
                error_message = "O portal requere verificação em 2 passos (Chave Móvel Digital). Introduza o código enviado para o seu telemóvel."
                error_type = "mfa_requerido"
            elif error_detail == "mfa_timeout":
                error_message = "O código de verificação não foi submetido a tempo. O scraper expirou após 2 minutos à espera do código SMS."
                error_type = "mfa_timeout"
            elif error_detail == "mfa_codigo_incorreto":
                error_message = "O código de verificação SMS introduzido parece estar incorreto. O login não foi concluído."
                error_type = "mfa_codigo_incorreto"
            elif error_detail == "mfa_error" or error_detail == "mfa_no_input":
                error_message = "Erro ao processar o código de verificação. Tente novamente."
                error_type = "mfa_error"
            elif error_detail == "memory_error" or error_detail == "MemoryError":
                error_message = "O servidor não tem memória suficiente para executar a obtenção automática neste momento. Por favor, tente novamente mais tarde ou faça download manualmente."
                error_type = "scraper_unavailable"
            else:
                error_message = "O serviço de obtenção automática de documentos não está disponível de momento. Por favor, faça download manualmente da Segurança Social e envie os documentos através do botão de upload."
                error_type = "scraper_unavailable"

            await db.portal_scraper_jobs.update_one(
                {"id": scraper_job_id},
                {"$set": {
                    "status": "error",
                    "error_type": error_type,
                    "message": error_message,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }}
            )

            try:
                await _send_portal_fetch_email(
                    client_email, client_name, "seguranca_social", "error"
                )
            except Exception:
                pass

            try:
                await manager.broadcast_to_room(
                    f"process_{process_id}",
                    create_ws_message(WSEventType.DOCUMENT_UPLOADED, {
                        "process_id": process_id,
                        "source": "auto_seguranca_social_error",
                        "error": error_type,
                    })
                )
            except Exception:
                pass

    except Exception as e:
        logger.error(f"[PORTAL-BG] Erro inesperado no scraper Seg. Social: {type(e).__name__}: {e}", exc_info=True)

        await db.portal_scraper_jobs.update_one(
            {"id": scraper_job_id},
            {"$set": {
                "status": "error",
                "error_type": "unexpected_error",
                "message": "Ocorreu um erro ao obter os documentos. Tente novamente mais tarde ou contacte o seu consultor.",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }}
        )

        try:
            await _send_portal_fetch_email(
                client_email, client_name, "seguranca_social", "error"
            )
        except Exception:
            pass


async def _run_financas_scraper(nif: str, password: str, process_id: str):
    """
    Invoca o scraper do Portal das Finanças (gov_scraper.py).

    O scraper utiliza Playwright em modo headless para:
    1. Autenticar no Portal das Finanças via acesso.gov.pt
    2. Navegar até à secção de IRS
    3. Descarregar a Declaração de IRS e a Nota de Liquidação
    4. Retornar os PDFs em bytes

    Após obter os documentos, faz upload para o S3 e cria registos na BD.

    SEGURANÇA: As credenciais (NIF + password) são usadas APENAS em memória
    pelo scraper e eliminadas logo após a execução (del + gc.collect).
    NUNCA são persistidas na BD ou impressas no log.
    """
    from services.gov_scraper import fetch_financas_documents

    # Obter informações do processo para upload S3
    process = await db.processes.find_one({"id": process_id})
    client_name = process.get("client_name", "cliente") if process else "cliente"
    s3_folder = process.get("s3_folder") if process else None

    # ── Invocar o scraper real ──
    result = await fetch_financas_documents(nif, password, process_id=process_id)

    # Neste ponto, o scraper já limpou as credenciais da memória
    # (garantido pelo `finally` em fetch_financas_documents)

    if not result.success:
        error_map = {
            "credenciais_invalidas": "credenciais_invalidas",
            "mfa_requerido": "mfa_requerido",
            "mfa_timeout": "mfa_timeout",
            "mfa_codigo_incorreto": "mfa_codigo_incorreto",
            "mfa_no_input": "mfa_error",
            "mfa_error": "mfa_error",
            "timeout": "timeout_scraper",
            "sem_documentos": "sem_documentos",
            "selector_desatualizado": "selector_desatualizado",
        }
        response = {
            "success": False,
            "error": error_map.get(result.error, result.error or "erro_desconhecido"),
            "step_failed": result.step_failed,
        }
        # Incluir screenshot para debug (se disponível)
        if result.screenshot_b64:
            response["screenshot_available"] = True
            # Não enviar o base64 no response (pode ser grande) — guardar no log
            logger.info(f"[PORTAL] Screenshot disponível para debug ({len(result.screenshot_b64)} chars)")
        return response

    # ── Upload dos documentos para o S3 e registo na BD ──
    docs_registered = 0
    docs_for_attachment = []  # Documentos para anexar ao email de sucesso

    for doc in result.documents:
        try:
            # Upload para o S3
            import io
            file_obj = io.BytesIO(doc.content_bytes)
            s3_path = s3_service.upload_file(
                file_obj=file_obj,
                client_id=process_id,
                client_name=client_name,
                category=doc.category,
                filename=doc.filename,
                content_type=doc.content_type,
                s3_folder=s3_folder,
            )

            if not s3_path:
                logger.warning(f"[PORTAL] Falha no upload S3 para {doc.filename} — a criar registo sem S3 path")

            # Timestamp único por documento (evita que vários docs do mesmo
            # batch fiquem com a mesma data/hora exacta no CRM)
            doc_now = datetime.now(timezone.utc).isoformat()

            # Criar registo na BD
            doc_id = str(uuid.uuid4())
            doc_record = {
                "id": doc_id,
                "process_id": process_id,
                "filename": doc.filename,
                "original_filename": doc.filename,
                "category": doc.category,
                # Mantemos sempre o label legível ("Declaração de IRS",
                # "Nota de Liquidação IRS", etc.) para o utilizador identificar
                # o tipo específico dentro da categoria "Financeiros".
                "custom_label": doc.label,
                "status": "RECEIVED",
                "source": "auto_financas",
                "uploaded_at": doc_now,
                "uploaded_by": "system_financas_scraper",
                "content_type": doc.content_type,
                "file_size": len(doc.content_bytes),
                "s3_path": s3_path,
                "auto_fetched": True,
            }

            await db.documents.insert_one(doc_record)
            docs_registered += 1

            # Guardar dados do documento para anexar ao email de sucesso
            docs_for_attachment.append({
                "filename": doc.filename,
                "content_bytes": doc.content_bytes,
                "content_type": doc.content_type,
            })

            logger.info(
                f"[PORTAL] Documento Finanças registado: {doc.filename} "
                f"({len(doc.content_bytes)} bytes, S3: {'sim' if s3_path else 'não'}, "
                f"categoria: {doc.category}, label: {doc.label})"
            )

        except Exception as e:
            logger.error(f"[PORTAL] Erro ao registar documento {doc.filename}: {type(e).__name__}: {e}")

    # ── Marcar documentos pendentes como UPLOADED ──
    # Quando o scraper Finanças obtém docs com sucesso, marcar qualquer
    # documento REQUESTED/PENDING das categorias IRS/Financeiros como UPLOADED
    # para que o cliente veja o item como "entregue" na checklist do portal.
    if docs_registered > 0:
        try:
            financas_categories = ["IRS", "Financeiros", "irs", "financeiros"]
            update_result = await db.documents.update_many(
                {
                    "process_id": process_id,
                    "status": {"$in": ["REQUESTED", "PENDING", "requested", "pending"]},
                    "category": {"$in": financas_categories},
                },
                {
                    "$set": {
                        "status": "UPLOADED",
                        "uploaded_at": datetime.now(timezone.utc).isoformat(),
                        "uploaded_by": "system_financas_scraper",
                        "auto_fetched": True,
                        "source": "auto_financas",
                    }
                }
            )
            if update_result.modified_count > 0:
                logger.info(
                    f"[PORTAL] {update_result.modified_count} documento(s) pendente(s) "
                    f"IRS/Financeiros marcado(s) como UPLOADED para processo {process_id}"
                )
        except Exception as mark_err:
            logger.warning(
                f"[PORTAL] Erro ao marcar docs pendentes como UPLOADED: "
                f"{type(mark_err).__name__}: {mark_err}"
            )

    return {"success": True, "documents_count": docs_registered, "documents": docs_for_attachment}


async def _run_seguranca_social_scraper(niss: str, password: str, process_id: str):
    """
    Invoca o scraper da Segurança Social (gov_scraper.py).

    O scraper utiliza Playwright em modo headless para:
    1. Autenticar na Segurança Social Direta
    2. Navegar até à secção de documentos
    3. Descarregar a Situação Contributiva e o Extrato de Remunerações
    4. Retornar os PDFs em bytes

    SEGURANÇA: As credenciais (NISS + password) são usadas APENAS em memória
    pelo scraper e eliminadas logo após a execução (del + gc.collect).
    NUNCA são persistidas na BD ou impressas no log.
    """
    from services.gov_scraper import fetch_seg_social_documents

    # Obter informações do processo para upload S3
    process = await db.processes.find_one({"id": process_id})
    client_name = process.get("client_name", "cliente") if process else "cliente"
    s3_folder = process.get("s3_folder") if process else None

    # ── Invocar o scraper real ──
    result = await fetch_seg_social_documents(niss, password, process_id=process_id)

    # Neste ponto, o scraper já limpou as credenciais da memória

    if not result.success:
        error_map = {
            "credenciais_invalidas": "credenciais_invalidas",
            "mfa_requerido": "mfa_requerido",
            "mfa_timeout": "mfa_timeout",
            "mfa_codigo_incorreto": "mfa_codigo_incorreto",
            "mfa_no_input": "mfa_error",
            "mfa_error": "mfa_error",
            "timeout": "timeout_scraper",
            "sem_documentos": "sem_documentos",
            "selector_desatualizado": "selector_desatualizado",
        }
        response = {
            "success": False,
            "error": error_map.get(result.error, result.error or "erro_desconhecido"),
            "step_failed": result.step_failed,
        }
        if result.screenshot_b64:
            response["screenshot_available"] = True
            logger.info(f"[PORTAL] Screenshot disponível para debug ({len(result.screenshot_b64)} chars)")
        return response

    # ── Upload dos documentos para o S3 e registo na BD ──
    docs_registered = 0
    docs_for_attachment = []  # Documentos para anexar ao email de sucesso

    for doc in result.documents:
        try:
            # Upload para o S3
            import io
            file_obj = io.BytesIO(doc.content_bytes)
            s3_path = s3_service.upload_file(
                file_obj=file_obj,
                client_id=process_id,
                client_name=client_name,
                category=doc.category,
                filename=doc.filename,
                content_type=doc.content_type,
                s3_folder=s3_folder,
            )

            if not s3_path:
                logger.warning(f"[PORTAL] Falha no upload S3 para {doc.filename} — a criar registo sem S3 path")

            # Timestamp único por documento (evita que vários docs do mesmo
            # batch fiquem com a mesma data/hora exacta no CRM)
            doc_now = datetime.now(timezone.utc).isoformat()

            # Criar registo na BD
            doc_id = str(uuid.uuid4())
            doc_record = {
                "id": doc_id,
                "process_id": process_id,
                "filename": doc.filename,
                "original_filename": doc.filename,
                "category": doc.category,
                # Mantemos sempre o label legível ("Situação Contributiva",
                # "Extrato de Remunerações") para o utilizador identificar
                # o tipo específico dentro da categoria genérica.
                "custom_label": doc.label,
                "status": "RECEIVED",
                "source": "auto_seguranca_social",
                "uploaded_at": doc_now,
                "uploaded_by": "system_seguranca_social_scraper",
                "content_type": doc.content_type,
                "file_size": len(doc.content_bytes),
                "s3_path": s3_path,
                "auto_fetched": True,
            }

            await db.documents.insert_one(doc_record)
            docs_registered += 1

            # Guardar dados do documento para anexar ao email de sucesso
            docs_for_attachment.append({
                "filename": doc.filename,
                "content_bytes": doc.content_bytes,
                "content_type": doc.content_type,
            })

            logger.info(
                f"[PORTAL] Documento Seg. Social registado: {doc.filename} "
                f"({len(doc.content_bytes)} bytes, S3: {'sim' if s3_path else 'não'}, "
                f"categoria: {doc.category}, label: {doc.label})"
            )

        except Exception as e:
            logger.error(f"[PORTAL] Erro ao registar documento {doc.filename}: {type(e).__name__}: {e}")

    # ── Marcar documentos pendentes como UPLOADED ──
    # Quando o scraper Segurança Social obtém docs com sucesso, marcar qualquer
    # documento REQUESTED/PENDING das categorias Financeiros/Segurança Social
    # como UPLOADED para que o cliente veja o item como "entregue" na checklist.
    if docs_registered > 0:
        try:
            ss_categories = ["Financeiros", "financeiros", "Seguranca_Social", "Segurança_Social"]
            update_result = await db.documents.update_many(
                {
                    "process_id": process_id,
                    "status": {"$in": ["REQUESTED", "PENDING", "requested", "pending"]},
                    "category": {"$in": ss_categories},
                },
                {
                    "$set": {
                        "status": "UPLOADED",
                        "uploaded_at": datetime.now(timezone.utc).isoformat(),
                        "uploaded_by": "system_seguranca_social_scraper",
                        "auto_fetched": True,
                        "source": "auto_seguranca_social",
                    }
                }
            )
            if update_result.modified_count > 0:
                logger.info(
                    f"[PORTAL] {update_result.modified_count} documento(s) pendente(s) "
                    f"Seg. Social marcado(s) como UPLOADED para processo {process_id}"
                )
        except Exception as mark_err:
            logger.warning(
                f"[PORTAL] Erro ao marcar docs pendentes como UPLOADED: "
                f"{type(mark_err).__name__}: {mark_err}"
            )

    return {"success": True, "documents_count": docs_registered, "documents": docs_for_attachment}


async def _send_portal_fetch_email(to_email: str, client_name: str, source: str, status: str, docs_count: int = 0, attachments: list = None):
    """
    Envia email de estado ao cliente sobre a obtenção automática de documentos.

    Utiliza o serviço de email principal (send_email) em vez de SMTP directo,
    para suportar tanto Resend API como SMTP, e garantir que os emails são
    registados no histórico do processo.

    Args:
        to_email: Email do destinatário (cliente).
        client_name: Nome do cliente.
        source: Origem dos documentos ("financas" ou "seguranca_social").
        status: Estado do processo ("started", "error" ou "success").
        docs_count: Número de documentos obtidos (apenas para status="success").
        attachments: Lista de anexos a incluir no email (apenas para status="success").
            Cada anexo é um dict com:
            - filename (str): Nome do ficheiro.
            - content_bytes (bytes): Conteúdo binário do documento.
            - content_type (str): Tipo MIME (ex: "application/pdf").

    Status:
    - started:  "O nosso sistema automático começou a reunir os seus documentos..."
    - error:    "As credenciais que introduziu estão incorretas..."
    - success:  "Os documentos foram descarregados e anexados ao seu processo com sucesso..."
    """
    if not to_email:
        return

    source_label = {
        "financas": "Portal das Finanças",
        "seguranca_social": "Segurança Social",
    }.get(source, source)

    if status == "started":
        subject = f"Obtenção de Documentos — {source_label}"
        body_text = (
            f"Exmo(a). Sr(a). {client_name},\n\n"
            f"O nosso sistema automático começou a reunir os seus documentos "
            f"junto do {source_label}.\n\n"
            f"Iremos notificá-lo(a) assim que o processo esteja concluído.\n\n"
            f"Com os melhores cumprimentos,\nEquipa Power Precision"
        )
    elif status == "error":
        subject = f"Credenciais Incorretas — {source_label}"
        body_text = (
            f"Exmo(a). Sr(a). {client_name},\n\n"
            f"As credenciais que introduziu estão incorretas para o {source_label}.\n\n"
            f"Por favor, verifique os seus dados e tente novamente no portal, "
            f"ou contacte o seu consultor para assistência.\n\n"
            f"Com os melhores cumprimentos,\nEquipa Power Precision"
        )
    elif status == "success":
        subject = f"Documentos Obtidos com Sucesso — {source_label}"
        body_text = (
            f"Exmo(a). Sr(a). {client_name},\n\n"
            f"Os documentos foram descarregados e anexados ao seu processo com sucesso "
            f"junto do {source_label} ({docs_count} documento{'s' if docs_count != 1 else ''} obtido{'s' if docs_count != 1 else ''}).\n\n"
            f"Não é necessário qualquer ação adicional da sua parte.\n\n"
            f"Com os melhores cumprimentos,\nEquipa Power Precision"
        )
    else:
        return

    html_content = f"""
    <html><body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: #0f766e; color: white; padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
            <h2 style="margin: 0;">Power Precision</h2>
        </div>
        <div style="background: #f9f9f9; padding: 20px; border-radius: 0 0 8px 8px;">
            <p>{body_text.replace(chr(10), '<br>')}</p>
        </div>
        <p style="text-align: center; font-size: 11px; color: #999; margin-top: 15px;">
            Este email foi enviado automaticamente. Não responda diretamente.
        </p>
    </div>
    </body></html>
    """

    # ── Enviar via serviço de email principal (Resend API ou SMTP) ──
    # Incluir anexos apenas no email de sucesso (quando há documentos para enviar)
    try:
        from services.email_service import send_email
        await send_email(
            account_name="power",
            to_emails=[to_email],
            subject=subject,
            body=body_text,
            body_html=html_content,
            force_system=True,
            system_purpose="NOTIFICATIONS",
            attachments=attachments if status == "success" and attachments else None,
        )
        att_info = f" com {len(attachments)} anexo(s)" if attachments and status == "success" else ""
        logger.info(f"[PORTAL] Email de estado '{status}' enviado para {to_email} ({source_label}{att_info})")
    except Exception as e:
        # Fallback para SMTP directo se o serviço principal falhar
        logger.warning(f"[PORTAL] Serviço de email principal falhou, a tentar SMTP directo: {type(e).__name__}")
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            from email.mime.application import MIMEApplication

            smtp_server = os.environ.get('SMTP_SERVER')
            smtp_port = int(os.environ.get('SMTP_PORT', 465))
            smtp_email = os.environ.get('SMTP_EMAIL')
            smtp_password_env = os.environ.get('SMTP_PASSWORD')

            if not all([smtp_server, smtp_email, smtp_password_env]):
                logger.warning("[PORTAL] SMTP também não configurado — email de estado não enviado")
                return

            # Construir mensagem com suporte a anexos
            if attachments and status == "success":
                msg = MIMEMultipart("mixed")
                body_part = MIMEMultipart("alternative")
                body_part.attach(MIMEText(body_text, "plain", "utf-8"))
                body_part.attach(MIMEText(html_content, "html", "utf-8"))
                msg.attach(body_part)

                # Anexar documentos PDF
                for att in attachments:
                    att_bytes = att.get("content_bytes")
                    att_filename = att.get("filename", "documento.pdf")
                    if att_bytes:
                        pdf_part = MIMEApplication(att_bytes, _subtype="pdf")
                        pdf_part.add_header(
                            "Content-Disposition", "attachment",
                            filename=att_filename,
                        )
                        msg.attach(pdf_part)
                        logger.info(
                            f"[PORTAL] Anexo adicionado ao SMTP fallback: "
                            f"{att_filename} ({len(att_bytes)} bytes)"
                        )
            else:
                msg = MIMEMultipart('alternative')
                msg.attach(MIMEText(html_content, 'html'))

            msg['Subject'] = subject
            msg['From'] = smtp_email
            msg['To'] = to_email

            import ssl
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context, timeout=30) as server:
                server.login(smtp_email, smtp_password_env)
                server.sendmail(smtp_email, to_email, msg.as_string())

            att_info = f" com {len(attachments)} anexo(s)" if attachments and status == "success" else ""
            logger.info(f"[PORTAL] Email de estado '{status}' enviado via SMTP fallback para {to_email}{att_info}")
        except Exception as fallback_err:
            logger.warning(f"[PORTAL] SMTP fallback também falhou: {type(fallback_err).__name__}")


async def _notify_assigned_team_fetch(process: dict, source_name: str, docs_count: int):
    """Notifica a equipa atribuída sobre documentos obtidos automaticamente."""
    assigned_ids = _get_all_assigned_user_ids(process)
    if not assigned_ids:
        return

    client_name = process.get("client_name", "Cliente")
    process_number = process.get("process_number", "")
    process_ref = f"#{process_number}" if process_number else process.get("id", "")[:8]

    for uid in assigned_ids:
        try:
            user = await db.users.find_one({"id": uid}, {"name": 1, "email": 1})
            if user:
                await send_notification_with_preference_check(
                    user.get("email"),
                    f"Documentos Obtidos — {source_name}",
                    f"O sistema obteve {docs_count} documento{'s' if docs_count != 1 else ''} do {source_name} para o cliente {client_name} no processo {process_ref}.",
                    notification_type="document_auto_fetch"
                )
        except Exception as e:
            logger.warning(f"Erro ao notificar {uid} sobre fetch {source_name}: {e}")


async def run_check_scraper_status():
    """
    Verifica se o serviço de obtenção automática de documentos está disponível.

    Retorna o estado do Playwright e do browser Chromium, para diagnóstico.
    Endpoint público (não requer autenticação) para permitir verificação prévia.

    Em DEV (ENVIRONMENT != production): retorna mock sem importar Playwright.
    """
    # DEV MODE: Mock — não importar Playwright em DEV para poupar RAM
    if os.environ.get('ENVIRONMENT') != 'production':
        return {
            "available": False,
            "playwright_installed": False,
            "chromium_available": False,
            "dev_mode": True,
            "error": "MOCK DEV: Scraper de portais governamentais desativado em DEV para poupar RAM. Funciona apenas em ENVIRONMENT=production.",
        }

    try:
        from services.gov_scraper import check_playwright_available
        result = await check_playwright_available()
        return {
            "available": result.get("playwright_installed") and result.get("chromium_available"),
            "playwright_installed": result.get("playwright_installed", False),
            "chromium_available": result.get("chromium_available", False),
            "browsers_path": result.get("browsers_path"),
            "browsers_dir_exists": result.get("browsers_dir_exists"),
            "error": result.get("error"),
        }
    except Exception as e:
        return {
            "available": False,
            "playwright_installed": False,
            "chromium_available": False,
            "error": str(e),
        }


async def run_fetch_financas_documents(data: dict, background_tasks: BackgroundTasks, client_data: dict):
    """
    Obtém documentos do Portal das Finanças (IRS, Nota de Liquidação).

    SEGURANÇA: As credenciais (NIF + Password) NUNCA são guardadas na BD.
    São usadas apenas em memória para invocar o scraper e descartadas de imediato.

    Body:
    - nif: NIF do cliente (obrigatório, 9 dígitos)
    - password: Password do Portal das Finanças (obrigatório)

    Fluxo (ASSÍNCRONO com BackgroundTasks):
    1. Valida credenciais e responde IMEDIATAMENTE com HTTP 200 {status: "processing"}
    2. Em background: envia email de início → invoca scraper → anexa docs → notifica
    3. O cliente consulta o estado via polling ou WebSocket

    Isto resolve CORS/502 Bad Gateway causado pelo timeout do Render (30s)
    quando o scraper demora mais de 1 minuto a executar.

    DEV MODE: Se ENVIRONMENT != 'production', retorna mock de sucesso sem invocar Playwright.
    """
    # DEV MODE: Mock do scraper — SÓ PRODUÇÃO lança o browser
    # REGRA ABSOLUTA: Se ENVIRONMENT != 'production', o Chromium NÃO lança.
    if os.environ.get('ENVIRONMENT') != 'production':
        logger.info("[PORTAL] MOCK DEV: fetch-financas desativado em DEV para poupar RAM.")
        return {
            "success": True,
            "message": "MOCK DEV: Acesso ao Portal das Finanças desativado em DEV para poupar RAM. Funciona apenas em ENVIRONMENT=production.",
            "documents_count": 0,
            "dev_mode": True,
        }

    process = client_data["process"]
    process_id = process["id"]
    client_name = process.get("client_name", "Cliente")
    client_email = process.get("client_email", "")

    nif = data.get("nif", "").strip()
    password = data.get("password", "")

    # Validação básica
    if not nif or len(nif) != 9 or not nif.isdigit():
        raise HTTPException(status_code=400, detail="NIF inválido. Deve conter 9 dígitos.")
    if not password:
        raise HTTPException(status_code=400, detail="A password é obrigatória.")

    # ── Registar estado inicial do scraper na BD ──
    scraper_job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.portal_scraper_jobs.insert_one({
        "id": scraper_job_id,
        "process_id": process_id,
        "source": "financas",
        "status": "processing",
        "created_at": now,
        "updated_at": now,
    })

    # ── Passar apenas campos necessários do processo (evitar reter dados grandes em memória) ──
    process_minimal = {
        "id": process.get("id"),
        "client_name": process.get("client_name", ""),
        "process_number": process.get("process_number", ""),
        "assigned_consultor_ids": process.get("assigned_consultor_ids"),
        "assigned_consultor_id": process.get("assigned_consultor_id"),
        "assigned_mediador_ids": process.get("assigned_mediador_ids"),
        "assigned_mediador_id": process.get("assigned_mediador_id"),
        "assigned_indexacao_id": process.get("assigned_indexacao_id"),
        "assigned_parceiro_id": process.get("assigned_parceiro_id"),
    }

    # ── Agendar execução pesada em BackgroundTask ──
    background_tasks.add_task(
        _run_financas_background,
        nif=nif,
        password=password,
        process_id=process_id,
        client_name=client_name,
        client_email=client_email,
        process=process_minimal,
        scraper_job_id=scraper_job_id,
    )

    # ── Responder IMEDIATAMENTE com HTTP 200 ──
    logger.info(f"[PORTAL] Fetch Finanças agendado em background para processo {process_id}")
    return JSONResponse(content={
        "status": "processing",
        "message": "A obter documentos em background. Será notificado quando estiverem prontos.",
        "scraper_job_id": scraper_job_id,
        "process_id": process_id,
    })


async def run_fetch_seguranca_social_documents(data: dict, background_tasks: BackgroundTasks, client_data: dict):
    """
    Obtém documentos da Segurança Social.

    SEGURANÇA: As credenciais (NISS + Password) NUNCA são guardadas na BD.
    São usadas apenas em memória para invocar o scraper e descartadas de imediato.

    Body:
    - niss: NISS do cliente (obrigatório, 11 dígitos)
    - password: Password da Segurança Social (obrigatório)

    Fluxo (ASSÍNCRONO com BackgroundTasks):
    1. Valida credenciais e responde IMEDIATAMENTE com HTTP 200 {status: "processing"}
    2. Em background: envia email de início → invoca scraper → anexa docs → notifica
    3. O cliente consulta o estado via polling ou WebSocket

    Isto resolve CORS/502 Bad Gateway causado pelo timeout do Render (30s)
    quando o scraper demora mais de 1 minuto a executar.

    DEV MODE: Se ENVIRONMENT != 'production', retorna mock de sucesso sem invocar Playwright.
    """
    # DEV MODE: Mock do scraper — SÓ PRODUÇÃO lança o browser
    # REGRA ABSOLUTA: Se ENVIRONMENT != 'production', o Chromium NÃO lança.
    if os.environ.get('ENVIRONMENT') != 'production':
        logger.info("[PORTAL] MOCK DEV: fetch-seguranca-social desativado em DEV para poupar RAM.")
        return {
            "success": True,
            "message": "MOCK DEV: Acesso à Segurança Social desativado em DEV para poupar RAM. Funciona apenas em ENVIRONMENT=production.",
            "documents_count": 0,
            "dev_mode": True,
        }

    process = client_data["process"]
    process_id = process["id"]
    client_name = process.get("client_name", "Cliente")
    client_email = process.get("client_email", "")

    niss = data.get("niss", "").strip()
    password = data.get("password", "")

    # Validação básica
    if not niss or len(niss) != 11 or not niss.isdigit():
        raise HTTPException(status_code=400, detail="NISS inválido. Deve conter 11 dígitos.")
    if not password:
        raise HTTPException(status_code=400, detail="A password é obrigatória.")

    # ── Registar estado inicial do scraper na BD ──
    scraper_job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    await db.portal_scraper_jobs.insert_one({
        "id": scraper_job_id,
        "process_id": process_id,
        "source": "seguranca_social",
        "status": "processing",
        "created_at": now,
        "updated_at": now,
    })

    # ── Passar apenas campos necessários do processo (evitar reter dados grandes em memória) ──
    process_minimal = {
        "id": process.get("id"),
        "client_name": process.get("client_name", ""),
        "process_number": process.get("process_number", ""),
        "assigned_consultor_ids": process.get("assigned_consultor_ids"),
        "assigned_consultor_id": process.get("assigned_consultor_id"),
        "assigned_mediador_ids": process.get("assigned_mediador_ids"),
        "assigned_mediador_id": process.get("assigned_mediador_id"),
        "assigned_indexacao_id": process.get("assigned_indexacao_id"),
        "assigned_parceiro_id": process.get("assigned_parceiro_id"),
    }

    # ── Agendar execução pesada em BackgroundTask ──
    background_tasks.add_task(
        _run_seguranca_social_background,
        niss=niss,
        password=password,
        process_id=process_id,
        client_name=client_name,
        client_email=client_email,
        process=process_minimal,
        scraper_job_id=scraper_job_id,
    )

    # ── Responder IMEDIATAMENTE com HTTP 200 ──
    logger.info(f"[PORTAL] Fetch Seg. Social agendado em background para processo {process_id}")
    return JSONResponse(content={
        "status": "processing",
        "message": "A obter documentos em background. Será notificado quando estiverem prontos.",
        "scraper_job_id": scraper_job_id,
        "process_id": process_id,
    })


async def run_submit_mfa_code(data: dict, client_data: dict):
    """
    Submete o código MFA recebido por SMS para retomar o scraper.

    Quando a Segurança Social pede verificação em 2 passos (código SMS),
    o scraper pausa e coloca o job em estado "awaiting_mfa". O frontend
    mostra um input ao cliente, e ao submeter, este endpoint guarda o
    código no Redis (TTL 300s) para o scraper o consumir.

    Body:
    - process_id: ID do processo (obrigatório)
    - mfa_code: Código de verificação SMS (obrigatório, 4-8 dígitos)

    Fluxo:
    1. Scraper detecta MFA → job status = "awaiting_mfa"
    2. Frontend faz polling → vê "awaiting_mfa" → mostra input
    3. Cliente submete código → POST /submit-mfa
    4. Código guardado no Redis (mfa_code:{process_id}, TTL 300s)
    5. Scraper lê código do Redis → preenche no browser → continua
    """
    process = client_data["process"]
    process_id = process["id"]

    # Validar que o process_id no body corresponde ao do token JWT
    body_process_id = data.get("process_id", "").strip()
    if body_process_id and body_process_id != process_id:
        raise HTTPException(status_code=403, detail="process_id não corresponde ao token.")

    mfa_code = data.get("mfa_code", "").strip()
    if not mfa_code:
        raise HTTPException(status_code=400, detail="Código MFA é obrigatório.")

    # Validar formato: 4 a 8 dígitos (códigos SMS tipicamente têm este tamanho)
    if not mfa_code.isdigit() or len(mfa_code) < 4 or len(mfa_code) > 8:
        raise HTTPException(
            status_code=400,
            detail="Código MFA inválido. Deve conter entre 4 e 8 dígitos."
        )

    # Verificar que existe um job em estado "awaiting_mfa" para este processo
    job = await db.portal_scraper_jobs.find_one(
        {"process_id": process_id, "status": "awaiting_mfa"},
        {"_id": 0}
    )
    if not job:
        # Pode ter expirado ou o scraper ainda não pediu MFA
        existing = await db.portal_scraper_jobs.find_one(
            {"process_id": process_id},
            {"_id": 0, "status": 1}
        )
        if existing:
            if existing.get("status") in ("success", "error"):
                raise HTTPException(
                    status_code=409,
                    detail=f"O processo já terminou com estado '{existing['status']}'. Não é necessário código MFA."
                )
            elif existing.get("status") == "processing":
                raise HTTPException(
                    status_code=409,
                    detail="O scraper ainda está a processar o login. Aguarde que o pedido de MFA apareça."
                )
        else:
            raise HTTPException(
                status_code=404,
                detail="Nenhum job de scraper encontrado para este processo."
            )

    # Guardar código MFA no Redis (TTL 300s = 5 minutos)
    from services.mfa_cache import set_mfa_code
    success = await set_mfa_code(process_id, mfa_code, ttl=300)

    if not success:
        raise HTTPException(
            status_code=500,
            detail="Erro ao guardar o código MFA. Tente novamente."
        )

    logger.info(
        f"[PORTAL] Código MFA submetido para processo {process_id} "
        f"({len(mfa_code)} dígitos)"
    )

    return JSONResponse(content={
        "success": True,
        "message": "Código submetido com sucesso. O scraper vai utilizá-lo automaticamente.",
        "process_id": process_id,
    })


async def run_get_scraper_job_status(job_id: str):
    """
    Retorna o estado de um job de scraper (para polling pelo frontend).

    Após submeter fetch-financas ou fetch-seguranca-social, o frontend
    pode fazer polling a este endpoint para saber quando os documentos
    estão prontos.

    Returns:
    - status: "processing" | "success" | "error"
    - documents_count: número de documentos obtidos (se sucesso)
    - error_type: tipo de erro (se erro)
    - message: mensagem de estado
    """
    job = await db.portal_scraper_jobs.find_one(
        {"id": job_id},
        {"_id": 0}
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado.")

    return job


