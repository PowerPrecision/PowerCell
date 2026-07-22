"""S3 File Explorer ops (list/rename/delete/create/upload/download).

Do NOT name this module `admin_storage.py` (collides with routes/admin_storage.py).
Do NOT overwrite `s3_storage.py` or `storage_service.py`.
Extraído de `routes/admin_storage.py`.
"""
from __future__ import annotations

import logging

from fastapi import HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from models.auth import UserRole

logger = logging.getLogger(__name__)

# Base path do explorador de ficheiros — pasta raiz virtual do S3
S3_EXPLORER_BASE_PATH = "Documentação Clientes"

# Roles that can perform file operations
FILE_OPS_ROLES = [UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]
# Roles that can view/download files (broader access)
FILE_VIEW_ROLES = [
    UserRole.ADMIN,
    UserRole.CEO,
    UserRole.DIRETOR,
    UserRole.ADMINISTRATIVO,
    UserRole.CONSULTOR,
    UserRole.INTERMEDIARIO,
    UserRole.INDEXACAO,
]


class S3RenameRequest(BaseModel):
    old_path: str
    new_name: str
    is_folder: bool = False


class S3DeleteRequest(BaseModel):
    path: str
    is_folder: bool = False


class S3CreateFolderRequest(BaseModel):
    folder_path: str


def _resolve_explorer_path(path: str) -> str:
    """
    Resolve o caminho S3 para operações do File Explorer.

    Se o caminho estiver vazio, retorna o base path ("Documentação Clientes").
    Se o caminho já contiver o base path, retorna como está.
    Se o caminho não contiver o base path, prefixa com ele.

    Isto garante que as operações de criação/upload respeitem
    a pasta actual onde o utilizador navegou, corrigindo o bug
    onde pastas criadas na raiz do explorador iam parar à raiz
    do bucket S3 em vez de dentro de "Documentação Clientes/".
    """
    path = path.strip()
    if not path:
        return S3_EXPLORER_BASE_PATH
    if path.startswith(S3_EXPLORER_BASE_PATH):
        return path
    return f"{S3_EXPLORER_BASE_PATH}/{path}"


async def run_get_s3_folder_contents(folder_path: str, user: dict):
    """Lista conteúdo de uma pasta S3. Se folder_path vazio, lista a raiz do bucket (Documentação Clientes/)."""
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="S3 não configurado")

    # Se folder_path vazio, usar a pasta principal "Documentação Clientes/" como raiz
    prefix = _resolve_explorer_path(folder_path.strip())

    try:
        list_prefix = prefix if prefix.endswith("/") else f"{prefix}/"
        response = s3_service.s3_client.list_objects_v2(
            Bucket=s3_service.bucket_name,
            Prefix=list_prefix,
            Delimiter="/"
        )

        subfolders = []
        for common_prefix in response.get("CommonPrefixes", []):
            subfolder_path = common_prefix.get("Prefix", "")
            parts = subfolder_path.rstrip("/").split("/")
            subfolder_name = parts[-1] if parts else ""
            if subfolder_name:
                subfolders.append({
                    "path": subfolder_path.rstrip("/"),
                    "name": subfolder_name
                })

        files = []
        for obj in response.get("Contents", []):
            key = obj.get("Key", "")
            if key != list_prefix and not key.endswith("/"):
                file_name = key.split("/")[-1]
                files.append({
                    "path": key,
                    "name": file_name,
                    "size": obj.get("Size", 0),
                    "last_modified": obj.get("LastModified").isoformat() if obj.get("LastModified") else None
                })

        return {
            "folder_path": folder_path,
            "subfolders": subfolders,
            "files": files,
            "total_items": len(subfolders) + len(files)
        }

    except Exception as e:
        logger.error(f"Erro ao listar conteúdo S3: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao listar pasta: {str(e)}")


async def run_s3_rename(data: S3RenameRequest, user: dict):
    """Renomeia um ficheiro ou pasta no S3 (copy + delete)."""
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="S3 não configurado")

    old_path = data.old_path
    new_name = data.new_name.strip()

    if not old_path or not new_name:
        raise HTTPException(status_code=400, detail="Caminho original e novo nome são obrigatórios")

    # Build the new path: replace the last segment with the new name
    path_parts = old_path.rstrip("/").split("/")
    path_parts[-1] = new_name
    new_path = "/".join(path_parts)

    # If it's a folder, we need to rename all objects with the old prefix
    if data.is_folder:
        try:
            old_prefix = old_path.rstrip("/") + "/"
            new_prefix = new_path.rstrip("/") + "/"

            # List all objects under the old prefix
            response = s3_service.s3_client.list_objects_v2(
                Bucket=s3_service.bucket_name,
                Prefix=old_prefix
            )

            moved_count = 0
            for obj in response.get("Contents", []):
                old_key = obj["Key"]
                # Replace old prefix with new prefix
                new_key = new_prefix + old_key[len(old_prefix):]

                # Copy to new location
                copy_source = {'Bucket': s3_service.bucket_name, 'Key': old_key}
                s3_service.s3_client.copy_object(
                    CopySource=copy_source,
                    Bucket=s3_service.bucket_name,
                    Key=new_key
                )

                # Delete from old location
                s3_service.s3_client.delete_object(
                    Bucket=s3_service.bucket_name,
                    Key=old_key
                )
                moved_count += 1

            logger.info(f"Pasta renomeada: {old_path} -> {new_path} ({moved_count} objetos movidos)")
            return {"success": True, "old_path": old_path, "new_path": new_path, "objects_moved": moved_count}

        except Exception as e:
            logger.error(f"Erro ao renomear pasta S3: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao renomear pasta: {str(e)}")
    else:
        # Rename a single file
        success = s3_service.rename_file(old_path, new_path)
        if success:
            return {"success": True, "old_path": old_path, "new_path": new_path}
        else:
            raise HTTPException(status_code=500, detail="Erro ao renomear ficheiro")


async def run_s3_delete(data: S3DeleteRequest, user: dict):
    """Elimina um ficheiro ou pasta (e todo o seu conteúdo) do S3."""
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="S3 não configurado")

    path = data.path
    if not path:
        raise HTTPException(status_code=400, detail="Caminho é obrigatório")

    if data.is_folder:
        try:
            prefix = path.rstrip("/") + "/"

            # List all objects under the prefix
            deleted_count = 0
            continuation_token = None

            while True:
                kwargs = {
                    "Bucket": s3_service.bucket_name,
                    "Prefix": prefix,
                }
                if continuation_token:
                    kwargs["ContinuationToken"] = continuation_token

                response = s3_service.s3_client.list_objects_v2(**kwargs)

                for obj in response.get("Contents", []):
                    s3_service.s3_client.delete_object(
                        Bucket=s3_service.bucket_name,
                        Key=obj["Key"]
                    )
                    deleted_count += 1

                if response.get("IsTruncated"):
                    continuation_token = response.get("NextContinuationToken")
                else:
                    break

            logger.info(f"Pasta eliminada: {path} ({deleted_count} objetos removidos)")
            return {"success": True, "path": path, "objects_deleted": deleted_count}

        except Exception as e:
            logger.error(f"Erro ao eliminar pasta S3: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao eliminar pasta: {str(e)}")
    else:
        # Delete a single file
        success = s3_service.delete_file(path)
        if success:
            return {"success": True, "path": path}
        else:
            raise HTTPException(status_code=500, detail="Erro ao eliminar ficheiro")


async def run_s3_create_folder(data: S3CreateFolderRequest, user: dict):
    """Cria uma pasta no S3 (cria um ficheiro marcador .keep vazio).

    O caminho é resolvido relativamente ao base path do explorador
    ("Documentação Clientes"), garantindo que a pasta é criada no
    nível correto da árvore de ficheiros, mesmo quando o utilizador
    está na raiz do explorador.
    """
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="S3 não configurado")

    folder_path = data.folder_path.strip()
    if not folder_path:
        raise HTTPException(status_code=400, detail="Caminho da pasta é obrigatório")

    # Resolver caminho relativo ao base path do explorador
    folder_path = _resolve_explorer_path(folder_path)

    # Ensure path ends with /
    if not folder_path.endswith("/"):
        folder_path += "/"

    # Create a .keep marker file to represent the folder
    marker_path = folder_path + ".keep"

    try:
        s3_service.s3_client.put_object(
            Bucket=s3_service.bucket_name,
            Key=marker_path,
            Body=b"",
            ContentType="application/x-directory"
        )
        logger.info(f"Pasta criada no S3: {folder_path}")
        return {"success": True, "folder_path": folder_path, "marker": marker_path}
    except Exception as e:
        logger.error(f"Erro ao criar pasta S3: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao criar pasta: {str(e)}")


async def run_s3_upload(file: UploadFile, folder_path: str, user: dict):
    """Faz upload de um ficheiro para uma pasta S3 (usado pelo File Explorer).

    O caminho é resolvido relativamente ao base path do explorador
    ("Documentação Clientes"), garantindo que o ficheiro é colocado no
    nível correto da árvore de ficheiros, mesmo quando o utilizador
    está na raiz do explorador.
    """
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="S3 não configurado")

    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="Ficheiro é obrigatório")

    # Resolver caminho relativo ao base path do explorador
    base_path = _resolve_explorer_path(folder_path.strip())
    if not base_path.endswith("/"):
        base_path += "/"

    s3_key = f"{base_path}{file.filename}"

    try:
        content = await file.read()
        content_type = file.content_type or "application/octet-stream"

        s3_service.s3_client.put_object(
            Bucket=s3_service.bucket_name,
            Key=s3_key,
            Body=content,
            ContentType=content_type
        )

        logger.info(f"Ficheiro enviado para S3: {s3_key} ({len(content)} bytes)")
        return {
            "success": True,
            "path": s3_key,
            "filename": file.filename,
            "size": len(content),
            "content_type": content_type
        }
    except Exception as e:
        logger.error(f"Erro ao fazer upload para S3: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao enviar ficheiro: {str(e)}")


async def run_s3_download(path: str, user: dict):
    """Faz download de um ficheiro do S3 (streaming response)."""
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="S3 não configurado")

    if not path:
        raise HTTPException(status_code=400, detail="Caminho é obrigatório")

    try:
        response = s3_service.s3_client.get_object(
            Bucket=s3_service.bucket_name,
            Key=path
        )

        filename = path.split("/")[-1]
        content_type = response.get("ContentType", "application/octet-stream")

        def iterfile():
            chunk_size = 8192
            stream = response["Body"]
            while True:
                chunk = stream.read(chunk_size)
                if not chunk:
                    break
                yield chunk

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"'
        }

        return StreamingResponse(
            iterfile(),
            media_type=content_type,
            headers=headers
        )
    except Exception as e:
        logger.error(f"Erro ao fazer download do S3: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao fazer download: {str(e)}")
