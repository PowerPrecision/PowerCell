"""
Proxy de download S3 via backend (CORS-safe streaming).

Extraído de `routes/documents.py` (`proxy_s3_file`).
"""
from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote

from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from services.document_constants import (
    ERROR_S3_FILE_NOT_FOUND,
    ERROR_S3_NOT_CONFIGURED,
)
from services.document_process_resolve import assert_path_within_document_root
from services.document_s3_paths import s3_path_variations
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)


def _get_s3_object(key: str):
    return s3_service.s3_client.get_object(Bucket=s3_service.bucket_name, Key=key)


async def run_proxy_s3_file(file_path: str) -> StreamingResponse:
    """Stream ficheiro S3 através do backend (tenta variações de path)."""
    logger.info(f"[PROXY] Acesso a ficheiro: {file_path}")

    # SEGURANÇA (IDOR/path-scope): antes de tocar em S3, garantir que o path
    # está dentro da raiz "Documentação Clientes/" — caso contrário qualquer
    # utilizador autenticado poderia servir-se deste proxy para descarregar
    # ficheiros fora do âmbito de documentos (ex.: backups/*.zip).
    assert_path_within_document_root(file_path)

    if not s3_service.is_configured():
        logger.error("[PROXY] S3 não configurado")
        raise HTTPException(status_code=500, detail=ERROR_S3_NOT_CONFIGURED)

    response = None
    used_path = None
    loop = asyncio.get_event_loop()

    for try_path in s3_path_variations(file_path):
        try:
            response = await loop.run_in_executor(
                None, lambda p=try_path: _get_s3_object(p)
            )
            used_path = try_path
            logger.info(f"[PROXY] Ficheiro encontrado com path: {try_path}")
            break
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "NoSuchKey":
                logger.debug(f"[PROXY] Path não encontrado: {try_path}")
                continue
            if error_code == "AccessDenied":
                logger.error(f"[PROXY] Acesso negado ao ficheiro: {try_path}")
                continue
            logger.error(f"[PROXY] Erro S3 ({error_code}) no path {try_path}: {e}")
            continue
        except NoCredentialsError:
            logger.error("[PROXY] Credenciais S3 não configuradas")
            raise HTTPException(
                status_code=500, detail="Credenciais S3 não configuradas"
            )
        except Exception as e:
            logger.error(
                f"[PROXY] Erro inesperado ao tentar {try_path}: "
                f"{type(e).__name__}: {e}"
            )
            continue

    if response is None:
        logger.warning(
            f"[PROXY] Ficheiro não encontrado em nenhuma variação: {file_path}"
        )
        raise HTTPException(status_code=404, detail=ERROR_S3_FILE_NOT_FOUND)

    try:
        content_type = response.get("ContentType", "application/octet-stream")
        content_length = response.get("ContentLength", 0)
        filename = used_path.split("/")[-1] if "/" in used_path else used_path
        logger.info(
            f"[PROXY] Streaming ficheiro: {filename} ({content_length} bytes)"
        )

        def iterfile():
            body = response["Body"]
            try:
                while True:
                    chunk = body.read(8192)
                    if not chunk:
                        break
                    yield chunk
            finally:
                body.close()

        encoded_filename = quote(filename, safe="")
        headers = {
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded_filename}",
            "Content-Length": str(content_length),
            "Cache-Control": "private, max-age=3600",
        }
        return StreamingResponse(
            iterfile(), media_type=content_type, headers=headers
        )
    except (BotoCoreError, IOError, OSError) as e:
        logger.error(f"[PROXY] Erro ao fazer proxy do ficheiro S3: {e}")
        raise HTTPException(
            status_code=500, detail=f"Erro ao obter ficheiro: {str(e)}"
        )
    except Exception as e:
        logger.error(f"[PROXY] Erro inesperado: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Erro interno: {str(e)}"
        )
