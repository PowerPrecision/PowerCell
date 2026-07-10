"""
====================================================================
SERVIÇO DE ATRIBUIÇÃO DE PROCESSOS - CREDITOIMO
====================================================================
Lógica de negócio para atribuição de consultores e intermediários
a processos, incluindo auto-atribuição inteligente de indexadores
com limite de carga e fila de espera.
====================================================================
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple, Dict, List

from database import db

logger = logging.getLogger(__name__)

# ==== CONSTANTES DE ATRIBUIÇÃO ====

# Número máximo de processos ativos que um indexador pode ter
MAX_ACTIVE_PROCESSES_PER_INDEXER = 15

# Status que NÃO contam como processos ativos para o indexador
# (processos concluídos, arquivados, perdidos ou desistidos)
INDEXER_INACTIVE_STATUSES = {
    "concluidos",
    "arquivo",
    "perdido",
    "desistencias",
    "eliminados",
    "pre_registo",  # pré-registo não conta como carga real do indexador
}


# ==== VALIDAÇÃO DE ATRIBUIÇÃO ====

async def validate_assignment_user(user_id: str) -> Tuple[bool, Optional[dict], str]:
    """
    Valida se o utilizador existe e pode ser atribuído.
    
    Args:
        user_id: ID do utilizador a validar
        
    Returns:
        Tuple com (válido, dados do utilizador, mensagem de erro)
    """
    if not user_id:
        return False, None, "ID do utilizador não fornecido"
    
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    
    if not user:
        return False, None, f"Utilizador {user_id} não encontrado"
    
    if not user.get("is_active", True):
        return False, None, f"Utilizador {user.get('name', user_id)} está inactivo"
    
    return True, user, ""


# ==== ATRIBUIÇÃO PRINCIPAL ====

async def assign_consultant_to_process(
    process_id: str,
    consultant_id: str,
    assigning_user: dict
) -> Tuple[bool, dict, str]:
    """
    Atribui um consultor a um processo.
    
    Args:
        process_id: ID do processo
        consultant_id: ID do consultor a atribuir
        assigning_user: Utilizador que está a fazer a atribuição
        
    Returns:
        Tuple com (sucesso, dados atualizados, mensagem)
    """
    # Validar consultor
    valid, consultant, error = await validate_assignment_user(consultant_id)
    if not valid:
        return False, {}, error
    
    # Actualizar processo
    update_data = {
        "consultant_id": consultant_id,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    result = await db.processes.update_one(
        {"id": process_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        return False, {}, "Processo não encontrado ou não atualizado"
    
    return True, {
        "consultant_id": consultant_id,
        "consultant_name": consultant.get("name", "")
    }, f"Consultor {consultant.get('name')} atribuído com sucesso"


async def assign_mediador_to_process(
    process_id: str,
    mediador_id: str,
    assigning_user: dict
) -> Tuple[bool, dict, str]:
    """
    Atribui um mediador/intermediário a um processo.
    
    Args:
        process_id: ID do processo
        mediador_id: ID do mediador a atribuir
        assigning_user: Utilizador que está a fazer a atribuição
        
    Returns:
        Tuple com (sucesso, dados atualizados, mensagem)
    """
    # Validar mediador
    valid, mediador, error = await validate_assignment_user(mediador_id)
    if not valid:
        return False, {}, error
    
    # Actualizar processo
    update_data = {
        "mediador_id": mediador_id,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    result = await db.processes.update_one(
        {"id": process_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        return False, {}, "Processo não encontrado ou não atualizado"
    
    return True, {
        "mediador_id": mediador_id,
        "mediador_name": mediador.get("name", "")
    }, f"Mediador {mediador.get('name')} atribuído com sucesso"


async def assign_indexacao_to_process(
    process_id: str,
    indexacao_id: str,
    assigning_user: dict
) -> Tuple[bool, dict, str]:
    """
    Atribui um utilizador de indexação a um processo.
    
    Args:
        process_id: ID do processo
        indexacao_id: ID do utilizador de indexação a atribuir
        assigning_user: Utilizador que está a fazer a atribuição
        
    Returns:
        Tuple com (sucesso, dados atualizados, mensagem)
    """
    # Validar utilizador de indexação
    valid, indexacao_user, error = await validate_assignment_user(indexacao_id)
    if not valid:
        return False, {}, error
    
    # Actualizar processo
    update_data = {
        "assigned_indexacao_id": indexacao_id,
        "indexacao_name": indexacao_user.get("name", ""),
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    result = await db.processes.update_one(
        {"id": process_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        return False, {}, "Processo não encontrado ou não atualizado"
    
    return True, {
        "assigned_indexacao_id": indexacao_id,
        "indexacao_name": indexacao_user.get("name", "")
    }, f"Indexação {indexacao_user.get('name')} atribuído com sucesso"


async def assign_both_to_process(
    process_id: str,
    consultant_id: Optional[str],
    mediador_id: Optional[str],
    assigning_user: dict
) -> Tuple[bool, dict, str]:
    """
    Atribui consultor e/ou mediador a um processo.
    
    Args:
        process_id: ID do processo
        consultant_id: ID do consultor (opcional)
        mediador_id: ID do mediador (opcional)
        assigning_user: Utilizador que está a fazer a atribuição
        
    Returns:
        Tuple com (sucesso, dados atualizados, mensagem)
    """
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    messages = []
    result_data = {}
    
    # Validar e preparar consultor
    if consultant_id:
        valid, consultant, error = await validate_assignment_user(consultant_id)
        if not valid:
            return False, {}, f"Consultor: {error}"
        update_data["consultant_id"] = consultant_id
        result_data["consultant_id"] = consultant_id
        result_data["consultant_name"] = consultant.get("name", "")
        messages.append(f"Consultor: {consultant.get('name')}")
    
    # Validar e preparar mediador
    if mediador_id:
        valid, mediador, error = await validate_assignment_user(mediador_id)
        if not valid:
            return False, {}, f"Mediador: {error}"
        update_data["mediador_id"] = mediador_id
        result_data["mediador_id"] = mediador_id
        result_data["mediador_name"] = mediador.get("name", "")
        messages.append(f"Mediador: {mediador.get('name')}")
    
    if len(update_data) == 1:  # Apenas updated_at
        return False, {}, "Nenhuma atribuição especificada"
    
    # Actualizar processo
    result = await db.processes.update_one(
        {"id": process_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        return False, {}, "Processo não encontrado ou não atualizado"
    
    return True, result_data, f"Atribuído: {', '.join(messages)}"


# ==== AUTO-ATRIBUIÇÃO ====

async def assign_self_to_process(
    process_id: str,
    user: dict,
    role_type: str = "consultant"
) -> Tuple[bool, dict, str]:
    """
    Atribui o utilizador actual a um processo.
    
    Args:
        process_id: ID do processo
        user: Utilizador actual
        role_type: Tipo de papel ("consultant" ou "mediador")
        
    Returns:
        Tuple com (sucesso, dados atualizados, mensagem)
    """
    user_id = user.get("id")
    user_name = user.get("name", "")
    
    if role_type == "consultant":
        field = "consultant_id"
    else:
        field = "mediador_id"
    
    update_data = {
        field: user_id,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    result = await db.processes.update_one(
        {"id": process_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        return False, {}, "Processo não encontrado ou não atualizado"
    
    return True, {field: user_id, f"{role_type}_name": user_name}, f"Auto-atribuição como {role_type}: {user_name}"


async def unassign_self_from_process(
    process_id: str,
    user: dict
) -> Tuple[bool, dict, str]:
    """
    Remove a auto-atribuição do utilizador de um processo.
    
    Args:
        process_id: ID do processo
        user: Utilizador actual
        
    Returns:
        Tuple com (sucesso, dados atualizados, mensagem)
    """
    user_id = user.get("id")
    
    # Verificar se o utilizador está atribuído
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        return False, {}, "Processo não encontrado"
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    removed_from = []
    
    if process.get("consultant_id") == user_id:
        update_data["consultant_id"] = None
        removed_from.append("consultor")
    
    if process.get("mediador_id") == user_id:
        update_data["mediador_id"] = None
        removed_from.append("mediador")
    
    if len(update_data) == 1:  # Apenas updated_at
        return False, {}, "Não está atribuído a este processo"
    
    result = await db.processes.update_one(
        {"id": process_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        return False, {}, "Erro ao remover atribuição"
    
    return True, update_data, f"Removido de: {', '.join(removed_from)}"


# ==== LISTA DE UTILIZADORES PARA ATRIBUIÇÃO ====

async def get_users_for_assignment(role_filter: Optional[str] = None) -> list:
    """
    Obtém lista de utilizadores disponíveis para atribuição.
    
    Args:
        role_filter: Filtrar por papel específico (opcional)
        
    Returns:
        Lista de utilizadores
    """
    from services.role_query import build_deep_role_query
    query = {"is_active": True}
    
    if role_filter:
        query = build_deep_role_query(query, role=role_filter)
    
    cursor = db.users.find(
        query,
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}
    ).sort("name", 1)
    
    return await cursor.to_list(length=100)


# ==== AUTO-ATRIBUIÇÃO INTELIGENTE DE INDEXADORES ====

async def _count_active_processes_for_indexer(indexer_id: str) -> int:
    """
    Conta quantos processos ATIVOS um indexador tem atualmente na sua posse.

    Um processo conta como "ativo" para o indexador se:
    - Está atribuído a ele (assigned_indexacao_id == indexer_id)
    - O seu status NÃO está na lista de estados inativos (concluído, arquivo, etc.)
    - A sua indexação NÃO está concluída (is_indexed != true)

    Isto significa que quando o indexador marca is_indexed=true, esse processo
    deixa de contar para a sua carga ativa, libertando vaga na sua lista.

    Args:
        indexer_id: ID do utilizador indexador

    Returns:
        Número de processos ativos atribuídos ao indexador
    """
    active_query = {
        "assigned_indexacao_id": indexer_id,
        "status": {"$nin": list(INDEXER_INACTIVE_STATUSES)},
        "$or": [
            {"is_indexed": {"$ne": True}},
            {"is_indexed": {"$exists": False}},
        ],
    }

    count = await db.processes.count_documents(active_query)
    return count


async def assign_to_indexer(process_id: str, update_status: bool = True) -> Tuple[bool, dict, str]:
    """
    Atribui automaticamente um processo ao indexador com menor carga.

    Algoritmo de distribuição:
    1. Encontra todos os utilizadores com o role 'indexacao' (incluindo additional_roles).
    2. Para cada indexador, conta os processos ativos (status não terminal).
    3. Filtra os indexadores com menos de MAX_ACTIVE_PROCESSES_PER_INDEXER processos.
    4. Ordena pelo número de processos ativos (ascendente) — distribui a quem tem menos.
    5. Se houver indexador disponível:
       - Atribui o processo (assigned_indexacao_id + indexacao_name).
       - Altera o status do processo para 'fase_documental' (pronto para indexação).
       - Envia email de notificação ao indexador.
       - Envia notificação em tempo real (in-app).
    6. Se TODOS os indexadores estiverem no limite:
       - O processo NÃO é atribuído a ninguém.
       - O status muda para 'fila_espera' (aguarda vaga).

    PACOTE DB — parâmetro `update_status`:
    - Quando True (default, retrocompatível): o status é atualizado para
      'fase_documental' (indexador disponível) ou 'fila_espera' (sem vaga).
    - Quando False: o status do processo NÃO é alterado em NENHUM cenário.
      O indexador é atribuído se disponível (cenário 5), mas o processo
      mantém o status atual (ex.: 1ª fase real do Kanban definida na criação).
      Isto evita "fases fantasma" hardcoded (fila_espera/fase_documental)
      quando o chamador já definiu o status correto (ex.: criação manual
      no CRM, auto-avanço do Portal).

    Args:
        process_id: ID do processo a atribuir

    Returns:
        Tuple com (sucesso, dados atualizados, mensagem)
    """
    from services.role_query import build_deep_role_query
    from services.notification_service import send_notification_with_preference_check
    from services.realtime_notifications import send_realtime_notification
    from services.history import log_history

    # ── 1. Obter o processo ──
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        return False, {}, f"Processo {process_id} não encontrado"

    # Evitar re-atribuição se já tem indexador
    if process.get("assigned_indexacao_id"):
        existing_name = process.get("indexacao_name", "desconhecido")
        return False, {}, (
            f"Processo já atribuído ao indexador: {existing_name}"
        )

    # ── 2. Encontrar todos os indexadores ativos ──
    query = build_deep_role_query({"is_active": True}, role="indexacao")
    indexers_cursor = db.users.find(
        query,
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "additional_roles": 1}
    )
    indexers = await indexers_cursor.to_list(length=100)

    if not indexers:
        # Sem indexadores no sistema
        # PACOTE DB — se update_status=False, NÃO forçar fila_espera.
        # O processo mantém o status atual (ex.: 1ª fase real do Kanban).
        if not update_status:
            logger.warning(
                f"[ASSIGN-INDEXER] Nenhum indexador encontrado no sistema. "
                f"Processo {process_id} mantém status atual (update_status=False)."
            )
            return True, {
                "status": process.get("status"),
                "assigned": False,
                "reason": "no_indexers",
            }, "Nenhum indexador disponível no sistema — processo mantém status atual"
        now = datetime.now(timezone.utc).isoformat()
        update_data = {
            "status": "fila_espera",
            "updated_at": now,
        }
        await db.processes.update_one(
            {"id": process_id},
            {"$set": update_data}
        )
        logger.warning(
            f"[ASSIGN-INDEXER] Nenhum indexador encontrado no sistema. "
            f"Processo {process_id} colocado na fila de espera."
        )
        return True, {
            "status": "fila_espera",
            "assigned": False,
            "reason": "no_indexers",
        }, "Nenhum indexador disponível no sistema — processo colocado na fila de espera"

    # ── 3. Contar processos ativos por indexador ──
    indexer_loads: List[Dict] = []
    for indexer in indexers:
        active_count = await _count_active_processes_for_indexer(indexer["id"])
        indexer_loads.append({
            "id": indexer["id"],
            "name": indexer.get("name", ""),
            "email": indexer.get("email", ""),
            "active_count": active_count,
        })
        logger.debug(
            f"[ASSIGN-INDEXER] Indexador {indexer.get('name')} "
            f"({indexer['id'][:8]}): {active_count} processos ativos"
        )

    # ── 4. Filtrar indexadores disponíveis (menos de 15 processos) ──
    available_indexers = [
        ix for ix in indexer_loads
        if ix["active_count"] < MAX_ACTIVE_PROCESSES_PER_INDEXER
    ]

    # ── 5. Se não há indexadores disponíveis → FILA DE ESPERA ──
    if not available_indexers:
        # PACOTE DB — se update_status=False, NÃO forçar fila_espera.
        # O processo mantém o status atual; fica apenas sem indexador atribuído.
        if not update_status:
            logger.info(
                f"[ASSIGN-INDEXER] Todos os {len(indexers)} indexadores estão no limite "
                f"({MAX_ACTIVE_PROCESSES_PER_INDEXER} processos). "
                f"Processo {process_id} mantém status atual (update_status=False)."
            )
            return True, {
                "status": process.get("status"),
                "assigned": False,
                "reason": "all_indexers_full",
                "indexers_checked": len(indexers),
            }, (
                f"Todos os {len(indexers)} indexadores estão no limite de "
                f"{MAX_ACTIVE_PROCESSES_PER_INDEXER} processos — processo mantém status atual"
            )
        now = datetime.now(timezone.utc).isoformat()
        update_data = {
            "status": "fila_espera",
            "updated_at": now,
        }
        result = await db.processes.update_one(
            {"id": process_id},
            {"$set": update_data}
        )

        if result.modified_count == 0:
            return False, {}, "Erro ao atualizar processo para fila de espera"

        # Registar no histórico (utilizador sistema)
        system_user = {"id": "system", "name": "Sistema", "role": "admin"}
        await log_history(
            process_id=process_id,
            user=system_user,
            action="Processo colocado na fila de espera — todos os indexadores no limite",
            field="status",
            old_value=process.get("status", ""),
            new_value="fila_espera",
        )

        logger.info(
            f"[ASSIGN-INDEXER] Todos os {len(indexers)} indexadores estão no limite "
            f"({MAX_ACTIVE_PROCESSES_PER_INDEXER} processos). "
            f"Processo {process_id} colocado na fila de espera."
        )

        return True, {
            "status": "fila_espera",
            "assigned": False,
            "reason": "all_indexers_full",
            "indexers_checked": len(indexers),
        }, (
            f"Todos os {len(indexers)} indexadores estão no limite de "
            f"{MAX_ACTIVE_PROCESSES_PER_INDEXER} processos — processo na fila de espera"
        )

    # ── 6. Ordenar por carga (ascendente) e escolher o menos carregado ──
    available_indexers.sort(key=lambda ix: ix["active_count"])
    chosen = available_indexers[0]

    logger.info(
        f"[ASSIGN-INDEXER] Indexador escolhido: {chosen['name']} "
        f"com {chosen['active_count']} processos ativos "
        f"(de {len(available_indexers)} disponíveis)"
    )

    # ── 7. Atribuir processo ao indexador ──
    now = datetime.now(timezone.utc).isoformat()
    # PACOTE DB — se update_status=False, NÃO forçar fase_documental.
    # O indexador é atribuído mas o processo mantém o status atual.
    update_data = {
        "assigned_indexacao_id": chosen["id"],
        "indexacao_name": chosen["name"],
        "updated_at": now,
    }
    if update_status:
        update_data["status"] = "fase_documental"

    result = await db.processes.update_one(
        {"id": process_id},
        {"$set": update_data}
    )

    if result.modified_count == 0:
        return False, {}, "Erro ao atribuir processo ao indexador"

    # Registar no histórico (utilizador sistema)
    system_user = {"id": "system", "name": "Sistema", "role": "admin"}
    await log_history(
        process_id=process_id,
        user=system_user,
        action=f"Auto-atribuição ao indexador {chosen['name']}",
        field="assigned_indexacao_id",
        old_value=None,
        new_value=chosen["name"],
    )

    # ── 8. Enviar notificações (email + in-app) ──
    client_name = process.get("client_name", "Cliente")
    process_number = process.get("process_number") or process.get("process_ref") or process_id[:8]

    # Email de notificação
    try:
        from services.email import get_base_template
        import os

        frontend_url = os.environ.get("FRONTEND_URL", "")
        process_link = f"{frontend_url}/processo/{process_id}" if frontend_url else ""

        subject = f"Novo Processo Atribuído: {client_name}"
        body_text = (
            f"Olá {chosen['name']},\n\n"
            f"Foi-lhe atribuído automaticamente um novo processo como Indexação.\n\n"
            f"Cliente: {client_name}\n"
            f"Processo: {process_number}\n"
        )
        if process_link:
            body_text += f"\nAceda ao processo em: {process_link}\n"

        # Corpo em HTML
        link_html = ""
        if process_link:
            link_html = f"""
            <tr>
                <td style="padding: 15px 30px; text-align: center;">
                    <a href="{process_link}" style="
                        display: inline-block;
                        background: linear-gradient(135deg, #1e3a5f, #2d5a87);
                        color: #ffffff;
                        padding: 12px 30px;
                        border-radius: 8px;
                        text-decoration: none;
                        font-weight: 600;
                        font-size: 14px;
                    ">Abrir Processo no CRM</a>
                </td>
            </tr>"""

        content_html = f"""
        <table width="100%" cellpadding="0" cellspacing="0" style="padding: 20px 0;">
            <tr>
                <td style="padding: 10px 30px;">
                    <p style="margin: 0 0 10px 0; font-size: 16px;">Olá <strong>{chosen['name']}</strong>,</p>
                    <p style="margin: 0 0 20px 0; font-size: 15px; color: #555;">
                        Foi-lhe atribuído automaticamente um novo processo como <strong>Indexação</strong>.
                    </p>
                </td>
            </tr>
            <tr>
                <td style="padding: 15px 30px; background: #f8f9fa; border-radius: 8px;">
                    <table width="100%" cellpadding="0" cellspacing="0">
                        <tr>
                            <td style="padding: 8px 0; font-size: 14px; color: #666; width: 120px;"><strong>Cliente:</strong></td>
                            <td style="padding: 8px 0; font-size: 14px;">{client_name}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; font-size: 14px; color: #666;"><strong>Processo:</strong></td>
                            <td style="padding: 8px 0; font-size: 14px;">{process_number}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px 0; font-size: 14px; color: #666;"><strong>Processos Ativos:</strong></td>
                            <td style="padding: 8px 0; font-size: 14px;">{chosen['active_count'] + 1} / {MAX_ACTIVE_PROCESSES_PER_INDEXER}</td>
                        </tr>
                    </table>
                </td>
            </tr>
            {link_html}
        </table>"""

        html_body = get_base_template(content_html, title=subject)

        await send_notification_with_preference_check(
            to_email=chosen["email"],
            subject=subject,
            body=body_text,
            html_body=html_body,
            notification_type="process_assigned",
        )
        logger.info(
            f"[ASSIGN-INDEXER] Email de notificação enviado para {chosen['email']}"
        )
    except Exception as e:
        logger.warning(
            f"[ASSIGN-INDEXER] Erro ao enviar email de atribuição para {chosen['id']}: {e}"
        )

    # Notificação em tempo real (in-app)
    try:
        await send_realtime_notification(
            user_id=chosen["id"],
            title="Novo Processo Atribuído",
            message=f"Foi-lhe atribuído automaticamente o processo de {client_name}",
            notification_type="process_assigned",
            link=f"/processo/{process_id}",
            process_id=process_id,
        )
    except Exception as e:
        logger.warning(
            f"[ASSIGN-INDEXER] Erro ao enviar notificação in-app para {chosen['id']}: {e}"
        )

    return True, {
        "assigned_indexacao_id": chosen["id"],
        "indexacao_name": chosen["name"],
        "status": "fase_documental",
        "assigned": True,
        "indexer_active_count": chosen["active_count"] + 1,
        "indexers_available": len(available_indexers),
    }, (
        f"Processo atribuído automaticamente a {chosen['name']} "
        f"({chosen['active_count']} → {chosen['active_count'] + 1} processos ativos)"
    )


# ==== AUTO-ATRIBUIÇÃO DE CONSULTOR/INTERMEDIÁRIO (FALLBACK) ====

# Status que NÃO contam como processos ativos para o consultor/intermediário
CONSULTANT_INACTIVE_STATUSES = {
    "concluidos",
    "arquivo",
    "perdido",
    "desistencias",
    "eliminados",
}


async def _count_active_processes_for_consultant(consultant_id: str) -> int:
    """
    Conta quantos processos ATIVOS um consultor/intermediário tem atualmente.

    Um processo conta como "ativo" se:
    - Está atribuído a ele (assigned_consultor_id == consultant_id OU consultant_id == consultant_id)
    - O seu status NÃO está na lista de estados inativos

    Args:
        consultant_id: ID do utilizador consultor/intermediário

    Returns:
        Número de processos ativos atribuídos ao consultor
    """
    active_query = {
        "$or": [
            {"assigned_consultor_id": consultant_id},
            {"consultant_id": consultant_id},
        ],
        "status": {"$nin": list(CONSULTANT_INACTIVE_STATUSES)},
    }

    count = await db.processes.count_documents(active_query)
    return count


async def assign_to_least_busy_consultant(process_id: str) -> Tuple[bool, dict, str]:
    """
    Atribui automaticamente um processo ao consultor/intermediário com menor carga.

    Algoritmo de distribuição:
    1. Encontra todos os utilizadores com o role 'consultor' ou 'intermediario'
       (incluindo additional_roles).
    2. Para cada consultor, conta os processos ativos (status não terminal).
    3. Ordena pelo número de processos ativos (ascendente) — distribui a quem tem menos.
    4. Se houver consultor disponível:
       - Atribui o processo (assigned_consultor_id + consultor_name).
       - Envia notificação em tempo real (in-app).
    5. Se NÃO houver consultores no sistema:
       - O processo avança de estado mas fica sem consultor atribuído (não órfão de estado).

    Args:
        process_id: ID do processo a atribuir

    Returns:
        Tuple com (sucesso, dados atualizados, mensagem)
    """
    from services.role_query import build_deep_role_query
    from services.history import log_history

    # ── 1. Obter o processo ──
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        return False, {}, f"Processo {process_id} não encontrado"

    # Verificar se já tem consultor atribuído
    existing_consultor = (
        process.get("assigned_consultor_id")
        or process.get("consultant_id")
    )
    if existing_consultor:
        existing_name = (
            process.get("consultor_name")
            or process.get("assigned_consultor_id")
        )
        return True, {
            "assigned_consultor_id": existing_consultor,
        }, f"Processo já tem consultor atribuído: {existing_name}"

    # ── 2. Encontrar todos os consultores/intermediários ativos ──
    # Pesquisar por ambos os roles
    consultor_query = build_deep_role_query({"is_active": True}, role="consultor")
    intermediario_query = build_deep_role_query({"is_active": True}, role="intermediario")

    consultores_cursor = db.users.find(
        consultor_query,
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "additional_roles": 1}
    )
    intermediarios_cursor = db.users.find(
        intermediario_query,
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "additional_roles": 1}
    )

    consultores = await consultores_cursor.to_list(length=100)
    intermediarios = await intermediarios_cursor.to_list(length=100)

    # Combinar e remover duplicados (alguém pode ter ambos os roles)
    seen_ids = set()
    all_consultants = []
    for c in consultores + intermediarios:
        if c["id"] not in seen_ids:
            seen_ids.add(c["id"])
            all_consultants.append(c)

    if not all_consultants:
        logger.warning(
            f"[ASSIGN-CONSULTANT] Nenhum consultor/intermediário encontrado no sistema. "
            f"Processo {process_id} avança de estado sem consultor atribuído."
        )
        return True, {
            "assigned": False,
            "reason": "no_consultants",
        }, "Nenhum consultor/intermediário disponível — processo avança sem atribuição"

    # ── 3. Contar processos ativos por consultor ──
    consultant_loads: List[Dict] = []
    for consultant in all_consultants:
        active_count = await _count_active_processes_for_consultant(consultant["id"])
        consultant_loads.append({
            "id": consultant["id"],
            "name": consultant.get("name", ""),
            "email": consultant.get("email", ""),
            "role": consultant.get("role", ""),
            "active_count": active_count,
        })
        logger.debug(
            f"[ASSIGN-CONSULTANT] Consultor {consultant.get('name')} "
            f"({consultant['id'][:8]}): {active_count} processos ativos"
        )

    # ── 4. Ordenar por carga (ascendente) e escolher o menos carregado ──
    consultant_loads.sort(key=lambda c: c["active_count"])
    chosen = consultant_loads[0]

    logger.info(
        f"[ASSIGN-CONSULTANT] Consultor escolhido: {chosen['name']} "
        f"com {chosen['active_count']} processos ativos "
        f"(de {len(consultant_loads)} disponíveis)"
    )

    # ── 5. Atribuir processo ao consultor ──
    now = datetime.now(timezone.utc).isoformat()
    update_data = {
        "assigned_consultor_id": chosen["id"],
        "consultant_id": chosen["id"],
        "consultor_name": chosen["name"],
        "updated_at": now,
    }

    result = await db.processes.update_one(
        {"id": process_id},
        {"$set": update_data}
    )

    if result.modified_count == 0:
        return False, {}, "Erro ao atribuir processo ao consultor"

    # Registar no histórico (utilizador sistema)
    system_user = {"id": "system", "name": "Sistema", "role": "admin"}
    await log_history(
        process_id=process_id,
        user=system_user,
        action=f"Auto-atribuição ao consultor/intermediário {chosen['name']}",
        field="assigned_consultor_id",
        old_value=None,
        new_value=chosen["name"],
    )

    # ── 6. Enviar notificação in-app ──
    try:
        from services.realtime_notifications import send_realtime_notification

        client_name = process.get("client_name", "Cliente")
        await send_realtime_notification(
            user_id=chosen["id"],
            title="Novo Processo Atribuído",
            message=f"Foi-lhe atribuído automaticamente o processo de {client_name}",
            notification_type="process_assigned",
            link=f"/processo/{process_id}",
            process_id=process_id,
        )
    except Exception as e:
        logger.warning(
            f"[ASSIGN-CONSULTANT] Erro ao enviar notificação in-app para {chosen['id']}: {e}"
        )

    return True, {
        "assigned_consultor_id": chosen["id"],
        "consultant_id": chosen["id"],
        "consultor_name": chosen["name"],
        "assigned": True,
        "consultant_active_count": chosen["active_count"] + 1,
    }, (
        f"Processo atribuído automaticamente a {chosen['name']} "
        f"({chosen['active_count']} → {chosen['active_count'] + 1} processos ativos)"
    )


async def process_queue_for_freed_indexer(indexer_id: str) -> int:
    """
    Processa a fila de espera quando um indexador liberta capacidade.

    Quando um indexador completa ou entrega um processo, a sua carga diminui.
    Esta função verifica se existem processos na 'fila_espera' e, se sim,
    atribui o mais antigo ao indexador que ficou com vaga.

    Deve ser chamada quando:
    - Um processo com indexador atribuído muda para status terminal (concluído, desistência)
    - Um indexador é removido de um processo manualmente

    Args:
        indexer_id: ID do indexador que libertou capacidade

    Returns:
        Número de processos da fila que foram atribuídos
    """
    from services.history import log_history

    # Verificar se o indexador tem capacidade agora
    active_count = await _count_active_processes_for_indexer(indexer_id)
    if active_count >= MAX_ACTIVE_PROCESSES_PER_INDEXER:
        return 0  # Ainda sem vaga

    # Obter dados do indexador
    indexer = await db.users.find_one({"id": indexer_id}, {"_id": 0, "name": 1, "email": 1})
    if not indexer:
        return 0

    # Buscar processos na fila de espera (ordenados por data de criação — mais antigo primeiro)
    queue_cursor = db.processes.find(
        {"status": "fila_espera"},
        {"_id": 0}
    ).sort("created_at", 1)

    queue_processes = await queue_cursor.to_list(length=MAX_ACTIVE_PROCESSES_PER_INDEXER - active_count)

    assigned_count = 0
    for proc in queue_processes:
        proc_id = proc["id"]

        # Verificar se ainda tem vaga
        current_active = await _count_active_processes_for_indexer(indexer_id)
        if current_active >= MAX_ACTIVE_PROCESSES_PER_INDEXER:
            break

        # Atribuir processo
        now = datetime.now(timezone.utc).isoformat()
        update_data = {
            "assigned_indexacao_id": indexer_id,
            "indexacao_name": indexer.get("name", ""),
            "status": "fase_documental",
            "updated_at": now,
        }

        await db.processes.update_one(
            {"id": proc_id},
            {"$set": update_data}
        )

        # Histórico
        system_user = {"id": "system", "name": "Sistema", "role": "admin"}
        await log_history(
            process_id=proc_id,
            user=system_user,
            action=f"Retirado da fila e atribuído a {indexer.get('name')}",
            field="status",
            old_value="fila_espera",
            new_value="fase_documental",
        )

        # Notificações
        client_name = proc.get("client_name", "Cliente")
        try:
            from services.notification_service import send_notification_with_preference_check
            from services.realtime_notifications import send_realtime_notification
            from services.email import get_base_template
            import os

            frontend_url = os.environ.get("FRONTEND_URL", "")
            process_link = f"{frontend_url}/processo/{proc_id}" if frontend_url else ""
            process_number = proc.get("process_number") or proc.get("process_ref") or proc_id[:8]

            subject = f"Processo da Fila Atribuído: {client_name}"
            body_text = (
                f"Olá {indexer.get('name', '')},\n\n"
                f"Um processo que estava na fila de espera foi-lhe atribuído.\n\n"
                f"Cliente: {client_name}\n"
                f"Processo: {process_number}\n"
            )

            link_html = ""
            if process_link:
                link_html = f"""
                <tr>
                    <td style="padding: 15px 30px; text-align: center;">
                        <a href="{process_link}" style="
                            display: inline-block;
                            background: linear-gradient(135deg, #1e3a5f, #2d5a87);
                            color: #ffffff;
                            padding: 12px 30px;
                            border-radius: 8px;
                            text-decoration: none;
                            font-weight: 600;
                            font-size: 14px;
                        ">Abrir Processo no CRM</a>
                    </td>
                </tr>"""

            content_html = f"""
            <table width="100%" cellpadding="0" cellspacing="0" style="padding: 20px 0;">
                <tr>
                    <td style="padding: 10px 30px;">
                        <p style="margin: 0 0 10px 0; font-size: 16px;">Olá <strong>{indexer.get('name', '')}</strong>,</p>
                        <p style="margin: 0 0 20px 0; font-size: 15px; color: #555;">
                            Um processo que estava na <strong>fila de espera</strong> foi-lhe atribuído.
                        </p>
                    </td>
                </tr>
                <tr>
                    <td style="padding: 15px 30px; background: #f8f9fa; border-radius: 8px;">
                        <table width="100%" cellpadding="0" cellspacing="0">
                            <tr>
                                <td style="padding: 8px 0; font-size: 14px; color: #666; width: 120px;"><strong>Cliente:</strong></td>
                                <td style="padding: 8px 0; font-size: 14px;">{client_name}</td>
                            </tr>
                            <tr>
                                <td style="padding: 8px 0; font-size: 14px; color: #666;"><strong>Processo:</strong></td>
                                <td style="padding: 8px 0; font-size: 14px;">{process_number}</td>
                            </tr>
                        </table>
                    </td>
                </tr>
                {link_html}
            </table>"""

            html_body = get_base_template(content_html, title=subject)

            await send_notification_with_preference_check(
                to_email=indexer.get("email", ""),
                subject=subject,
                body=body_text,
                html_body=html_body,
                notification_type="process_assigned",
            )

            await send_realtime_notification(
                user_id=indexer_id,
                title="Processo da Fila Atribuído",
                message=f"Um processo da fila de espera de {client_name} foi-lhe atribuído",
                notification_type="process_assigned",
                link=f"/processo/{proc_id}",
                process_id=proc_id,
            )
        except Exception as e:
            logger.warning(
                f"[QUEUE-PROCESS] Erro ao notificar indexador {indexer_id} sobre processo {proc_id}: {e}"
            )

        assigned_count += 1
        logger.info(
            f"[QUEUE-PROCESS] Processo {proc_id} retirado da fila e atribuído a "
            f"{indexer.get('name')} (vaga libertada)"
        )

    if assigned_count > 0:
        logger.info(
            f"[QUEUE-PROCESS] {assigned_count} processos da fila atribuídos a "
            f"{indexer.get('name')} (carga actual: {active_count + assigned_count})"
        )

    return assigned_count


# ==== GATILHO DE LIBERTAÇÃO DA FILA DE ESPERA ====

async def check_waitlist_for_indexer(user_id: str) -> int:
    """
    Verifica se o indexador tem capacidade e puxa o processo mais antigo da fila.

    Gatilho principal do motor de onboarding: quando um indexador completa
    a indexação de um processo (is_indexed=true) ou um processo atribuído
    a ele muda para estado terminal, esta função é invocada para verificar
    se há processos na fila_espera que possam ser atribuídos.

    Fluxo:
    1. Verifica se o user_id tem role 'indexacao' (direto ou additional_roles).
    2. Conta os processos ativos actuais do indexador.
    3. Se < MAX_ACTIVE_PROCESSES_PER_INDEXER, procura o processo mais antigo
       no estado 'fila_espera' (ordem de created_at ASC).
    4. Se existir, atribui ao indexador, muda o estado para 'fase_documental'
       e envia notificação por email e in-app.
    5. Repete enquanto houver vagas e processos na fila.

    Deve ser chamada (via asyncio.create_task para não bloquear):
    - Em mark_process_indexed (is_indexed = true)
    - Em move_process_kanban (status → terminal: concluidos, desistencias)
    - Em update_process (status → terminal)

    Args:
        user_id: ID do utilizador indexador que libertou capacidade

    Returns:
        Número de processos da fila atribuídos ao indexador
    """
    from services.role_query import deep_role_filter

    # Verificar se o utilizador tem role indexacao
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "role": 1, "additional_roles": 1})
    if not user:
        logger.debug(f"[WAITLIST] Utilizador {user_id} não encontrado")
        return 0

    user_role = user.get("role", "")
    additional_roles = user.get("additional_roles") or []

    is_indexer = user_role == "indexacao" or "indexacao" in additional_roles
    if not is_indexer:
        logger.debug(f"[WAITLIST] Utilizador {user_id} não é indexador (role={user_role})")
        return 0

    # Delegar para a função de processamento da fila
    assigned = await process_queue_for_freed_indexer(user_id)

    if assigned > 0:
        logger.info(
            f"[WAITLIST] {assigned} processo(s) da fila atribuídos ao indexador {user_id}"
        )

    return assigned


# ==== DUPLA AUTO-ATRIBUIÇÃO (Conversão Pré-Registo → Pipeline) ====

async def _find_least_busy_user(
    role: str,
    company_id: Optional[str] = None
) -> Optional[Dict]:
    """
    Encontra o utilizador activo com menor carga para um dado role.
    
    "Menor carga" = menor nº de processos activos atribuídos.
    Processos em pré-registo NÃO contam como carga real.
    
    Args:
        role: 'consultor' ou 'intermediario'
        company_id: Filtrar por empresa (Multi-Tenant)
    
    Returns:
        Dict com id, name, current_load ou None
    """
    from services.role_query import build_deep_role_query

    query = build_deep_role_query({"is_active": True}, role=role)
    
    users = await db.users.find(
        query,
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1}
    ).to_list(100)

    if not users:
        logger.warning(f"[DUAL-AUTO] Nenhum utilizador activo com role={role}")
        return None

    # Contar processos activos por utilizador (excluindo pré-registo)
    user_loads = []
    for user in users:
        if role == "consultor":
            field = "assigned_consultor_ids"
        else:
            field = "assigned_mediador_ids"

        count_query = {
            field: user["id"],
            "is_active": True,
            "status": {"$ne": "pre_registo"},  # pré-registo NÃO conta como carga
        }
        if company_id:
            count_query["company_id"] = company_id

        count = await db.processes.count_documents(count_query)
        user_loads.append({
            "id": user["id"],
            "name": user.get("name", ""),
            "email": user.get("email", ""),
            "current_load": count,
        })

    # Ordenar por carga ascendente — menos ocupado primeiro
    user_loads.sort(key=lambda u: u["current_load"])

    chosen = user_loads[0]
    logger.info(
        f"[DUAL-AUTO] Least-busy {role} seleccionado: "
        f"{chosen['name']} ({chosen['current_load']} processos, "
        f"{len(user_loads)} candidatos)"
    )
    return chosen


async def dual_auto_assign_on_pre_registo_transition(
    process_id: str,
    company_id: Optional[str] = None,
    indexador_user_id: Optional[str] = None
) -> Dict:
    """
    🔥 DUPLA AUTO-ATRIBUIÇÃO — Conversão Mágica
    
    Quando o Indexador valida os documentos e clica em "Concluído/Indexado",
    o status transita de pre_registo para a primeira fase oficial da pipeline.
    
    NESTE EXACTO MOMENTO DA TRANSIÇÃO, o backend DISPARA o motor de
    auto-atribuição para preencher em simultâneo os DOIS papéis:
    
    - consultor_id → menos ocupado
    - mediador_id  → menos ocupado
    
    Se os campos já estiverem preenchidos, NÃO sobrescreve.
    
    Args:
        process_id: ID do processo que transitou de pre_registo
        company_id: Empresa activa (Multi-Tenant)
        indexador_user_id: O indexador que executou a validação
    
    Returns:
        Dict com consultor_id, consultor_name, mediador_id, mediador_name
    """
    from services.history import log_history

    logger.info(
        f"[DUAL-AUTO] 🚀 Dupla auto-atribuição iniciada "
        f"processo={process_id} empresa={company_id}"
    )

    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        logger.error(f"[DUAL-AUTO] Processo {process_id} não encontrado")
        return {}

    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    result_data = {}

    # ── Consultor: só atribui se campo vazio ─────────────────────
    existing_consultant = process.get("consultant_id")
    if existing_consultant:
        user = await db.users.find_one({"id": existing_consultant}, {"name": 1})
        result_data["consultant_id"] = existing_consultant
        result_data["consultant_name"] = user.get("name", "") if user else ""
        logger.info(
            f"[DUAL-AUTO] Consultor já atribuído: {result_data['consultant_name']} — mantendo"
        )
    else:
        consultor = await _find_least_busy_user("consultor", company_id)
        if consultor:
            update_data["consultant_id"] = consultor["id"]
            result_data["consultant_id"] = consultor["id"]
            result_data["consultant_name"] = consultor["name"]

    # ── Intermediário: só atribui se campo vazio ─────────────────
    existing_mediador = process.get("mediador_id")
    if existing_mediador:
        user = await db.users.find_one({"id": existing_mediador}, {"name": 1})
        result_data["mediador_id"] = existing_mediador
        result_data["mediador_name"] = user.get("name", "") if user else ""
        logger.info(
            f"[DUAL-AUTO] Mediador já atribuído: {result_data['mediador_name']} — mantendo"
        )
    else:
        intermediario = await _find_least_busy_user("intermediario", company_id)
        if intermediario:
            update_data["mediador_id"] = intermediario["id"]
            result_data["mediador_id"] = intermediario["id"]
            result_data["mediador_name"] = intermediario["name"]

    # ── Actualização ATÓMICA: ambos os papéis em simultâneo ──────
    if len(update_data) > 1:  # Mais do que apenas updated_at
        await db.processes.update_one(
            {"id": process_id},
            {"$set": update_data}
        )

    # ── Registar no histórico ────────────────────────────────────
    system_user = {"id": indexador_user_id or "system", "name": "Sistema", "role": "admin"}
    assigned_parts = []
    if "consultant_name" in result_data and not existing_consultant:
        assigned_parts.append(f"Consultor: {result_data['consultant_name']}")
    if "mediador_name" in result_data and not existing_mediador:
        assigned_parts.append(f"Intermediário: {result_data['mediador_name']}")

    if assigned_parts:
        await log_history(
            process_id=process_id,
            user=system_user,
            action=f"Dupla auto-atribuição (pré-registo → pipeline): {', '.join(assigned_parts)}",
            field="assignment",
            old_value="",
            new_value=", ".join(assigned_parts),
        )

    logger.info(
        f"[DUAL-AUTO] ✅ Dupla auto-atribuição concluída "
        f"consultor={result_data.get('consultant_name', 'N/A')} "
        f"intermediario={result_data.get('mediador_name', 'N/A')}"
    )

    return result_data
