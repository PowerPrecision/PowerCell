"""Webmail listagem/stats/sync, contas e jobs.

Extraído de `routes/emails.py`.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import HTTPException, BackgroundTasks, Request

from database import db
from services.auth import get_effective_role
from services.email_enrich import enrich_email
from services.email_service import (
    test_email_connection,
    get_email_accounts,
    get_email_accounts_async,
    sync_webmail_emails,
)
from utils.input_sanitization import sanitize_string

logger = logging.getLogger(__name__)


def build_ucr_mailbox_filter(
    active_company_id: Optional[str],
    mailbox_email: Optional[str],
) -> Optional[dict]:
    """Filtro Mongo estrito para a mailbox do UCR activo (Pacote DN.2).

    Inclui emails com ``company_id`` da empresa activa **ou** cujo campo
    ``account`` é o endereço IMAP dessa UCR (legado, sem company_id).

    Não inclui emails globais / de outros perfis do mesmo utilizador.
    """
    clauses: List[dict] = []
    company_id = (active_company_id or "").strip()
    if company_id and company_id != "default":
        clauses.append({"company_id": company_id})
    mailbox = (mailbox_email or "").strip().lower()
    if mailbox:
        escaped = re.escape(mailbox)
        clauses.append({"account": {"$regex": f"^{escaped}$", "$options": "i"}})
    if not clauses:
        return None
    if len(clauses) == 1:
        return clauses[0]
    return {"$or": clauses}


async def resolve_ucr_mailbox_filter(
    request: Request,
    current_user: dict,
    box: Optional[str] = None,
    mailbox: Optional[str] = None,
) -> Optional[dict]:
    """Resolve o filtro UCR a partir do header X-Company-Id + config de email.

    Caixas partilhadas (geral / indexação) não são scoped por UCR pessoal.
    Se ``mailbox`` for dado (Pacote DN.4), filtra só essa conta IMAP.
    """
    if box in ("general", "shared_indexacao"):
        return None
    from services.auth import get_active_company_id_async
    from services.email_config_resolver import resolve_email_config_for_sync

    active_company_id = None
    try:
        active_company_id = await get_active_company_id_async(request, current_user)
    except Exception as exc:
        logger.warning("[Webmail] Falha a ler empresa activa: %s", exc)

    selected_mailbox = (mailbox or "").strip().lower() or None
    if selected_mailbox:
        # Conta pessoal específica — não misturar as outras do mesmo UCR
        return build_ucr_mailbox_filter(None, selected_mailbox)

    mailbox_email = None
    try:
        resolved = await resolve_email_config_for_sync(
            current_user.get("id"),
            active_role=get_effective_role(request, current_user),
            active_company_id=active_company_id,
        )
        if resolved:
            mailbox_email = (resolved.get("email_address") or "").strip() or None
    except Exception as exc:
        logger.warning("[Webmail] Falha a resolver mailbox UCR: %s", exc)

    return build_ucr_mailbox_filter(active_company_id, mailbox_email)


def _and_query(query: dict, extra: Optional[dict]) -> dict:
    """Combina um filtro extra sem esmagar um ``$or`` já presente."""
    if not extra:
        return query
    return {"$and": [query, extra]}


async def run_test_email_connections(current_user: dict, account: Optional[str] = None):
    """Testar ligação com as contas de email."""
    if current_user["role"] not in ["admin", "ceo"]:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    results = await test_email_connection(account)
    return results


async def run_get_configured_accounts(current_user: dict):
    """Listar contas de email configuradas."""
    accounts = get_email_accounts()
    return [
        {
            "name": a.name,
            "email": a.email,
            "imap_server": a.imap_server,
            "smtp_server": a.smtp_server
        }
        for a in accounts
    ]


async def run_webmail_list(request: Request, current_user: dict, folder: str = "inbox", page: int = 1, limit: int = 30, account: Optional[str] = None, search: Optional[str] = None, label: Optional[str] = None, custom_folder: Optional[str] = None, box: Optional[str] = None, mailbox: Optional[str] = None):
    """
    Listar emails no formato Webmail por pasta.
    
    ISOLAMENTO DE DADOS (Segurança):
    - admin/ceo/diretor: podem ver TODOS os emails (caixa geral)
    - outros roles (consultor, intermediario, etc.): só vêem emails onde são
      recipient (inbox) ou sender (sent). Filtragem por endereço de email.
    
    BOX PARAM (Tabbed webmail):
    - personal: emails do utilizador (synced_for_user ou created_by)
    - general: emails partilhados da caixa geral (shared_role=geral)
    - shared_indexacao: emails partilhados do role indexacao
    
    - inbox: emails recebidos (direction=received, não arquivados)
    - sent: emails enviados (direction=sent)
    - starred: emails marcados como estrela
    - trash: emails arquivados
    - drafts: emails com status=draft
    - custom: emails numa pasta personalizada (requer custom_folder param)
    """
    from models.auth import UserRole
    
    user_email = (current_user.get("email") or "").lower().strip()
    user_role = current_user.get("role", "")  # Used for permission checks (403)
    user_id = current_user.get("id", "")
    effective_role = get_effective_role(request, current_user)  # Used for data filtering
    can_see_all = effective_role in (UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR)
    
    logger.debug(f"User {current_user.get('email')} (id={user_id}, role={user_role}, effective_role={effective_role}) querying box={box} folder={folder} account={account}")
    
    # === BOX FILTER: permissões e isolamento por caixa ===
    if box == "general":
        # Blocked for consultor and indexacao
        if user_role in (UserRole.CONSULTOR, UserRole.INDEXACAO):
            raise HTTPException(
                status_code=403,
                detail=f"Acesso à caixa 'geral' não permitido para o role '{user_role}'."
            )
        logger.info(f"[Webmail List] box=general, user={user_email}, role={user_role}")
    elif box == "shared_indexacao":
        # Blocked for everyone except admin and indexacao
        if user_role not in (UserRole.ADMIN, UserRole.INDEXACAO):
            raise HTTPException(
                status_code=403,
                detail=f"Acesso à caixa 'shared_indexacao' não permitido para o role '{user_role}'."
            )
        logger.info(f"[Webmail List] box=shared_indexacao, user={user_email}, role={user_role}")
    elif box == "personal":
        logger.info(f"[Webmail List] box=personal, user={user_email}, role={user_role}")
    
    # === OBTER EMAIL DA CONTA IMAP SELECIONADA ===
    # Quando o user seleciona uma conta (ex: "power"), obtém o email dessa conta
    # para incluir no filtro — permite ver emails da caixa partilhada.
    account_email = None
    if account:
        try:
            accounts = await get_email_accounts_async()
            for acc in accounts:
                if acc.name == account:
                    account_email = (acc.email or "").lower().strip()
                    break
        except Exception:
            pass
    
    # === CONSTRUIR QUERY USANDO $and PARA EVITAR CONFLITOS ENTRE $or ===
    # Cada condição independente entra como um elemento separado do $and.
    # Isso evita que múltiplos $or se sobreponham.
    and_conditions = []
    
    # === MULTI-EMPRESA (Pacote DN.2 + DN.4): filtrar pela mailbox do UCR / conta ──
    # Estrito: só emails da empresa/conta IMAP do perfil escolhido no Header.
    ucr_filter = await resolve_ucr_mailbox_filter(
        request, current_user, box=box, mailbox=mailbox,
    )
    if ucr_filter:
        and_conditions.append(ucr_filter)
    
    # === ISOLAMENTO POR UTILIZADOR ===
    # Quando box é fornecido, ele substitui a lógica de isolamento padrão.
    # Quando box não é fornecido, mantém o comportamento actual.
    if box:
        # --- BOX-SPECIFIC ISOLATION ---
        if box == "personal":
            # Emails onde synced_for_user ou created_by corresponde ao utilizador
            # synced_for_user pode ser gravado como user_id OU como user.email,
            # por isso procuramos por ambos.
            ownership_filter = {
                "$or": [
                    {"created_by": user_id},
                    {"synced_for_user": user_id},
                    {"synced_for_user": user_email},
                ]
            }
            if folder == "inbox":
                # Quando box=personal, synced_for_user é o carimbo de propriedade.
                # Se synced_for_user corresponde ao user, NÃO filtramos adicionalmente
                # por to_emails — o email pode vir de uma conta IMAP com endereço diferente
                # do login do utilizador (ex: conta partilhada da empresa).
                # Apenas filter por to_emails quando o email NÃO tem synced_for_user.
                ownership_only = {
                    "$or": [
                        {"synced_for_user": user_id},
                        {"synced_for_user": user_email},
                    ]
                }
                ownership_with_to = {
                    "$and": [
                        {"$or": [
                            {"created_by": user_id},
                        ]},
                        {"$or": [
                            {"to_emails": {"$regex": re.escape(user_email), "$options": "i"}},
                        ]},
                    ]
                }
                if account_email and account_email != user_email:
                    ownership_with_to["$and"][1]["$or"].append(
                        {"to_emails": {"$regex": re.escape(account_email), "$options": "i"}}
                    )
                and_conditions.append({
                    "$or": [ownership_only, ownership_with_to]
                })
            elif folder == "sent":
                # Sent emails: synced_for_user match, OR created_by match, OR from_email match
                ownership_only = {
                    "$or": [
                        {"synced_for_user": user_id},
                        {"synced_for_user": user_email},
                        {"created_by": user_id},
                    ]
                }
                ownership_with_from = {
                    "$or": [
                        {"from_email": {"$regex": re.escape(user_email), "$options": "i"}},
                    ]
                }
                if account_email and account_email != user_email:
                    ownership_with_from["$or"].append(
                        {"from_email": {"$regex": re.escape(account_email), "$options": "i"}}
                    )
                and_conditions.append({
                    "$or": [ownership_only, ownership_with_from]
                })
            elif folder == "drafts":
                and_conditions.append({"created_by": user_id})
            elif folder in ("starred", "trash", "custom"):
                # For starred/trash/custom: show emails owned by user OR where user's email appears
                shared_or = [
                    {"from_email": {"$regex": re.escape(user_email), "$options": "i"}},
                    {"to_emails": {"$regex": re.escape(user_email), "$options": "i"}},
                    {"created_by": user_id},
                ]
                if account_email and account_email != user_email:
                    shared_or.append({"from_email": {"$regex": re.escape(account_email), "$options": "i"}})
                    shared_or.append({"to_emails": {"$regex": re.escape(account_email), "$options": "i"}})
                and_conditions.append({
                    "$or": [ownership_filter, {"$or": shared_or}]
                })
        elif box == "general":
            # Emails com shared_role=geral (caixa geral) OU is_general=True
            # (sync global via IMAP que marca is_general=True)
            and_conditions.append({"$or": [{"shared_role": "geral"}, {"is_general": True}]})
        elif box == "shared_indexacao":
            # Emails com shared_role=indexacao
            and_conditions.append({"shared_role": "indexacao"})
    elif not can_see_all and user_email:
        # --- DEFAULT ISOLATION (backward compatibility) ---
        # Regras estritas de isolamento para utilizadores não-admin:
        # 1. Emails devem pertencer ao utilizador (created_by OU synced_for_user)
        # 2. O endereço do utilizador deve aparecer no FROM/TO
        # 3. Emails legados sem user_id (antigo sync global "geral") são BLOQUEADOS
        # 4. EXCEÇÃO: Utilizadores de roles com email partilhado (ex: indexacao)
        #    podem ver emails sincronizados via Gmail API para esse role
        # NOTA: admin/ceo/diretor podem ver TUDO (can_see_all = True)
        user_id_isolation = current_user["id"]
        user_role_isolation = current_user.get("role", "")

        # Verificar se o utilizador pertence a um role com email partilhado
        shared_role_config = None
        if user_role_isolation:
            shared_role_config = await db.shared_role_email_configs.find_one(
                {"role": user_role_isolation, "is_configured": True},
                {"_id": 0, "role": 1},
            )

        # Filtro de pertença: o email deve ter sido criado por este utilizador
        # OU sincronizado para a sua conta pessoal
        # OU sincronizado para o role partilhado do utilizador
        ownership_filter = {
            "$or": [
                {"created_by": user_id_isolation},
                {"synced_for_user": user_id_isolation},
                {"synced_for_user": user_email},
            ]
        }

        # Se o utilizador tem um role com email partilhado, incluir emails do role
        if shared_role_config:
            ownership_filter["$or"].append({"shared_role": user_role_isolation})

        if folder == "inbox":
            inbox_or = [
                {"to_emails": {"$regex": re.escape(user_email), "$options": "i"}},
            ]
            # Se há conta selecionada, incluir também o email da conta partilhada
            if account_email and account_email != user_email:
                inbox_or.append({"to_emails": {"$regex": re.escape(account_email), "$options": "i"}})
            and_conditions.append({"$and": [ownership_filter, {"$or": inbox_or}]})
        elif folder == "sent":
            sent_or = [
                {"from_email": {"$regex": re.escape(user_email), "$options": "i"}},
                {"created_by": user_id_isolation},
            ]
            if account_email and account_email != user_email:
                sent_or.append({"from_email": {"$regex": re.escape(account_email), "$options": "i"}})
            and_conditions.append({"$or": [ownership_filter, {"$or": sent_or}]})
        elif folder == "drafts":
            # Rascunhos: criados pelo utilizador
            and_conditions.append({"created_by": user_id_isolation})
        elif folder in ("starred", "trash", "custom"):
            shared_or = [
                {"from_email": {"$regex": re.escape(user_email), "$options": "i"}},
                {"to_emails": {"$regex": re.escape(user_email), "$options": "i"}},
            ]
            if account_email and account_email != user_email:
                shared_or.append({"from_email": {"$regex": re.escape(account_email), "$options": "i"}})
                shared_or.append({"to_emails": {"$regex": re.escape(account_email), "$options": "i"}})
            and_conditions.append({"$and": [ownership_filter, {"$or": shared_or}]})
    
    # === FILTRO DE PASTA ===
    if folder == "inbox":
        and_conditions.append({"direction": "received"})
        and_conditions.append({"status": {"$ne": "draft"}})
        and_conditions.append({"is_archived": False})
    elif folder == "sent":
        and_conditions.append({"direction": "sent"})
        and_conditions.append({"status": {"$ne": "draft"}})
        and_conditions.append({"is_archived": False})
    elif folder == "starred":
        and_conditions.append({"is_starred": True})
    elif folder == "trash":
        and_conditions.append({"is_archived": True})
    elif folder == "drafts":
        and_conditions.append({"status": "draft"})
    elif folder == "custom":
        if not custom_folder:
            raise HTTPException(status_code=400, detail="ID da pasta não especificado")
        and_conditions.append({"folder_id": custom_folder})
    
    # === FILTRO POR CONTA IMAP ===
    # Quando box=personal, os emails sao isolados por synced_for_user e o campo
    # account guarda o endereco IMAP real do utilizador (ex: joao@empresa.pt).
    # O filtro account=power/precision so faz sentido para box=general/shared.
    if account and box != "personal":
        and_conditions.append({
            "$or": [
                {"account": account},
                {"account": {"$exists": False}},
            ]
        })
    
    # === FILTRO POR LABEL ===
    if label:
        and_conditions.append({"labels": label})
    
    # === PESQUISA TEXTUAL ===
    if search:
        search = sanitize_string(search, max_length=200)
        and_conditions.append({
            "$or": [
                {"subject": {"$regex": search, "$options": "i"}},
                {"body": {"$regex": search, "$options": "i"}},
                {"from_email": {"$regex": search, "$options": "i"}},
                {"to_emails": {"$regex": search, "$options": "i"}},
            ]
        })
    
    # Montar query final
    if len(and_conditions) == 1:
        query = and_conditions[0]
    elif and_conditions:
        query = {"$and": and_conditions}
    else:
        query = {}
    
    logger.debug(f"User {user_email} querying box {box} with filter {query}")
    
    skip = (page - 1) * limit
    total = await db.emails.count_documents(query)
    
    logger.debug(f"User {user_email} box={box} => total={total}")
    
    logger.info(f"[Webmail List] folder={folder}, account={account}, user={user_email}, total={total}")
    
    emails = await db.emails.find(
        query,
        {"_id": 0, "body": 0, "body_html": 0}
    ).sort("sent_at", -1).skip(skip).limit(limit).to_list(limit)

    # Serialize _id to string and ensure id is always a string for frontend keying
    emails_serialized = []
    for email in emails:
        email = dict(email)
        if "_id" in email and email["_id"]:
            email["_id"] = str(email["_id"])
        if "id" in email and email["id"]:
            email["id"] = str(email["id"])
        emails_serialized.append(email)
    emails = emails_serialized

    # Contar não lidos para a pasta inbox (com isolamento de utilizador)
    unread_count = 0
    if folder == "inbox":
        unread_and = [
            {"direction": "received"},
            {"status": {"$ne": "draft"}},
            {"is_read": False},
            {"is_archived": False},
        ]
        # Aplicar box filter ao unread_count
        if box == "personal":
            unread_and.append({
                "$or": [
                    {"created_by": user_id},
                    {"synced_for_user": user_id},
                    {"synced_for_user": user_email},
                ]
            })
        elif box == "general":
            unread_and.append({"$or": [{"shared_role": "geral"}, {"is_general": True}]})
        elif box == "shared_indexacao":
            unread_and.append({"shared_role": "indexacao"})
        elif not can_see_all and user_email:
            # Default isolation (backward compat)
            user_id_unread = current_user["id"]
            unread_and.append({
                "$and": [
                    {"$or": [
                        {"created_by": user_id_unread},
                        {"synced_for_user": user_id_unread},
                        {"synced_for_user": user_email},
                    ]},
                    {"$or": [
                        {"to_emails": {"$regex": re.escape(user_email), "$options": "i"}},
                    ]},
                ]
            })
        if account and box != "personal":
            unread_and.append({
                "$or": [
                    {"account": account},
                    {"account": {"$exists": False}},
                ]
            })
        unread_count = await db.emails.count_documents({"$and": unread_and})
    
    # Enriquecer emails com nome do processo/cliente
    enriched = []
    for email in emails:
        e = await enrich_email(email)
        e["id"] = str(e.get("id", ""))
        # Preview: primeira linha do body (buscar sem os campos excluídos acima)
        body_preview = email.get("body", "")[:120]
        if len(body_preview) == 120:
            body_preview += "..."
        e["preview"] = body_preview
        enriched.append(e)
    
    return {
        "emails": enriched,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit,
        "unread_count": unread_count,
        "folder": folder
    }


async def run_webmail_stats(
    current_user: dict,
    box: Optional[str] = None,
    request: Optional[Request] = None,
    mailbox: Optional[str] = None,
):
    """
    Estatísticas de Webmail para o utilizador logado.
    
    Retorna contadores de emails não lidos, enviados hoje e rascunhos pendentes.
    Respeita o isolamento de dados: consultor/intermediário só vê os seus.
    Admin/CEO/Diretor vêem a caixa geral.
    
    BOX PARAM: filtra as estatísticas por caixa (personal, general, shared_indexacao).
    Pacote DN.2: caixa pessoal filtrada pelo UCR activo (X-Company-Id).
    """
    from models.auth import UserRole
    
    user_email = (current_user.get("email") or "").lower().strip()
    user_role = current_user.get("role", "")
    user_id = current_user.get("id", "")
    can_see_all = user_role in (UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR)
    ucr_filter = None
    if request is not None:
        ucr_filter = await resolve_ucr_mailbox_filter(
            request, current_user, box=box, mailbox=mailbox,
        )
    
    # === BOX permission checks ===
    if box == "general":
        if user_role in (UserRole.CONSULTOR, UserRole.INDEXACAO):
            raise HTTPException(
                status_code=403,
                detail=f"Acesso à caixa 'geral' não permitido para o role '{user_role}'."
            )
        logger.info(f"[Webmail Stats] box=general, user={user_email}, role={user_role}")
    elif box == "shared_indexacao":
        if user_role not in (UserRole.ADMIN, UserRole.INDEXACAO):
            raise HTTPException(
                status_code=403,
                detail=f"Acesso à caixa 'shared_indexacao' não permitido para o role '{user_role}'."
            )
        logger.info(f"[Webmail Stats] box=shared_indexacao, user={user_email}, role={user_role}")
    
    # Base queries
    inbox_base = {
        "direction": "received",
        "status": {"$ne": "draft"},
        "is_archived": False,
    }
    sent_base = {
        "direction": "sent",
        "status": {"$ne": "draft"},
        "is_archived": False,
    }
    drafts_base = {
        "status": "draft",
        "is_archived": False,
    }
    
    # Apply box filter or default isolation
    if box == "personal":
        inbox_base["$or"] = [
            {"created_by": user_id},
            {"synced_for_user": user_id},
            {"synced_for_user": user_email},
        ]
        sent_base["$or"] = [
            {"created_by": user_id},
            {"synced_for_user": user_id},
            {"synced_for_user": user_email},
        ]
        drafts_base["created_by"] = user_id
    elif box == "general":
        inbox_base["$or"] = [{"shared_role": "geral"}, {"is_general": True}]
        sent_base["$or"] = [{"shared_role": "geral"}, {"is_general": True}]
        drafts_base["$or"] = [{"shared_role": "geral"}, {"is_general": True}]
    elif box == "shared_indexacao":
        inbox_base["shared_role"] = "indexacao"
        sent_base["shared_role"] = "indexacao"
        drafts_base["shared_role"] = "indexacao"
    elif not can_see_all and user_email:
        # Apply user isolation (same query as webmail list for consistency)
        user_isolation_or = [
            {"created_by": user_id},
            {"synced_for_user": user_id},
            {"synced_for_user": user_email},
        ]
        inbox_base["$or"] = user_isolation_or
        sent_base["$or"] = user_isolation_or
        drafts_base["created_by"] = user_id
    
    # Unread count
    unread_query = _and_query({**inbox_base, "is_read": False}, ucr_filter)
    unread_count = await db.emails.count_documents(unread_query)
    
    # Sent today
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    sent_today_query = _and_query({
        **sent_base,
        "sent_at": {"$gte": today_start}
    }, ucr_filter)
    sent_today_count = await db.emails.count_documents(sent_today_query)
    
    # Drafts count
    drafts_count = await db.emails.count_documents(_and_query(drafts_base, ucr_filter))
    
    # Full folder counts for sidebar badges
    inbox_count = await db.emails.count_documents(_and_query(inbox_base, ucr_filter))
    sent_count = await db.emails.count_documents(_and_query(sent_base, ucr_filter))
    
    # Starred count
    starred_base = {"is_starred": True, "is_archived": False}
    if box == "personal":
        starred_base["$or"] = [
            {"created_by": user_id},
            {"synced_for_user": user_id},
            {"synced_for_user": user_email},
        ]
    elif box == "general":
        starred_base["$or"] = [{"shared_role": "geral"}, {"is_general": True}]
    elif box == "shared_indexacao":
        starred_base["shared_role"] = "indexacao"
    elif not can_see_all and user_email:
        starred_base["$or"] = [
            {"created_by": user_id},
            {"synced_for_user": user_id},
            {"synced_for_user": user_email},
        ]
    starred_count = await db.emails.count_documents(_and_query(starred_base, ucr_filter))
    
    # Trash count
    trash_base = {"is_archived": True}
    if box == "personal":
        trash_base["$or"] = [
            {"created_by": user_id},
            {"synced_for_user": user_id},
            {"synced_for_user": user_email},
        ]
    elif box == "general":
        trash_base["$or"] = [{"shared_role": "geral"}, {"is_general": True}]
    elif box == "shared_indexacao":
        trash_base["shared_role"] = "indexacao"
    elif not can_see_all and user_email:
        trash_base["$or"] = [
            {"created_by": user_id},
            {"synced_for_user": user_id},
            {"synced_for_user": user_email},
        ]
    trash_count = await db.emails.count_documents(_and_query(trash_base, ucr_filter))
    
    return {
        "unread_count": unread_count,
        "sent_today_count": sent_today_count,
        "drafts_count": drafts_count,
        "folder_counts": {
            "inbox": inbox_count,
            "sent": sent_count,
            "starred": starred_count,
            "drafts": drafts_count,
            "trash": trash_count,
        }
    }


async def run_webmail_sync(current_user: dict, account: Optional[str] = None, days: int = 7):
    """
    Sincronizar emails do IMAP para o Webmail (background).
    
    ISOLAMENTO DE DADOS:
    - admin/ceo/diretor: podem sincronizar contas globais (power, precision)
    - outros roles: BLOQUEADOS — devem usar POST /webmail/sync-user
      para sincronizar a sua caixa pessoal.
    
    Esta rota faz pull de TODOS os emails recentes das pastas INBOX e Enviados
    das contas GLOBAIS configuradas. Para isolamento, utilizadores comuns
    devem usar o endpoint /webmail/sync-user.
    """
    from models.auth import UserRole
    from services.background_jobs import BackgroundJobService, JobType
    
    # Bloquear sync global para utilizadores não-admin
    user_role = current_user.get("role", "")
    if user_role not in (UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR):
        raise HTTPException(
            status_code=403,
            detail="Sincronização global apenas disponível para administradores. Use /webmail/sync-user para sincronizar o seu email pessoal."
        )
    
    # Verificar contas configuradas primeiro
    accounts = await get_email_accounts_async()
    if not accounts:
        return {
            "success": False,
            "error": "Nenhuma conta de email configurada. Vá a Configurações > Email e configure pelo menos uma conta IMAP.",
            "accounts_found": 0
        }
    
    # Se account foi especificado, verificar se existe
    if account:
        matched = [a for a in accounts if a.name == account]
        if not matched:
            available = [a.name for a in accounts]
            return {
                "success": False,
                "error": f"Conta '{account}' não encontrada. Contas disponíveis: {available}",
                "accounts_found": len(accounts),
                "available_accounts": available
            }
    
    # Criar job em background
    job_service = BackgroundJobService()
    job_id = await job_service.create_job(
        job_type=JobType.EMAIL_SYNC,
        user_id=current_user["id"],
        user_email=current_user.get("email", ""),
        metadata={"account": account, "days": days}
    )
    
    # Executar sincronização em background
    async def run_sync():
        try:
            await job_service.update_progress(job_id, 0, 1, "A sincronizar emails...")
            result = await sync_webmail_emails(
                account_name=account,
                days=days,
                max_emails=150
            )
            # Extract summary
            synced = result.get("emails_synced", result.get("synced", 0))
            total = result.get("emails_found", result.get("total", 0))
            msg = f"Sincronização concluída: {synced} emails"
            if result.get("success") == False:
                await job_service.fail_job(job_id, result.get("error", "Erro na sincronização"))
            else:
                await job_service.complete_job(job_id, {"synced": synced, "total": total, "details": result})
        except Exception as e:
            logger.error(f"Erro na sincronização webmail: {e}", exc_info=True)
            await job_service.fail_job(job_id, str(e))
    
    asyncio.create_task(run_sync())
    
    return {
        "success": True,
        "message": "Sincronização iniciada em background",
        "job_id": job_id,
        "status": "started"
    }


async def run_webmail_sync_user(
    request: Request,
    current_user: dict,
    account_id: Optional[str] = None,
    mailbox: Optional[str] = None,
):
    """
    Sincronizar emails usando as credenciais do utilizador logado.
    
    Para roles com email partilhado (indexacao, suporte), usa as credenciais
    da conta partilhada do departamento em vez das credenciais pessoais.
    """
    from services.background_jobs import BackgroundJobService, JobType
    
    user_id = current_user["id"]
    user_role = get_effective_role(request, current_user)
    
    # === INDEXACAO / SUPORTE: usar conta partilhada do departamento ===
    if user_role in ("indexacao", "suporte"):
        # Tenta shared_role_email_configs primeiro, depois fallback para system_webmail (Bloco C)
        shared_config = await db.shared_role_email_configs.find_one(
            {"role": user_role, "is_configured": True},
            {"_id": 0}
        )
        if not shared_config:
            # Fallback: verificar system_webmail das Integrações (Bloco C)
            from services.system_config import get_system_config
            sys_config = await get_system_config()
            sys_webmail = sys_config.system_webmail
            if not (sys_webmail.imap_host and sys_webmail.email_user and sys_webmail.app_password):
                return {
                    "success": False,
                    "error": f"Configuração de email partilhada para {user_role} não encontrada. Configure em Definições > Integrações (Bloco C) ou contacte o administrador."
                }
        
        # Criar job em background com sync partilhado
        job_service = BackgroundJobService()
        job_id = await job_service.create_job(
            job_type=JobType.EMAIL_SYNC,
            user_id=user_id,
            user_email=current_user.get("email", ""),
            metadata={"sync_type": "shared_role", "role": user_role}
        )
        
        async def run_shared_sync():
            try:
                from services.email_service import sync_shared_role_emails
                await job_service.update_progress(job_id, 0, 1, f"A sincronizar emails partilhados ({user_role})...")
                result = await sync_shared_role_emails(user_role)
                if result.get("success") == False:
                    await job_service.fail_job(job_id, result.get("error", "Erro na sincronização"))
                else:
                    synced = result.get("total_synced", 0)
                    await job_service.complete_job(job_id, {"synced": synced, "details": result})
            except Exception as e:
                logger.error(f"Erro na sincronização shared role emails: {e}", exc_info=True)
                await job_service.fail_job(job_id, str(e))
        
        asyncio.create_task(run_shared_sync())
        
        return {
            "success": True,
            "message": f"Sincronização de email partilhado ({user_role}) iniciada em background",
            "job_id": job_id,
        }
    
    # === UTILIZADORES NORMAIS: usar credenciais pessoais ===
    # Usar o resolver que suporta config individual, company e system (herança)
    active_role = user_role  # já obtido acima via get_effective_role
    from services.email_config_resolver import resolve_email_config_for_sync
    from services.auth import get_active_company_id_async
    active_company_id = await get_active_company_id_async(request, current_user)
    resolved = await resolve_email_config_for_sync(
        user_id,
        active_role=active_role,
        active_company_id=active_company_id,
        account_id=account_id,
    )
    if mailbox and resolved and (resolved.get("email_address") or "").lower() != mailbox.strip().lower():
        from services.user_email_config_service import list_company_email_configs
        docs = await list_company_email_configs(user_id, active_company_id or "default")
        match = next(
            (d for d in docs if (d.get("email_address") or "").lower() == mailbox.strip().lower()),
            None,
        )
        if match:
            resolved = await resolve_email_config_for_sync(
                user_id,
                active_role=active_role,
                active_company_id=active_company_id,
                account_id=match.get("id"),
            )
    
    if not resolved:
        return {
            "success": False,
            "error": "Configuração de email não encontrada. Vá ao seu Perfil > Configuração de Webmail para configurar."
        }
    
    # Criar job em background
    job_service = BackgroundJobService()
    job_id = await job_service.create_job(
        job_type=JobType.EMAIL_SYNC,
        user_id=user_id,
        user_email=current_user.get("email", ""),
        metadata={"sync_type": "user_personal", "company_id": active_company_id}
    )
    
    async def run_user_sync():
        try:
            from services.email_service import sync_user_emails
            await job_service.update_progress(job_id, 0, 1, "A sincronizar emails pessoais...")
            # Passar o `resolved` (config já resolvida pelo resolver canónico) para
            # que sync_user_emails NÃO volte a ler user.email_config embebido (que
            # para configs multi-empresa é aninhado e fazia a sync falhar com
            # "Configuração de email não ativa").
            result = await sync_user_emails(user_id, resolved_config=resolved)
            if result.get("success") == False:
                await job_service.fail_job(job_id, result.get("error", "Erro na sincronização"))
            else:
                synced = result.get("total_synced", 0)
                await job_service.complete_job(job_id, {"synced": synced, "details": result})
        except Exception as e:
            logger.error(f"Erro na sincronização user emails: {e}", exc_info=True)
            await job_service.fail_job(job_id, str(e))
    
    asyncio.create_task(run_user_sync())
    
    return {
        "success": True,
        "message": "Sincronização pessoal iniciada em background",
        "job_id": job_id,
    }


async def run_get_email_job_status(job_id: str, current_user: dict):
    """
    Obtém o estado de um job de sincronização de emails.
    
    Permite ao frontend fazer polling para saber quando a sincronização
    terminou e quantos emails foram sincronizados.
    """
    from services.background_jobs import BackgroundJobService
    
    job = await BackgroundJobService().get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    
    # Verificar permissão: apenas o dono do job ou admin podem ver
    if job.get("user_id") != current_user.get("id") and current_user.get("role") not in ["admin", "ceo", "diretor"]:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    return job


