"""
Upload directo S3 via pre-signed URL + confirmação pós-PUT.

Extraído de `routes/documents.py` (`generate_upload_url`, `confirm_upload`).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import BackgroundTasks, HTTPException

from database import db
from services.document_auto_categorize import auto_categorize_document_background
from services.document_constants import (
    DEFAULT_CLIENT_NAME,
    ERROR_FILE_ACCESS_DENIED,
    ERROR_PROCESS_NOT_FOUND,
)
from services.document_filenames import normalize_filename
from services.document_intake import (
    categoria_para_o_portal,
    descreve_destino,
    descricao_para_o_utilizador,
    planear_entrada,
    registar_na_fila_da_ia,
)
from services.document_process_resolve import (
    assert_path_within_document_root,
    assert_s3_file_belongs_to_process,
    extract_second_client_name,
)
from services.s3_content_quarantine import exigir_conteudo_valido
from services.document_upload import _auto_fulfill_portal_request
from services.document_visibility import assert_can_upload_to_process
from services.history import log_history
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)


async def run_generate_upload_url(data: dict, *, user: dict) -> dict:
    """Gera pre-signed URL PUT para upload directo frontend → S3."""
    process_id = data.get("process_id")
    filename = data.get("filename")
    content_type = data.get("content_type")
    category = data.get("category", "Outros")
    custom_filename = data.get("custom_filename")

    if not process_id:
        raise HTTPException(status_code=400, detail="process_id é obrigatório")
    if not filename:
        raise HTTPException(status_code=400, detail="filename é obrigatório")
    if not content_type:
        raise HTTPException(status_code=400, detail="content_type é obrigatório")

    if not s3_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Serviço de armazenamento S3 não configurado. "
                "Contacte o administrador."
            ),
        )

    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)
    await assert_can_upload_to_process(user, process)

    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)
    second_client_name = extract_second_client_name(process)
    s3_folder = process.get("s3_folder")

    # DESVIO INTELIGENTE (Bloco 2): a pasta do objecto decide-se AQUI, porque
    # o PUT pré-assinado fica preso à chave. Processo por indexar → `Index`.
    plano = planear_entrada(process, category)
    category = plano.categoria

    if custom_filename:
        normalized_filename = normalize_filename(custom_filename, category)
    else:
        normalized_filename = normalize_filename(filename, category)

    result = s3_service.generate_upload_presigned_url(
        client_id=process_id,
        client_name=client_name,
        category=category,
        filename=normalized_filename,
        content_type=content_type,
        second_client_name=second_client_name,
        s3_folder=s3_folder,
        expiration=300,
    )

    if not result:
        raise HTTPException(
            status_code=500,
            detail="Erro ao gerar URL de upload. Por favor tente novamente.",
        )

    logger.info(
        f"[DIRECT-UPLOAD] URL gerada para {normalized_filename} "
        f"por {user.get('email')}"
    )

    return {
        "success": True,
        "upload_url": result["upload_url"],
        "file_key": result["file_key"],
        "normalized_filename": normalized_filename,
        "original_filename": filename,
        "expires_at": result["expires_at"],
        "expires_in_seconds": result["expires_in_seconds"],
        "method": "PUT",
        "headers": {"Content-Type": content_type},
        "category": category,
        "intake": descricao_para_o_utilizador(plano),
    }


async def run_confirm_upload(
    data: dict,
    *,
    background_tasks: BackgroundTasks,
    user: dict,
) -> dict:
    """Confirma PUT S3 e agenda auto-categorização + histórico."""
    process_id = data.get("process_id")
    file_key = data.get("file_key")
    original_filename = data.get("original_filename")
    category = data.get("category", "Outros")
    # O `file_size`/`content_type` do CORPO do pedido são DECLARAÇÕES do
    # cliente e não são usados: o que vale é o veredicto da quarentena,
    # que os lê do objecto real. Continuam aceites por compatibilidade de
    # API (o `directS3Upload` do frontend ainda os envia).
    _ = (data.get("file_size"), data.get("content_type"))

    if not process_id:
        raise HTTPException(status_code=400, detail="process_id é obrigatório")
    if not file_key:
        raise HTTPException(status_code=400, detail="file_key é obrigatório")
    if not original_filename:
        raise HTTPException(status_code=400, detail="original_filename é obrigatório")

    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail=ERROR_PROCESS_NOT_FOUND)
    await assert_can_upload_to_process(user, process)

    client_name = process.get("client_name", DEFAULT_CLIENT_NAME)

    # ============================================================
    # POSSE ANTES DE CONTEÚDO (D-1, Set 2026)
    # ============================================================
    # O `file_key` vem do CORPO do pedido e, até aqui, era validado só
    # com `s3_service.file_exists()` — a MESMA lacuna do Incidente P0 do
    # Portal, nesta superfície. Um membro da equipa com sessão válida
    # nomeava `backups/dump-2026-09-01.zip` e a resposta devolvia-lhe um
    # `temporary_url` pré-assinado para o descarregar; no mesmo bucket
    # vivem os documentos de TODAS as redes, os backups e os
    # `companies/*`. Pior: o registo criado com esse `s3_path` fazia os
    # caminhos de download autorizarem a chave para sempre.
    #
    # As duas guardas são ambas precisas e nenhuma substitui a outra: a
    # da RAIZ defende de um `s3_folder` envenenado que aponte para fora
    # da árvore de documentos; a de POSSE defende do processo do vizinho.
    #
    # A ORDEM é a regra da quarentena do Portal: posse ANTES de
    # conteúdo. Invertida, o backend passava a ler 2 KB de qualquer
    # chave que um utilizador nomeasse — um oráculo feito com a própria
    # parede.
    # SEM DONO, RECUSA-SE. O degradado de
    # `assert_s3_file_belongs_to_process` (sem `s3_folder`) monta o
    # prefixo a partir do `client_name`; com o nome VAZIO os prefixos
    # válidos passam a ser `"Documentação Clientes/"` — a raiz inteira, ou
    # seja, a guarda deixa de guardar. É a mesma regra do
    # `portal_upload_ops`, aplicada aqui no ponto de chamada por não
    # alargar o raio da alteração à guarda partilhada, que serve dezenas
    # de endpoints do CRM.
    if not process.get("s3_folder") and not (process.get("client_name") or "").strip():
        logger.warning(
            "[CONFIRM-UPLOAD] Processo %s sem pasta nem nome de cliente — "
            "recusado por não ser possível determinar a posse do ficheiro.",
            process_id,
        )
        raise HTTPException(status_code=403, detail=ERROR_FILE_ACCESS_DENIED)

    assert_path_within_document_root(file_key)
    assert_s3_file_belongs_to_process(file_key, process)

    # Só agora se toca no objecto. `exigir_conteudo_valido` substitui o
    # `s3_service.file_exists()`: é o MESMO `head_object`, mas responde a
    # mais perguntas (tamanho e tipo REAIS) e apaga o que reprovar por
    # CONTEÚDO. Falha de leitura é 503 e não apaga nada.
    veredicto = await exigir_conteudo_valido(file_key, filename=original_filename)
    content_type = veredicto.tipo_detectado or "application/octet-stream"
    file_size = veredicto.tamanho

    normalized_filename = file_key.split("/")[-1] if "/" in file_key else file_key

    # DESVIO INTELIGENTE (Bloco 2): por indexar → fila da IA; indexado → só
    # guardado. A triagem à entrada (SEGUNDA chamada ao modelo sobre o mesmo
    # ficheiro, só para escolher a pasta) saiu: o objecto já está na pasta
    # que o `run_generate_upload_url` decidiu.
    plano = planear_entrada(process, category)
    category = plano.categoria

    file_content = None
    if plano.passa_pela_ia:
        await registar_na_fila_da_ia(
            process_id=process_id,
            client_name=client_name,
            s3_path=file_key,
            filename=normalized_filename,
            origem="upload_directo",
        )
        try:
            file_content = await asyncio.to_thread(s3_service.get_file_content, file_key)
        except Exception as e:
            logger.warning(f"[CONFIRM-UPLOAD] Não foi possível ler o ficheiro para a IA: {e}")
        try:
            if file_content:
                background_tasks.add_task(
                    auto_categorize_document_background,
                    process_id=process_id,
                    client_name=client_name,
                    s3_path=file_key,
                    filename=normalized_filename,
                    file_content=file_content,
                )
        except Exception as e:
            logger.warning(f"[CONFIRM-UPLOAD] Erro ao agendar categorização: {e}")

    try:
        await log_history(
            process_id=process_id,
            user=user,
            action="Carregou documento (upload direto)",
            field="documento",
            new_value=f"{normalized_filename} ({descreve_destino(plano)})",
        )
    except Exception as e:
        logger.warning(f"[CONFIRM-UPLOAD] Erro ao registar histórico: {e}")

    # Auto-Match — o documento acabou de ser gravado (S3 + categoria); tenta
    # imediatamente satisfazer um pedido pendente do Portal do Cliente.
    portal_fulfill = await _auto_fulfill_portal_request(
        process_id,
        {
            "category": categoria_para_o_portal(plano),
            "filename": normalized_filename or original_filename,
            "s3_path": file_key,
            "content_type": content_type,
            "file_size": file_size,
        },
        user=user,
    )

    logger.info(f"[CONFIRM-UPLOAD] Upload confirmado: {normalized_filename}")

    # ============================================================
    # PACOTE 10 — TASK LOG DO MONITOR GLOBAL ("Processos em
    # Segundo Plano"): o upload confirmado fica visível no widget
    # da topbar com estado Success (pedido explícito do Pacote 10 —
    # acções como "Upload de Documentos" com estado Loading/
    # Success/Failed). Best-effort: nunca afecta a resposta.
    # ============================================================
    try:
        from models.task_log import TaskType
        from services.task_log_service import task_log_service

        upload_task = await task_log_service.create_task(
            task_type=TaskType.DOCUMENT_UPLOAD,
            user_id=user.get("id"),
            title=f"Upload de Documento: {original_filename}",
            description=f"Documento carregado para o processo (categoria: {category}).",
            process_id=process_id,
            metadata={
                "s3_path": file_key,
                "category": category,
                "kind": "confirm_upload",
            },
        )
        # O upload JÁ terminou com sucesso quando o confirm corre — a
        # tarefa nasce concluída (fica no widget até ao OK do utilizador).
        if upload_task:
            await task_log_service.mark_completed(
                upload_task.task_id,
                result_data={"s3_path": file_key, "category": category},
            )
    except Exception as task_log_err:  # pragma: no cover — best-effort
        logger.warning(
            f"[CONFIRM-UPLOAD] Falha ao criar task log do monitor: {task_log_err}"
        )

    # ============================================================
    # PACOTE 11 (Eixo 1) — upload de documento delegado ao MOTOR DE
    # AUTOMAÇÃO (rules engine, /admin/automation/rules): regras com o
    # trigger "document_uploaded" (ex.: notificar consultor, mudar fase)
    # passam a disparar aqui. Fire-and-forget: falhas do motor nunca
    # afectam a confirmação do upload.
    # ============================================================
    try:
        from services.workflow_engine import process_trigger
        await process_trigger(
            "document_uploaded",
            {
                "process_id": process_id,
                "process_number": process.get("process_number"),
                "client_name": client_name,
                "client_email": process.get("client_email"),
                "filename": normalized_filename or original_filename,
                "category": category,
                "user_id": user.get("id"),
                "user_name": user.get("name"),
            },
        )
    except Exception as automation_err:  # pragma: no cover — best-effort
        logger.warning(
            f"[CONFIRM-UPLOAD] Motor de automação falhou (não fatal) para o "
            f"processo {process_id}: {automation_err}"
        )

    response_data: dict[str, Any] = {
        "success": True,
        "s3_path": file_key,
        "normalized_filename": normalized_filename,
        "original_filename": original_filename,
        "category": category,
        # `temporary_url` SAIU da resposta (D-1): era um URL pré-assinado
        # para a chave que o cliente nomeou, e portanto o veículo da fuga.
        # Ninguém o lia — o `directS3Upload` do `api.js` devolvia-o e não
        # tem chamadores. Mesma decisão do `portal/confirm-upload`.
        "message": "Upload registado com sucesso",
        "auto_categorization": (
            "dispensada" if not plano.passa_pela_ia
            else ("iniciada" if file_content else "indisponível")
        ),
        "portal_fulfilled": portal_fulfill.get("fulfilled", 0),
        "intake": descricao_para_o_utilizador(plano),
    }

    return response_data
