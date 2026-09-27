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
from services.s3_explorer_paths import (
    RAIZ_DO_EXPLORADOR,
    assert_dentro_da_raiz,
)
from services.s3_folder_relink import religar_apos_rename
from services.s3_explorer_scope import (
    ambito_do_utilizador,
    assert_pasta_no_ambito,
    filtrar_subpastas,
)

logger = logging.getLogger(__name__)

# Base path do explorador — reexportado de `s3_explorer_paths`, que é quem
# manda. Duas constantes com o mesmo valor divergem, e a divergência aqui
# seria uma fronteira de segurança a discordar de si própria.
S3_EXPLORER_BASE_PATH = RAIZ_DO_EXPLORADOR

# ────────────────────────────────────────────────────────────────────
# EXPLORADOR GLOBAL DE FICHEIROS — reaberto com isolamento (Épico 10)
#
# O Lote 5, ponto 1 trancou esta página a [ADMIN, CEO] porque o bucket está
# arrumado por pasta de CLIENTE e não havia `network_id` num prefixo S3
# para filtrar — era isolamento por ausência de utilizadores.
#
# Hoje a ponte existe: `processes.s3_folder` → `processes.network_id`, e
# `services/s3_explorer_scope.py` decide pasta a pasta (ver lá o desenho).
# A página pode reabrir.
#
# TRÊS NÍVEIS, porque as operações não pesam todas o mesmo:
#   VER        — navegar e descarregar. Todo o staff.
#   ESCREVER   — carregar ficheiros e criar pastas. Reversível.
#   DESTRUTIVO — renomear e APAGAR. Irreversível, e apagar uma pasta de
#                cliente leva com ela o histórico documental inteiro.
#
# `parceiro` (conta fantasma) e `cliente` (que tem o Portal) ficam de fora
# dos três. O isolamento por rede aplica-se a TODOS, incluindo admin/CEO —
# o que eles têm a mais é ver as pastas órfãs e ambíguas, para reconciliar.
# ────────────────────────────────────────────────────────────────────
FILE_VIEW_ROLES = [
    UserRole.ADMIN,
    UserRole.CEO,
    UserRole.DIRETOR,
    UserRole.ADMINISTRATIVO,
    UserRole.CONSULTOR,
    UserRole.INTERMEDIARIO,
    UserRole.INDEXACAO,
]

FILE_WRITE_ROLES = list(FILE_VIEW_ROLES)

FILE_OPS_ROLES = [
    UserRole.ADMIN,
    UserRole.CEO,
    UserRole.DIRETOR,
    UserRole.ADMINISTRATIVO,
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
    """Resolve e CONTÉM o caminho dentro da raiz do explorador.

    Antes fazia só `path.startswith(S3_EXPLORER_BASE_PATH)`, o que dava por
    bom `Documentação Clientes/../backups` (o `..` nunca era resolvido) e
    `Documentação Clientes_outro/` (prefixo de texto não é fronteira de
    segmento). Os backups da base de dados vivem no mesmo bucket.

    Levanta 400 para um caminho que saia da raiz.
    """
    return assert_dentro_da_raiz(path)


async def run_get_s3_folder_contents(folder_path: str, user: dict, request=None):
    """Lista conteúdo de uma pasta S3. Se folder_path vazio, lista a raiz do bucket (Documentação Clientes/)."""
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="S3 não configurado")

    # Se folder_path vazio, usar a pasta principal "Documentação Clientes/" como raiz
    prefix = _resolve_explorer_path(folder_path.strip())

    # A PAREDE (Épico 10, Passo 3). Duas coisas distintas:
    #   1. entrar numa pasta de outra rede → 404, como se não existisse;
    #   2. listar a raiz → devolve só o que é da rede de quem pede.
    scope, papel = await ambito_do_utilizador(request, user)
    await assert_pasta_no_ambito(prefix, scope, role=papel)

    try:
        list_prefix = prefix if prefix.endswith("/") else f"{prefix}/"

        # PAGINAÇÃO (Épico 10) — `list_objects_v2` devolve no MÁXIMO 1000
        # entradas por chamada. Havia aqui uma única chamada, sem
        # `ContinuationToken`: uma raiz com mais de mil pastas de cliente
        # ficava truncada **em silêncio**, e o utilizador não tinha como
        # distinguir "é só isto" de "o resto não coube". O `delete` e o
        # `rename` já paginavam; a listagem, que é a que toda a gente vê,
        # não. Com o filtro por rede do Passo 3 por cima, uma truncagem
        # invisível passaria a parecer isolamento a funcionar.
        subfolders = []
        files = []
        continuation_token = None
        paginas = 0

        while True:
            kwargs = {
                "Bucket": s3_service.bucket_name,
                "Prefix": list_prefix,
                "Delimiter": "/",
            }
            if continuation_token:
                kwargs["ContinuationToken"] = continuation_token

            response = s3_service.s3_client.list_objects_v2(**kwargs)
            paginas += 1

            for common_prefix in response.get("CommonPrefixes", []):
                subfolder_path = common_prefix.get("Prefix", "")
                parts = subfolder_path.rstrip("/").split("/")
                subfolder_name = parts[-1] if parts else ""
                if subfolder_name:
                    subfolders.append({
                        "path": subfolder_path.rstrip("/"),
                        "name": subfolder_name
                    })

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

            if not response.get("IsTruncated"):
                break
            continuation_token = response.get("NextContinuationToken")
            if not continuation_token:
                # Defesa contra um ciclo infinito se o S3 disser "truncado"
                # sem dar o cursor: melhor uma listagem incompleta com aviso
                # do que um pedido que nunca termina.
                logger.warning(
                    "[S3-EXPLORER] Listagem truncada sem NextContinuationToken "
                    "em '%s' após %d página(s)", list_prefix, paginas,
                )
                break

        # O filtro é uma leitura EM LOTE para a página inteira — nunca uma
        # query por pasta. É aqui que o desenho compra a performance.
        subfolders = await filtrar_subpastas(subfolders, scope, role=papel)

        return {
            "folder_path": folder_path,
            "subfolders": subfolders,
            "files": files,
            "total_items": len(subfolders) + len(files)
        }

    except Exception as e:
        logger.error(f"Erro ao listar conteúdo S3: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao listar pasta: {str(e)}")


async def run_s3_rename(data: S3RenameRequest, user: dict, request=None):
    """Renomeia um ficheiro ou pasta no S3 (copy + delete)."""
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="S3 não configurado")

    if not data.old_path or not data.new_name.strip():
        raise HTTPException(status_code=400, detail="Caminho original e novo nome são obrigatórios")

    # Recebia a chave CRUA: `old_path="backups/"` movia os backups da base
    # de dados. Contido antes de tocar no S3.
    old_path = _resolve_explorer_path(data.old_path)

    scope, papel = await ambito_do_utilizador(request, user)
    await assert_pasta_no_ambito(old_path, scope, role=papel)
    new_name = data.new_name.strip()
    if "/" in new_name:
        # O novo nome é um SEGMENTO, não um caminho: senão renomear era
        # outra forma de escrever uma chave arbitrária.
        raise HTTPException(status_code=400, detail="O nome não pode conter '/'")

    # Build the new path: replace the last segment with the new name
    path_parts = old_path.rstrip("/").split("/")
    path_parts[-1] = new_name
    new_path = "/".join(path_parts)

    # If it's a folder, we need to rename all objects with the old prefix
    if data.is_folder:
        try:
            old_prefix = old_path.rstrip("/") + "/"
            new_prefix = new_path.rstrip("/") + "/"

            # PAGINAÇÃO: uma só chamada movia no máximo 1000 objectos E
            # apagava-os, deixando o resto da pasta para trás sem que
            # ninguém desse por isso. O `delete` já paginava; o `rename`,
            # que é o que gera as ligações partidas, não.
            moved_count = 0
            continuation_token = None

            while True:
                kwargs = {"Bucket": s3_service.bucket_name, "Prefix": old_prefix}
                if continuation_token:
                    kwargs["ContinuationToken"] = continuation_token
                response = s3_service.s3_client.list_objects_v2(**kwargs)

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

                if not response.get("IsTruncated"):
                    break
                continuation_token = response.get("NextContinuationToken")
                if not continuation_token:
                    logger.warning(
                        "[S3-EXPLORER] Rename truncado sem cursor em '%s' — "
                        "%d objecto(s) movidos, o resto ficou por mover.",
                        old_prefix, moved_count,
                    )
                    break

            # PASSO 4 — mover a chave sem mover o mapeamento era apagar a
            # pasta do mundo: com o isolamento, um `s3_folder` a apontar
            # para o nome antigo torna-a órfã e invisível. Nunca bloqueia:
            # os objectos já se moveram.
            religacao = await religar_apos_rename(old_path, new_path)

            logger.info(f"Pasta renomeada: {old_path} -> {new_path} ({moved_count} objetos movidos)")
            return {
                "success": True,
                "old_path": old_path,
                "new_path": new_path,
                "objects_moved": moved_count,
                "relink": religacao,
            }

        except Exception as e:
            logger.error(f"Erro ao renomear pasta S3: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao renomear pasta: {str(e)}")
    else:
        # Rename a single file
        success = s3_service.rename_file(old_path, new_path)
        if success:
            # Um ficheiro solto também consta do `document_metadata` e dos
            # pedidos do Portal — renomeá-lo sem reapontar fazia-o
            # desaparecer do separador Documentos da ficha.
            religacao = await religar_apos_rename(old_path, new_path)
            return {
                "success": True,
                "old_path": old_path,
                "new_path": new_path,
                "relink": religacao,
            }
        else:
            raise HTTPException(status_code=500, detail="Erro ao renomear ficheiro")


async def run_s3_delete(data: S3DeleteRequest, user: dict, request=None):
    """Elimina um ficheiro ou pasta (e todo o seu conteúdo) do S3."""
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="S3 não configurado")

    if not data.path:
        raise HTTPException(status_code=400, detail="Caminho é obrigatório")

    # Recebia a chave CRUA: `path="backups/"` + `is_folder=True` apagava
    # todos os backups da base de dados, sem `../` nenhum.
    path = _resolve_explorer_path(data.path)

    scope, papel = await ambito_do_utilizador(request, user)
    await assert_pasta_no_ambito(path, scope, role=papel)

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


async def run_s3_create_folder(data: S3CreateFolderRequest, user: dict, request=None):
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

    scope, papel = await ambito_do_utilizador(request, user)
    await assert_pasta_no_ambito(folder_path, scope, role=papel)

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


async def run_s3_upload(file: UploadFile, folder_path: str, user: dict, request=None):
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

    scope, papel = await ambito_do_utilizador(request, user)
    await assert_pasta_no_ambito(base_path, scope, role=papel)
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


async def run_s3_download(path: str, user: dict, request=None):
    """Faz download de um ficheiro do S3 (streaming response)."""
    from services.s3_storage import s3_service

    if not s3_service.is_configured():
        raise HTTPException(status_code=503, detail="S3 não configurado")

    if not path:
        raise HTTPException(status_code=400, detail="Caminho é obrigatório")

    # Recebia a chave CRUA e fazia `get_object`: `backups/dump.gz` devolvia
    # a base de dados inteira em streaming.
    path = _resolve_explorer_path(path)

    scope, papel = await ambito_do_utilizador(request, user)
    await assert_pasta_no_ambito(path, scope, role=papel)

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
