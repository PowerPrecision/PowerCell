"""Staff (authenticated) handlers for temporary document links.

Extraído de `routes/temp_links.py`.

Uses `temp_link_api_*` prefix — do **not** overwrite existing
`services/temp_link_service.py` (core TempLinkService).
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import HTTPException

from database import db
from models.auth import UserRole
from models.temp_link import TempLinkType, TempLinkResponse
from services.temp_link_service import temp_link_service

logger = logging.getLogger(__name__)


async def run_create_temp_link(
    process_id: str,
    link_type: str,
    user: dict,
    expires_in_hours: int = 72,
    max_uses: int = 1,
    description: Optional[str] = None,
    file_paths: Optional[str] = None,
    notify_email: Optional[str] = "true",
    base_url: Optional[str] = None,
) -> TempLinkResponse:
    """Cria um link temporário para upload ou download de documentação."""
    logger.info(f"Criando link temporário: process_id={process_id}, link_type={link_type}, user={user.get('id')}")

    # Validar process_id
    if not process_id or process_id.strip() == "":
        logger.warning("process_id vazio ou inválido")
        raise HTTPException(
            status_code=400,
            detail="ID do processo é obrigatório."
        )

    try:
        link_type_enum = TempLinkType(link_type.lower())
    except ValueError:
        logger.warning(f"Tipo de link inválido: {link_type}")
        raise HTTPException(
            status_code=400,
            detail="Tipo de link inválido. Use 'upload' ou 'download'."
        )

    # Validar limites
    if expires_in_hours < 1 or expires_in_hours > 168:
        raise HTTPException(
            status_code=400,
            detail="Horas até expirar deve estar entre 1 e 168 (7 dias)."
        )

    if max_uses < 1 or max_uses > 10:
        raise HTTPException(
            status_code=400,
            detail="Máximo de utilizações deve estar entre 1 e 10."
        )

    # Parse file_paths se fornecido
    files_list = None
    if file_paths:
        if file_paths.startswith('['):
            import json
            try:
                files_list = json.loads(file_paths)
            except Exception:
                files_list = [p.strip() for p in file_paths.split(',') if p.strip()]
        else:
            files_list = [p.strip() for p in file_paths.split(',') if p.strip()]

    # Se é link de download, verificar que existem ficheiros
    if link_type_enum == TempLinkType.DOWNLOAD and not files_list:
        raise HTTPException(
            status_code=400,
            detail="Links de download requerem pelo menos um ficheiro."
        )

    # Parse notify_email: FormData envia "true"/"false" como strings,
    # FastAPI Form(bool) trata qualquer string não-vazia como True.
    notify_email_bool = notify_email.lower() in ("true", "1", "yes") if notify_email else True

    try:
        link = await temp_link_service.create_link(
            process_id=process_id,
            link_type=link_type_enum,
            user_id=user["id"],
            user_name=user.get("name", "Utilizador"),
            expires_in_hours=expires_in_hours,
            max_uses=max_uses,
            description=description,
            file_paths=files_list,
            notify_email=notify_email_bool,
            base_url=base_url
        )

        logger.info(f"Link temporário criado com sucesso: {link.id}")
        return link

    except ValueError as e:
        logger.warning(f"Erro de validação ao criar link: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Erro ao criar link temporário: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro ao criar link temporário: {str(e)}")


async def run_list_process_temp_links(process_id: str, user: dict) -> dict:
    """Lista todos os links temporários de um processo."""
    # Verificar acesso ao processo
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    # Verificar permissões
    user_role = user.get("role")
    if user_role not in [UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]:
        if process.get("assigned_consultor_id") != user.get("id") and \
           process.get("assigned_mediador_id") != user.get("id"):
            raise HTTPException(status_code=403, detail="Acesso não autorizado")

    links = await temp_link_service.list_process_links(process_id)

    return {
        "process_id": process_id,
        "client_name": process.get("client_name"),
        "links": links,
        "total": len(links)
    }


async def run_cancel_temp_link(link_id: str, user: dict) -> dict:
    """Cancela um link temporário."""
    # Verificar se o link existe
    link = await db.temp_links.find_one({"id": link_id})
    if not link:
        raise HTTPException(status_code=404, detail="Link não encontrado")

    # Verificar permissões
    if user.get("role") not in [UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO]:
        # Verificar se é o criador do link
        if link.get("created_by") != user.get("id"):
            raise HTTPException(
                status_code=403,
                detail="Só pode cancelar links que criou."
            )

    success = await temp_link_service.cancel_link(link_id, user["id"])

    if not success:
        raise HTTPException(
            status_code=400,
            detail="Não foi possível cancelar o link. Pode já ter sido usado ou expirado."
        )

    return {"success": True, "message": "Link cancelado com sucesso"}


async def run_delete_temp_link(link_id: str, user: dict) -> dict:
    """Elimina um link temporário (apenas admin)."""
    result = await db.temp_links.delete_one({"id": link_id})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Link não encontrado")

    return {"success": True, "message": "Link eliminado"}
