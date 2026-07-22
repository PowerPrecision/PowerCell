"""
Rotas de Chat Interno — thin FastAPI stubs.

Logic in services/chat_*.py.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query, UploadFile, File, Form

from services.auth import get_current_user
from models.chat import (
    ChatMessageCreate, ChatMessageReaction, ChatMessageEdit,
    ChatGroupCreate, ChatGroupUpdate, ChatSearchQuery, TypingIndicator
)

from services.chat_conversations import run_get_conversations
from services.chat_messages import (
    run_get_messages,
    run_send_message,
    run_upload_message_with_attachment,
    run_react_to_message,
    run_edit_message,
    run_delete_message,
    run_search_messages,
)
from services.chat_groups import (
    run_create_group,
    run_get_groups,
    run_get_group,
    run_update_group,
    run_delete_group,
    run_leave_group,
)
from services.chat_presence import (
    run_send_typing_indicator,
    run_get_unread_count,
    run_get_online_users,
    run_get_chat_users,
)

router = APIRouter(prefix="/chat", tags=["Chat Interno"])


# ============= ENDPOINTS DE MENSAGENS =============

@router.get("/conversations")
async def get_conversations(
    user: dict = Depends(get_current_user)
):
    """
    Obter lista de conversas do utilizador.
    Inclui conversas diretas e grupos.
    """
    return await run_get_conversations(user)


@router.get("/messages/{conversation_id}")
async def get_messages(
    conversation_id: str,
    limit: int = Query(50, ge=1, le=200),
    before: Optional[str] = None,
    is_group: bool = Query(False),
    user: dict = Depends(get_current_user)
):
    """
    Obter mensagens de uma conversa.
    conversation_id pode ser user_id (direto) ou group_id (grupo).
    """
    return await run_get_messages(
        conversation_id, user, limit=limit, before=before, is_group=is_group
    )


@router.post("/messages")
async def send_message(
    message: ChatMessageCreate,
    user: dict = Depends(get_current_user)
):
    """
    Enviar uma nova mensagem (direta ou para grupo).
    """
    return await run_send_message(message, user)


@router.post("/messages/upload")
async def upload_message_with_attachment(
    receiver_id: Optional[str] = Form(None),
    group_id: Optional[str] = Form(None),
    content: Optional[str] = Form(""),
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user)
):
    """
    Enviar mensagem com anexo.
    """
    return await run_upload_message_with_attachment(
        user, file, receiver_id=receiver_id, group_id=group_id, content=content
    )


@router.post("/messages/react")
async def react_to_message(
    reaction: ChatMessageReaction,
    user: dict = Depends(get_current_user)
):
    """
    Adicionar ou remover reação a uma mensagem.
    """
    return await run_react_to_message(reaction, user)


@router.put("/messages/edit")
async def edit_message(
    edit_data: ChatMessageEdit,
    user: dict = Depends(get_current_user)
):
    """
    Editar uma mensagem (apenas próprio remetente).
    """
    return await run_edit_message(edit_data, user)


@router.delete("/messages/{message_id}")
async def delete_message(
    message_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Apagar uma mensagem (apenas próprio remetente).
    """
    return await run_delete_message(message_id, user)


# ============= ENDPOINTS DE GRUPOS =============

@router.post("/groups")
async def create_group(
    group_data: ChatGroupCreate,
    user: dict = Depends(get_current_user)
):
    """
    Criar um novo grupo de chat.
    """
    return await run_create_group(group_data, user)


@router.get("/groups")
async def get_groups(
    user: dict = Depends(get_current_user)
):
    """
    Obter grupos do utilizador.
    """
    return await run_get_groups(user)


@router.get("/groups/{group_id}")
async def get_group(
    group_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Obter detalhes de um grupo.
    """
    return await run_get_group(group_id, user)


@router.put("/groups/{group_id}")
async def update_group(
    group_id: str,
    update_data: ChatGroupUpdate,
    user: dict = Depends(get_current_user)
):
    """
    Atualizar grupo (nome, descrição, membros).
    """
    return await run_update_group(group_id, update_data, user)


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Apagar grupo (apenas criador).
    """
    return await run_delete_group(group_id, user)


@router.post("/groups/{group_id}/leave")
async def leave_group(
    group_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Sair de um grupo.
    """
    return await run_leave_group(group_id, user)


# ============= ENDPOINTS DE PESQUISA =============

@router.post("/search")
async def search_messages(
    search: ChatSearchQuery,
    user: dict = Depends(get_current_user)
):
    """
    Pesquisar mensagens.
    """
    return await run_search_messages(search, user)


# ============= ENDPOINTS DE TYPING =============

@router.post("/typing")
async def send_typing_indicator(
    typing: TypingIndicator,
    user: dict = Depends(get_current_user)
):
    """
    Enviar indicador de digitação.
    """
    return await run_send_typing_indicator(typing, user)


# ============= ENDPOINTS AUXILIARES =============

@router.get("/unread-count")
async def get_unread_count(user: dict = Depends(get_current_user)):
    """
    Obter contagem total de mensagens não lidas.
    """
    return await run_get_unread_count(user)


@router.get("/online-users")
async def get_online_users(user: dict = Depends(get_current_user)):
    """
    Obter lista de utilizadores online.
    """
    return await run_get_online_users(user)


@router.get("/users")
async def get_chat_users(
    search: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """
    Obter lista de utilizadores disponíveis para chat.
    """
    return await run_get_chat_users(user, search=search)
