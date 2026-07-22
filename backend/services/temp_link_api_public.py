"""Public (unauthenticated) handlers for temporary document links.

Extraído de `routes/temp_links.py`.

Uses `temp_link_api_*` prefix — do **not** overwrite existing
`services/temp_link_service.py` (core TempLinkService).
"""
from __future__ import annotations

import asyncio
import io
import uuid
import zipfile
import logging
from datetime import datetime, timezone
from typing import List

from fastapi import HTTPException, UploadFile, BackgroundTasks
from fastapi.responses import StreamingResponse

from database import db
from models.temp_link import TempLinkType
from services.temp_link_service import temp_link_service

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {
    "pdf", "jpg", "jpeg", "png", "gif", "webp",
    "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "txt", "csv", "zip", "rar", "7z"
}


def validate_upload_extension(filename: str) -> str | None:
    """Return lowercase extension if allowed, else None."""
    ext = (filename.rsplit('.', 1)[1] if '.' in filename else '').lower()
    if ext not in ALLOWED_EXTENSIONS:
        return None
    return ext


def content_matches_extension(content: bytes, ext: str) -> bool:
    """Basic magic-byte check vs declared extension (pdf/jpg/png)."""
    if len(content) < 4:
        return True
    if ext == "pdf" and not content.startswith(b"%PDF"):
        return False
    if ext in ("jpg", "jpeg") and content[:3] != b"\xFF\xD8\xFF":
        return False
    if ext == "png" and content[:4] != b"\x89PNG":
        return False
    return True


async def run_get_public_link_info(token: str) -> dict:
    """Obtém informações públicas sobre um link temporário."""
    validation = await temp_link_service.validate_link(token)

    if not validation["valid"]:
        return {
            "valid": False,
            "error": validation.get("error")
        }

    link = validation["link"]

    # Retornar apenas informações necessárias
    return {
        "valid": True,
        "token": token,
        "link_type": link["link_type"],
        "client_name": link["client_name"],
        "expires_at": link["expires_at"],
        "remaining_uses": validation["remaining_uses"],
        "description": link.get("description"),
        "file_count": len(link.get("file_paths", [])) if link.get("file_paths") else 0
    }


async def run_upload_via_temp_link(
    token: str,
    files: List[UploadFile],
    background_tasks: BackgroundTasks | None = None,
) -> dict:
    """Faz upload de ficheiros através de um link temporário."""
    # Validar link
    try:
        validation = await temp_link_service.validate_link(token)
    except Exception as e:
        logger.error(f"Erro ao validar link temp: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Serviço temporariamente indisponível. Tente novamente.")

    if not validation["valid"]:
        raise HTTPException(status_code=400, detail=validation.get("error"))

    link = validation["link"]

    if link.get("link_type") != TempLinkType.UPLOAD.value:
        raise HTTPException(
            status_code=400,
            detail="Este link é para download, não para upload."
        )

    if not files:
        raise HTTPException(status_code=400, detail="Nenhum ficheiro enviado")

    # Importar serviço S3
    try:
        from services.s3_storage import s3_service
    except ImportError as e:
        logger.error(f"S3 service indisponível: {e}")
        raise HTTPException(status_code=503, detail="Serviço de armazenamento indisponível.")

    process_id = link.get("process_id")
    client_name = link.get("client_name", "Cliente")

    # Obter dados do processo para segundo titular
    try:
        process = await db.processes.find_one({"id": process_id})
    except Exception as e:
        logger.error(f"DB error fetching process {process_id}: {e}", exc_info=True)
        process = None
    second_client_name = None
    s3_folder = None
    if process:
        titular2 = process.get("titular2_data") or {}
        second_client_name = process.get("second_client_name") or titular2.get("nome") or titular2.get("name")
        s3_folder = process.get("s3_folder")

    uploaded_files = []

    for file in files:
        filename_safe = file.filename or "unknown_file"
        try:
            # Ler conteúdo
            content = await file.read()

            ext = validate_upload_extension(filename_safe)
            if ext is None:
                bad_ext = (filename_safe.rsplit('.', 1)[1] if '.' in filename_safe else '').lower()
                uploaded_files.append({"filename": filename_safe, "error": f"Tipo de ficheiro não permitido: .{bad_ext}"})
                continue

            # Verificar magic bytes vs extensão (apenas para tipos suportados)
            if not content_matches_extension(content, ext):
                uploaded_files.append({"filename": filename_safe, "error": "Conteúdo do ficheiro não corresponde à extensão"})
                continue

            # Determinar categoria (padrão: "Cliente Upload")
            category = "Cliente_Upload"

            # Sanitizar nome
            import re
            import unicodedata
            name_part = filename_safe.rsplit('.', 1)[0] if '.' in filename_safe else filename_safe
            file_ext = filename_safe.rsplit('.', 1)[1] if '.' in filename_safe else 'pdf'

            name_normalized = unicodedata.normalize('NFKD', name_part)
            name_normalized = name_normalized.encode('ASCII', 'ignore').decode('ASCII')
            name_normalized = re.sub(r'[^\w\s-]', '', name_normalized)
            name_normalized = re.sub(r'[\s_]+', '_', name_normalized.strip())[:50]

            date_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            normalized_filename = f"{category}_{date_str}_{name_normalized}.{file_ext}"

            # Upload para S3
            from io import BytesIO
            file_buffer = BytesIO(content)

            s3_path = s3_service.upload_file(
                file_buffer,
                process_id,
                client_name,
                category,
                normalized_filename,
                file.content_type,
                second_client_name=second_client_name,
                s3_folder=s3_folder
            )

            if s3_path:
                uploaded_files.append({
                    "original_name": filename_safe,
                    "normalized_name": normalized_filename,
                    "s3_path": s3_path,
                    "size": len(content),
                    "content_type": file.content_type
                })
            else:
                uploaded_files.append({"filename": filename_safe, "error": "Erro no upload para o storage"})

        except Exception as e:
            logger.error(f"Erro ao fazer upload de {filename_safe}: {e}", exc_info=True)
            uploaded_files.append({"filename": filename_safe, "error": f"Erro ao processar ficheiro: {str(e)}"})

    # Separar ficheiros com sucesso e erros
    failed_files = [f for f in uploaded_files if "error" in f]
    success_files = [f for f in uploaded_files if "error" not in f]

    if not success_files:
        raise HTTPException(
            status_code=400,
            detail=f"Nenhum ficheiro foi carregado com sucesso. Erros: {', '.join(f.get('error', 'desconhecido') for f in failed_files)}"
        )

    # Marcar link como usado (apenas ficheiros com sucesso)
    try:
        await temp_link_service.use_link(token, success_files)
    except Exception as e:
        logger.error(f"Erro ao marcar link como usado: {e}", exc_info=True)

    # Adicionar atividade ao processo (non-critical)
    try:
        activity = {
            "id": str(uuid.uuid4()),
            "process_id": process_id,
            "type": "document_upload",
            "comment": f"Cliente carregou {len(success_files)} documento(s) via link temporário",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "created_by": None,  # Sistema
            "metadata": {
                "files": [f["original_name"] for f in success_files],
                "via_temp_link": True,
                "failed_files": [f["filename"] for f in failed_files] if failed_files else []
            }
        }
        await db.activities.insert_one(activity)
    except Exception as e:
        logger.error(f"Erro ao registar atividade: {e}", exc_info=True)

    # Notificar consultor/mediador atribuído (non-critical)
    try:
        if process:
            from services.notification_service import notification_service
            assigned_consultor_id = process.get("assigned_consultor_id")
            if assigned_consultor_id:
                await notification_service.create_notification(
                    user_id=assigned_consultor_id,
                    title="📤 Documentos Carregados",
                    message=f"O cliente {client_name} carregou {len(success_files)} documento(s)",
                    type="document_upload",
                    link=f"/processo/{process_id}"
                )
    except Exception as e:
        logger.warning(f"Erro ao notificar consultor: {e}")

    result = {
        "success": len(failed_files) == 0,
        "message": f"{len(success_files)} ficheiro(s) carregado(s) com sucesso" if len(failed_files) == 0 else f"{len(success_files)} de {len(files)} ficheiro(s) carregado(s)",
        "files": success_files,
    }
    if failed_files:
        result["errors"] = failed_files

    return result


async def run_download_via_temp_link(token: str, file_index: int = 0) -> dict:
    """Faz download de um ficheiro através de um link temporário."""
    # Validar link
    validation = await temp_link_service.validate_link(token)

    if not validation["valid"]:
        raise HTTPException(status_code=400, detail=validation.get("error"))

    link = validation["link"]

    if link["link_type"] != TempLinkType.DOWNLOAD.value:
        raise HTTPException(
            status_code=400,
            detail="Este link é para upload, não para download."
        )

    file_paths = link.get("file_paths", [])

    if not file_paths:
        raise HTTPException(status_code=404, detail="Nenhum ficheiro disponível")

    if file_index < 0 or file_index >= len(file_paths):
        raise HTTPException(status_code=400, detail="Índice de ficheiro inválido")

    s3_path = file_paths[file_index]

    # Importar serviço S3
    from services.s3_storage import s3_service

    url = s3_service.get_presigned_url(s3_path)

    if not url:
        raise HTTPException(status_code=500, detail="Erro ao gerar link de download")

    # NOTA: Não chamamos use_link() aqui porque o consumo é feito
    # pelo endpoint /download-all (batch). Isto permite descarregar
    # ficheiros individuais sem esgotar o limite de utilizações.

    return {
        "success": True,
        "url": url,
        "filename": s3_path.split("/")[-1]
    }


async def run_download_all_via_temp_link(token: str) -> StreamingResponse:
    """Descarrega TODOS os ficheiros de um link temporário como um ZIP."""
    # Validar link
    validation = await temp_link_service.validate_link(token)

    if not validation["valid"]:
        raise HTTPException(status_code=400, detail=validation.get("error"))

    link = validation["link"]

    if link["link_type"] != TempLinkType.DOWNLOAD.value:
        raise HTTPException(
            status_code=400,
            detail="Este link é para upload, não para download."
        )

    file_paths = link.get("file_paths", [])

    if not file_paths:
        raise HTTPException(status_code=404, detail="Nenhum ficheiro disponível")

    # Importar serviço S3
    from services.s3_storage import s3_service

    # Criar ZIP em memória com todos os ficheiros do S3
    zip_buffer = io.BytesIO()
    zip_files_count = 0

    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for s3_path in file_paths:
            try:
                # Offload de I/O bloqueante (leitura S3) para não bloquear o event loop.
                file_content = await asyncio.to_thread(s3_service.get_file_content, s3_path)
                if file_content:
                    filename = s3_path.split("/")[-1]
                    # Evitar duplicados no ZIP (caso hajam ficheiros com o mesmo nome)
                    zip_filename = filename
                    counter = 1
                    while zip_filename in zip_file.namelist():
                        name_part, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
                        zip_filename = f"{name_part}_{counter}.{ext}" if ext else f"{name_part}_{counter}"
                        counter += 1
                    zip_file.writestr(zip_filename, file_content)
                    zip_files_count += 1
                else:
                    logger.warning(f"Falha ao obter ficheiro do S3: {s3_path}")
            except Exception as e:
                logger.error(f"Erro ao processar ficheiro {s3_path}: {e}")

    if zip_files_count == 0:
        raise HTTPException(status_code=500, detail="Erro ao obter ficheiros do storage")

    zip_buffer.seek(0)

    # Construir nome do ZIP baseado no nome do cliente
    client_name = link.get("client_name", "documentos")
    safe_name = client_name.replace(" ", "_")[:30]
    zip_filename = f"{safe_name}_documentos.zip"

    # Marcar link como usado (apenas 1 utilização para TODOS os ficheiros)
    await temp_link_service.use_link(token)

    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=\"{zip_filename}\""
        }
    )


async def run_list_temp_link_files(token: str) -> dict:
    """Lista ficheiros disponíveis para download num link temporário."""
    validation = await temp_link_service.validate_link(token)

    if not validation["valid"]:
        raise HTTPException(status_code=400, detail=validation.get("error"))

    link = validation["link"]

    if link["link_type"] != TempLinkType.DOWNLOAD.value:
        raise HTTPException(
            status_code=400,
            detail="Este link é para upload, não para download."
        )

    file_paths = link.get("file_paths", [])

    # Retornar lista de ficheiros
    files = []
    for idx, path in enumerate(file_paths):
        filename = path.split("/")[-1]
        files.append({
            "index": idx,
            "filename": filename,
            "path": path
        })

    return {
        "valid": True,
        "files": files,
        "total": len(files)
    }
