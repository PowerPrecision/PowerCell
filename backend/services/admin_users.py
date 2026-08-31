"""Users CRUD, impersonate, notification prefs, user email-config (admin).

Extraído de `routes/admin.py`.
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Optional

from fastapi import HTTPException, Query, Request, BackgroundTasks
from pydantic import BaseModel

from database import db
from models.auth import UserRole, UserCreate, UserUpdate, UserResponse
from models.workflow import WorkflowStatusCreate, WorkflowStatusUpdate, WorkflowStatusResponse
from models.email_config import EmailConfigCreate, EmailConfigResponse
from services.auth import hash_password, require_roles, get_current_user
from services.admin_helpers import _safe_float, _audit_log
from services.permissions import (
    get_default_permissions_for_role,
    get_all_available_permissions,
    get_role_display_info,
    validate_permissions,
    DEFAULT_PERMISSIONS_BY_ROLE,
    get_user_capabilities,
    build_permissions_document,
)
from models.permissions import (
    CAPABILITIES,
    CATEGORIES,
    SUPER_ADMIN_ROLES,
    ROLE_CAPABILITY_DEFAULTS,
    get_all_capabilities,
    get_capabilities_by_category,
    get_role_defaults,
    resolve_capability,
    validate_capabilities,
)

logger = logging.getLogger(__name__)

# Pacote EB — a Tab de Utilizadores da Administração precisa da lista completa
# (admin, indexação, inativos, parceiros). Sem paginação curta (ex. limit=10).
ADMIN_USERS_LIST_LIMIT = 10000


DEFAULT_NOTIFICATION_PREFS = {
    "email_new_process": False,  # Novo processo criado
    "email_status_change": False,  # Mudança de status de processo
    "email_document_upload": False,  # Documento carregado
    "email_task_assigned": False,  # Tarefa atribuída
    "email_deadline_reminder": True,  # Lembrete de prazo (importante)
    "email_urgent_only": True,  # Apenas urgentes
    "email_daily_summary": True,  # Resumo diário
    "email_weekly_report": True,  # Relatório semanal
    "inapp_new_process": True,
    "inapp_status_change": True,
    "inapp_document_upload": True,
    "inapp_task_assigned": True,
    "inapp_comments": True,
    "is_test_user": False,  # Se true, não recebe emails
}



async def run_get_users(
    user: dict,
    role: Optional[str] = None,
    for_assignment: bool = False,
):
    """Lista utilizadores do sistema, opcionalmente filtrados por role.

    O campo password é excluído da resposta por segurança.
    Acessível a Admin, CEO, Diretor, Consultor e Intermediário porque
    estes roles precisam de ver informações de utilizadores para
    atribuição de processos e colaboração.

    Pacote DT / FL: `for_assignment=True` exclui admin (e cliente/parceiro)
    das dropdowns de responsáveis; inclui indexação. A gestão de
    utilizadores chama sem este flag para continuar a listar todos os cargos.

    Pacote EB: por defeito NÃO filtra `is_active` nem cargos de staff —
    devolve admin, indexação, inativos e restantes, até
    ``ADMIN_USERS_LIST_LIMIT``.

    Args:
        role: Filtro opcional por role (ex: "consultor", "admin").
        user: Utilizador autenticado com role permitido (injetado).
        for_assignment: Se True, só devolve staff atribuível (inclui indexação).

    Returns:
        List[UserResponse]: Lista de utilizadores (sem password).
    """
    from services.role_query import build_deep_role_query
    from services.staff_assignment import (
        apply_assignment_staff_filter,
        filter_assignment_staff,
    )

    query = {}
    if role:
        query = build_deep_role_query(query, role=role)
    query = apply_assignment_staff_filter(query, for_assignment)

    users = await db.users.find(query, {"_id": 0, "password": 0}).to_list(
        ADMIN_USERS_LIST_LIMIT
    )
    if for_assignment:
        users = filter_assignment_staff(users)
    return [UserResponse(**u) for u in users]


async def run_create_user(data: UserCreate, user: dict):
    """Cria um novo utilizador no sistema com lógica diferenciada por role.

    Este endpoint suporta dois fluxos distintos de criação:

    **Utilizadores normais** (Consultor, Intermediário, Diretor, etc.):
    - Valida presença de email, password e role válido.
    - Verifica unicidade do email.
    - Envia email de boas-vindas com credenciais (não falha a criação
      se o email não for enviado).
    - Associa automaticamente processos do Trello cujo nome do membro
      corresponda ao nome do utilizador criado. (deprecated — Trello removed)

    **Parceiros** (ghost users):
    - Apenas requer nome. Email/password não são necessários porque
      parceiros não acedem ao sistema diretamente — servem apenas para
      associação a processos como entidades externas.
    - Gera um email placeholder único para satisfazer a constraint de
      unicidade sem reservar emails reais.

    Porquê o CLIENTE não pode ser criado aqui: no PowerCell, clientes
    são representados por processos (não por utilizadores do sistema).
    Um cliente submete o formulário público e é criado como processo.

    Args:
        data: Dados do utilizador (UserCreate com email, name, phone,
            password, role, onedrive_folder).
        user: Utilizador admin/CEO autenticado (injetado).

    Returns:
        UserResponse: Dados do utilizador criado (sem password).

    Raises:
        HTTPException(400): Se role é CLIENTE, role inválido, email já
            registado, password em falta, ou nome em falta (parceiro).
    """
    # Sanitizar inputs (sem validação restritiva — aceitar qualquer valor)
    clean_email = (data.email or "").strip().lower()
    clean_name = (data.name or "").strip()
    clean_phone = (data.phone or "").strip() if data.phone else None
    
    # Cliente não é um utilizador do sistema - é um processo
    if data.role == UserRole.CLIENTE:
        raise HTTPException(status_code=400, detail="Cliente não pode ser criado como utilizador. O cliente é representado pelo processo.")
    
    # Validar role - inclui PARCEIRO
    valid_roles = [UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO, UserRole.INDEXACAO, UserRole.CEO, UserRole.ADMIN, UserRole.PARCEIRO]
    if data.role not in valid_roles:
        raise HTTPException(status_code=400, detail="Role inválido")
    
    # PARCEIRO é um "ghost user" - apenas precisa do nome
    is_parceiro = data.role == UserRole.PARCEIRO
    
    if is_parceiro:
        # Para parceiros: nome é obrigatório, email/password não são necessários
        if not clean_name:
            raise HTTPException(status_code=400, detail="Nome é obrigatório")
        
        # Gerar email placeholder único para parceiros (para não violar unique constraint)
        import uuid as uuid_module
        placeholder_email = f"parceiro_{uuid_module.uuid4().hex[:8]}@placeholder.internal"
        
        user_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        
        user_doc = {
            "id": user_id,
            "email": placeholder_email,
            "password": None,  # Sem password para parceiros
            "name": clean_name,
            "phone": clean_phone,
            "role": data.role,
            "company": data.company or None,  # Empresa do utilizador
            "additional_roles": data.additional_roles or [],
            "is_active": True,
            "onedrive_folder": None,  # Parceiros não precisam de pasta
            "base_salary": _safe_float(data.base_salary),  # Vencimento fixo mensal
            "created_at": now
        }
        
        await db.users.insert_one(user_doc)
        await _audit_log("user_created", "user", user_id, user, {"role": data.role, "additional_roles": data.additional_roles, "name": clean_name, "type": "parceiro_ghost"})
        
        # Não enviar email de boas-vindas para parceiros
        return UserResponse(**user_doc)
    
    # Para outros roles: validar email e password
    existing = await db.users.find_one({"email": clean_email})
    if existing:
        raise HTTPException(status_code=400, detail="Email já registado")
    
    # Validar password (apenas presença — sem validação de força)
    if not data.password:
        raise HTTPException(status_code=400, detail="Password é obrigatória")
    
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    user_doc = {
        "id": user_id,
        "email": clean_email,
        "password": hash_password(data.password),
        "name": clean_name,
        "phone": clean_phone,
        "role": data.role,
        "company": data.company or None,  # Empresa do utilizador (ex: "Power Real Estate", "Precision Crédito")
        "additional_roles": data.additional_roles or [],
        "is_active": True,
        "onedrive_folder": data.onedrive_folder or clean_name,
        "base_salary": _safe_float(data.base_salary),  # Vencimento fixo mensal
        "created_at": now
    }
    
    await db.users.insert_one(user_doc)
    await _audit_log("user_created", "user", user_id, user, {"email": clean_email, "role": data.role, "additional_roles": data.additional_roles, "name": clean_name, "company": data.company})
    
    # Enviar email de boas-vindas com dados de acesso
    try:
        from services.email_service import send_email
        
        # Determinar o nome do cargo em português
        role_names = {
            UserRole.CONSULTOR: "Consultor",
            UserRole.INTERMEDIARIO: "Intermediário",
            UserRole.DIRETOR: "Diretor",
            UserRole.ADMINISTRATIVO: "Administrativo",
            UserRole.INDEXACAO: "Indexação",
            UserRole.CEO: "CEO",
            UserRole.ADMIN: "Administrador"
        }
        role_name = role_names.get(data.role, data.role)
        
        # Criar corpo do email
        # PACOTE DI — marca client-facing actualizada para Precision Crédito.
        email_body = f"""Olá {clean_name},

Bem-vindo(a) ao Precision Crédito!

A sua conta foi criada com sucesso. Seguem os dados de acesso:

📧 Email: {clean_email}
🔑 Password: {data.password}

Perfil: {role_name}

🔗 Aceda à plataforma em: https://powercell.vercel.app

Recomendamos que altere a sua password após o primeiro acesso.

Se tiver alguma dúvida, não hesite em contactar.

Cumprimentos,
Equipa Precision Crédito
"""
        
        email_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #1e3a5f 0%, #0d253f 100%); padding: 30px; border-radius: 10px 10px 0 0; text-align: center;">
                <h1 style="color: white; margin: 0;">Bem-vindo ao Precision Crédito</h1>
            </div>
            <div style="background: #f8fafc; padding: 30px; border-radius: 0 0 10px 10px; border: 1px solid #e2e8f0; border-top: none;">
                <p style="font-size: 16px; color: #334155;">Olá <strong>{data.name}</strong>,</p>
                <p style="font-size: 16px; color: #334155;">A sua conta foi criada com sucesso. Seguem os dados de acesso:</p>
                
                <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0; border: 1px solid #e2e8f0;">
                    <p style="margin: 10px 0;"><strong>📧 Email:</strong> {data.email}</p>
                    <p style="margin: 10px 0;"><strong>🔑 Password:</strong> <code style="background: #f1f5f9; padding: 2px 6px; border-radius: 4px;">{data.password}</code></p>
                    <p style="margin: 10px 0;"><strong>👤 Perfil:</strong> {role_name}</p>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="https://powercell.vercel.app" style="background: linear-gradient(135deg, #0d9488 0%, #0f766e 100%); color: white; padding: 12px 30px; border-radius: 8px; text-decoration: none; font-weight: bold; display: inline-block;">
                        Aceder à Plataforma
                    </a>
                </div>
                
                <p style="font-size: 14px; color: #64748b; background: #fef3c7; padding: 15px; border-radius: 8px; border-left: 4px solid #f59e0b;">
                    ⚠️ Recomendamos que altere a sua password após o primeiro acesso.
                </p>
                
                <p style="font-size: 14px; color: #64748b; margin-top: 30px;">
                    Se tiver alguma dúvida, não hesite em contactar.<br><br>
                    Cumprimentos,<br>
                    <strong>Equipa Precision Crédito</strong>
                </p>
            </div>
        </body>
        </html>
        """
        
        # PACOTE DI — subject client-facing actualizado para Precision Crédito.
        email_result = await send_email(
            account_name="power",  # Usar conta Power Real Estate
            to_emails=[clean_email],
            subject="Bem-vindo ao Precision Crédito - Dados de Acesso",
            body=email_body,
            body_html=email_html
        )
        
        if email_result.get("success"):
            logger.info(f"Email de boas-vindas enviado para {data.email}")
        else:
            logger.warning(f"Não foi possível enviar email para {data.email}: {email_result.get('error')}")
            
    except Exception as e:
        logger.warning(f"Erro ao enviar email de boas-vindas: {e}")
        # Não falhar a criação do utilizador se o email falhar
    
    # Trello member auto-association removed (Trello integration deprecated)
    
    return UserResponse(
        id=user_id,
        email=clean_email,
        name=clean_name,
        phone=clean_phone,
        role=data.role,
        created_at=now,
        onedrive_folder=data.onedrive_folder or clean_name
    )


async def run_update_user(user_id: str, data: UserUpdate, user: dict):
    """Atualiza os dados de um utilizador existente.

    Este endpoint suporta a atualização de todos os campos editáveis
    do utilizador, com regras de negócio específicas:

    - **Email**: Verifica unicidade contra outros utilizadores.
    - **Role**: Se alterado, sincroniza automaticamente as permissões
      com o novo role (a menos que o utilizador tenha permissões
      personalizadas — nesse caso mantém as personalizadas).
    - **is_active**: Protege o utilizador administrador de ser
      desativado (um admin desativado não poderia ser reativado).
    - **Password**: Hasha a nova password antes de guardar.
    - **Permissões explícitas**: Se o admin fornecer permissões no
      body, essas sobrepõem-se às padrão do role.

    Porquê a sincronização automática de permissões: quando o role
    de um utilizador muda (ex: Consultor → Diretor), as suas
    permissões devem refletir as capacidades do novo cargo. No
    entanto, se o admin definiu permissões personalizadas manualmente,
    essas são preservadas para não destruir configurações deliberadas.

    Args:
        user_id: ID do utilizador a atualizar.
        data: Campos a atualizar (UserUpdate com name, phone, email,
            role, is_active, password, permissions, onedrive_folder).
        user: Utilizador admin/CEO autenticado (injetado).

    Returns:
        UserResponse: Dados atualizados do utilizador (sem password).

    Raises:
        HTTPException(404): Se utilizador não encontrado.
        HTTPException(400): Se email já existe noutro utilizador,
            role inválido, ou tentativa de desativar um admin.
    """
    from services.permissions import should_sync_permissions
    
    target_user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    update_data = {}
    role_changed = False
    old_role = target_user.get("role")
    
    if data.name is not None:
        update_data["name"] = (data.name or "").strip()
    if data.phone is not None:
        update_data["phone"] = (data.phone or "").strip() if data.phone else None
    if data.email is not None:
        clean_email = (data.email or "").strip().lower()
        if clean_email:
            # Verificar se email já existe noutro utilizador
            existing = await db.users.find_one({"email": clean_email, "id": {"$ne": user_id}})
            if existing:
                raise HTTPException(status_code=400, detail="Email já registado noutro utilizador")
            update_data["email"] = clean_email
    if data.role is not None:
        if data.role not in [UserRole.CLIENTE, UserRole.CONSULTOR, UserRole.INTERMEDIARIO, UserRole.DIRETOR, UserRole.ADMINISTRATIVO, UserRole.INDEXACAO, UserRole.CEO, UserRole.ADMIN]:
            raise HTTPException(status_code=400, detail="Role inválido")
        if data.role != old_role:
            role_changed = True
        update_data["role"] = data.role
    if data.is_active is not None:
        # Proteger admin de ser desactivado
        if target_user.get("role") == "admin" and data.is_active == False:
            raise HTTPException(status_code=400, detail="Não é possível desactivar o utilizador administrador")
        update_data["is_active"] = data.is_active
    if data.onedrive_folder is not None:
        update_data["onedrive_folder"] = data.onedrive_folder
    # Processar base_salary (vencimento fixo mensal — modelo híbrido)
    if data.base_salary is not None:
        salary = _safe_float(data.base_salary)
        if salary < 0:
            raise HTTPException(status_code=400, detail="Salário fixo não pode ser negativo")
        update_data["base_salary"] = salary
    # Processar additional_roles (múltiplos perfis)
    if data.additional_roles is not None:
        update_data["additional_roles"] = data.additional_roles
    # Processar empresa (company) do utilizador
    if data.company is not None:
        update_data["company"] = data.company.strip() if data.company.strip() else None
    # Processar alteração de password (apenas admin pode alterar password de outros)
    if data.password is not None and data.password.strip():
        update_data["password"] = hash_password(data.password)
    
    # Processar permissões - sincronizar automaticamente quando o role muda
    current_permissions = target_user.get("permissions")
    new_role = data.role or old_role
    
    if data.permissions is not None:
        # Se o admin está a definir permissões explicitamente, usar essas
        update_data["permissions"] = validate_permissions(data.permissions)
    elif role_changed:
        # Se o role mudou, sincronizar permissões com o novo role
        # Apenas sincronizar se o utilizador não tinha permissões personalizadas
        if should_sync_permissions(old_role, new_role, current_permissions):
            update_data["permissions"] = get_default_permissions_for_role(new_role)
            logger.info(f"Permissões sincronizadas para utilizador {user_id}: {old_role} -> {new_role}")
        # Se tinha permissões personalizadas, manter (admin pode redefinir manualmente)
    
    if update_data:
        await db.users.update_one({"id": user_id}, {"$set": update_data})
    
    updated = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    return UserResponse(**updated)


async def run_delete_user(user_id: str, user: dict):
    """Elimina permanentemente um utilizador do sistema.

    Este endpoint remove o utilizador da base de dados de forma
    irreversível. Por segurança, impede que um utilizador elimine
    a sua própria conta (o que causaria sessão órfã).

    Nota: a eliminação não remove processos, documentos, ou histórico
    associados ao utilizador. Esses dados permanecem no sistema para
    preservar a integridade do histórico de processos.

    Args:
        user_id: ID do utilizador a eliminar.
        user: Utilizador admin/CEO autenticado (injetado).

    Returns:
        dict: Mensagem de confirmação ``{"message": "Utilizador eliminado"}``.

    Raises:
        HTTPException(400): Se tentar eliminar a própria conta.
        HTTPException(404): Se utilizador não encontrado.
    """
    if user_id == user["id"]:
        raise HTTPException(status_code=400, detail="Não pode eliminar a própria conta")
    
    target = await db.users.find_one({"id": user_id}, {"_id": 0, "email": 1, "name": 1, "role": 1})
    result = await db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    await _audit_log("user_deleted", "user", user_id, user, {"deleted_email": target.get("email"), "deleted_name": target.get("name"), "deleted_role": target.get("role")})
    return {"message": "Utilizador eliminado"}


async def run_impersonate_user(user_id: str, user: dict):
    """
    Permite ao admin/CEO ver o sistema como outro utilizador, gerando
    um token temporário com os dados e permissões do utilizador alvo.

    Porquê este endpoint existe: essencial para suporte técnico e
    troubleshooting — permite ao admin reproduzir exatamente o que o
    utilizador vê (permissões, dados visíveis, interface) sem precisar
    de partilhar passwords ou usar a conta de outro utilizador.

    Garantias de segurança:
    - Impedir personificação de outros admins (autoproteção).
    - Token inclui campos de auditoria (impersonated_by, is_impersonated).
    - Toda a ação realizada durante impersonate é registada no histórico.

    Args:
        user_id: ID do utilizador a personificar.
        user: Utilizador admin/CEO autenticado (injetado pelo Depends).

    Returns:
        dict: Novo access_token e dados do utilizador personificado,
            incluindo campos de auditoria (impersonated_by, is_impersonated).

    Raises:
        HTTPException: 404 se utilizador não encontrado, 403 se tentar
            personificar outro administrador.
    """
    from services.auth import create_access_token
    
    # Verificar que o utilizador alvo existe
    target_user = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    # Não permitir impersonate de outro admin
    if target_user["role"] == UserRole.ADMIN and user_id != user["id"]:
        raise HTTPException(status_code=403, detail="Não pode personificar outro administrador")
    
    # Criar token com dados do utilizador alvo, mas marcar como impersonated
    token_data = {
        "sub": target_user["id"],
        "email": target_user["email"],
        "role": target_user["role"],
        "name": target_user["name"],
        # Informação de auditoria
        "impersonated_by": user["id"],
        "impersonated_by_name": user["name"],
        "is_impersonated": True
    }
    
    access_token = create_access_token(token_data)
    
    # Log da acção
    await db.history.insert_one({
        "id": str(uuid.uuid4()),
        "process_id": None,
        "user_id": user["id"],
        "user_name": user["name"],
        "action": f"Admin impersonou utilizador: {target_user['name']} ({target_user['email']})",
        "field": "impersonate",
        "old_value": None,
        "new_value": target_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    })
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": target_user["id"],
            "email": target_user["email"],
            "name": target_user["name"],
            "role": target_user["role"],
            "is_impersonated": True,
            "impersonated_by": user["id"],
            "impersonated_by_name": user["name"]
        }
    }


async def run_stop_impersonate(user: dict):
    """
    Termina a sessão de personificação e restaura a conta original do admin.

    Porquê um endpoint dedicado: o token do utilizador personificado não
    contém a password do admin original, pelo que não é possível fazer
    login diretamente. Este endpoint usa o campo ``impersonated_by`` do
    token atual para identificar o admin original e gerar um novo token.

    Args:
        user: Utilizador atualmente em modo de personificação (o token
            contém o campo impersonated_by com o ID do admin original).

    Returns:
        dict: Novo access_token para a conta original do admin e dados
            do administrador (sem campos de personificação).

    Raises:
        HTTPException: 400 se não está em modo de personificação,
            404 se o admin original não foi encontrado.
    """
    from services.auth import create_access_token
    
    if not user.get("impersonated_by"):
        raise HTTPException(status_code=400, detail="Não está em modo de personificação")
    
    # Buscar o admin original
    admin_user = await db.users.find_one({"id": user["impersonated_by"]}, {"_id": 0, "password": 0})
    if not admin_user:
        raise HTTPException(status_code=404, detail="Administrador original não encontrado")
    
    # Criar novo token para o admin
    token_data = {
        "sub": admin_user["id"],
        "email": admin_user["email"],
        "role": admin_user["role"],
        "name": admin_user["name"]
    }
    
    access_token = create_access_token(token_data)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": admin_user["id"],
            "email": admin_user["email"],
            "name": admin_user["name"],
            "role": admin_user["role"]
        }
    }


async def run_get_notification_preferences(
    user_id: str,
    user: dict,
    company_id: Optional[str] = None
):
    """
    Obtém as preferências de notificação de um utilizador.
    Admin pode ver/editar de qualquer utilizador.

    PACOTE DF — Per-UCR: Se `company_id` for fornecido (query param),
    procura primeiro o campo `notification_preferences` na UCR
    (user_company_roles, keyed por user_id + company_id). Se existir,
    devolve essas preferências. Caso contrário, cai para o store global
    (db.notification_preferences) para backward compat.
    """
    target_user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")

    # ── PACOTE DF — Tentar ler da UCR ativa primeiro ──
    if company_id and company_id != "default":
        try:
            ucr_doc = await db.user_company_roles.find_one(
                {"user_id": user_id, "company_id": company_id},
                {"_id": 0, "notification_preferences": 1}
            )
            if ucr_doc and ucr_doc.get("notification_preferences"):
                return {
                    "user_id": user_id,
                    "user_email": target_user.get("email"),
                    "user_name": target_user.get("name"),
                    "company_id": company_id,
                    "scope": "ucr",
                    "preferences": ucr_doc["notification_preferences"]
                }
        except Exception as e:
            logger.warning(
                f"[admin/get_notif_prefs] Erro ao ler UCR para user_id={user_id}, "
                f"company_id={company_id!r}: {e}. A usar store global."
            )

    # Obter preferências globais da DB ou usar defaults
    prefs = await db.notification_preferences.find_one({"user_id": user_id}, {"_id": 0})

    if not prefs:
        prefs = {**DEFAULT_NOTIFICATION_PREFS, "user_id": user_id}

    return {
        "user_id": user_id,
        "user_email": target_user.get("email"),
        "user_name": target_user.get("name"),
        "scope": "global",
        "preferences": prefs
    }


async def run_update_notification_preferences(
    user_id: str,
    preferences: dict,
    user: dict,
    company_id: Optional[str] = None
):
    """
    Actualiza as preferências de notificação de um utilizador.
    Admin pode editar de qualquer utilizador.

    PACOTE DF — Per-UCR: Se `company_id` for fornecido (query param),
    grava as preferências em `user_company_roles.notification_preferences`
    (keyed por user_id + company_id) e também no store global para
    backward compat. Caso contrário, mantém o comportamento legacy
    (gravação apenas no store global).
    """
    target_user = await db.users.find_one({"id": user_id})
    if not target_user:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")

    # Filtrar apenas campos válidos
    valid_keys = set(DEFAULT_NOTIFICATION_PREFS.keys())
    filtered_prefs = {k: v for k, v in preferences.items() if k in valid_keys}

    filtered_prefs["user_id"] = user_id
    filtered_prefs["updated_at"] = datetime.now(timezone.utc).isoformat()
    filtered_prefs["updated_by"] = user.get("email", "admin")

    # ── PACOTE DF — Gravar na UCR se houver company_id ──
    if company_id and company_id != "default":
        try:
            ucr_update = {
                "notification_preferences": {k: v for k, v in filtered_prefs.items()
                                             if k in valid_keys},
                "updated_at": filtered_prefs["updated_at"]
            }
            await db.user_company_roles.update_one(
                {"user_id": user_id, "company_id": company_id},
                {"$set": ucr_update},
                upsert=True
            )
            logger.info(
                f"[admin/update_notif_prefs] UCR gravação: user_id={user_id}, "
                f"company_id={company_id!r}"
            )
        except Exception as e:
            logger.warning(
                f"[admin/update_notif_prefs] Erro ao gravar na UCR "
                f"(user_id={user_id}, company_id={company_id!r}): {e}. "
                f"A gravar apenas no store global."
            )

    # Gravar no store global (sempre, para backward compat com consumidores legacy)
    await db.notification_preferences.update_one(
        {"user_id": user_id},
        {"$set": filtered_prefs},
        upsert=True
    )

    # Invalidar cache de preferências de notificação
    try:
        from services.realtime_notifications import _invalidate_pref_cache
        _invalidate_pref_cache(user_id)
    except ImportError:
        pass

    return {"success": True, "preferences": filtered_prefs, "scope": "ucr" if (company_id and company_id != "default") else "global"}


async def run_get_all_notification_preferences(user: dict):
    """Lista preferências de todos os utilizadores."""
    users = await db.users.find({}, {"_id": 0, "id": 1, "email": 1, "name": 1, "role": 1}).to_list(500)
    
    result = []
    for u in users:
        prefs = await db.notification_preferences.find_one({"user_id": u["id"]}, {"_id": 0})
        if not prefs:
            prefs = {**DEFAULT_NOTIFICATION_PREFS, "user_id": u["id"]}
        
        result.append({
            "user_id": u["id"],
            "email": u.get("email"),
            "name": u.get("name"),
            "role": u.get("role"),
            "receives_email": not prefs.get("is_test_user", False) and (
                prefs.get("email_urgent_only") or 
                prefs.get("email_daily_summary") or
                prefs.get("email_weekly_report")
            ),
            "is_test_user": prefs.get("is_test_user", False)
        })
    
    return result


async def run_bulk_update_notification_preferences(data: dict, user: dict):
    """
    Actualiza preferências de múltiplos utilizadores de uma vez.
    
    Body:
    {
        "user_ids": ["id1", "id2"],
        "preferences": {"is_test_user": true}
    }
    """
    user_ids = data.get("user_ids", [])
    preferences = data.get("preferences", {})
    
    if not user_ids:
        raise HTTPException(status_code=400, detail="user_ids é obrigatório")
    
    valid_keys = set(DEFAULT_NOTIFICATION_PREFS.keys())
    filtered_prefs = {k: v for k, v in preferences.items() if k in valid_keys}
    filtered_prefs["updated_at"] = datetime.now(timezone.utc).isoformat()
    filtered_prefs["updated_by"] = user.get("email", "admin")
    
    updated = 0
    for uid in user_ids:
        result = await db.notification_preferences.update_one(
            {"user_id": uid},
            {"$set": {**filtered_prefs, "user_id": uid}},
            upsert=True
        )
        if result.modified_count > 0 or result.upserted_id:
            updated += 1
    
    # Invalidar cache de preferências de notificação para todos os utilizadores afectados
    try:
        from services.realtime_notifications import _invalidate_pref_cache
        for uid in user_ids:
            _invalidate_pref_cache(uid)
    except ImportError:
        pass
    
    return {"success": True, "updated_count": updated}


async def run_admin_get_user_email_config(user_id: str, admin: dict):
    """Obter configuração de email de um utilizador alvo (Admin/CEO).

    SEGURANÇA: Nunca devolve a password real — apenas has_password: true.
    O admin pode VER que uma password existe, mas nunca a lê em plain-text.

    Args:
        user_id: ID do utilizador alvo.
        admin: Utilizador admin/CEO autenticado (injetado).

    Returns:
        dict: Configuração de email (sem password).

    Raises:
        HTTPException(404): Se utilizador não encontrado.
    """
    target = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "email_config": 1, "name": 1, "email": 1}
    )
    if not target:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")

    config = target.get("email_config")
    if not config:
        return {
            "is_configured": False,
            "email_address": None,
            "imap_server": None,
            "imap_port": None,
            "smtp_server": None,
            "smtp_port": None,
            "has_password": False,
            "target_user": {
                "id": user_id,
                "name": target.get("name"),
                "email": target.get("email"),
            },
        }

    return {
        "is_configured": config.get("is_configured", False),
        "email_address": config.get("email_address"),
        "imap_server": config.get("imap_server"),
        "imap_port": config.get("imap_port", 993),
        "smtp_server": config.get("smtp_server"),
        "smtp_port": config.get("smtp_port", 465),
        "has_password": bool(config.get("encrypted_password")),
        "has_google_oauth": bool(config.get("google_refresh_token")),
        "auth_method": (
            "google_oauth" if config.get("google_refresh_token")
            else "imap_smtp" if config.get("encrypted_password")
            else "none"
        ),
        "google_email": config.get("google_email"),
        "target_user": {
            "id": user_id,
            "name": target.get("name"),
            "email": target.get("email"),
        },
    }


async def run_admin_set_user_email_config(user_id: str, config: 'EmailConfigCreate', admin: dict):
    """Definir configuração de email IMAP/SMTP de um utilizador alvo (Admin/CEO).

    SEGURANÇA: A password fornecida pelo admin é encriptada com Fernet
    (via services/encryption.py) ANTES de ser guardada na base de dados.
    O admin nunca visualiza a password existente — apenas pode definir uma nova.

    Se a password for omitida/vazia e o utilizador já tem uma configuração,
    a password existente é mantida.

    Args:
        user_id: ID do utilizador alvo.
        config: Dados de configuração (EmailConfigCreate).
        admin: Utilizador admin/CEO autenticado (injetado).

    Returns:
        dict: success, message.

    Raises:
        HTTPException(404): Se utilizador não encontrado.
        HTTPException(500): Se erro ao guardar.
    """
    from models.email_config import EmailConfigCreate
    from services.encryption import encryption_service

    target = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "name": 1, "email_config": 1}
    )
    if not target:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")

    # Se não foi fornecida password, manter a existente (se houver)
    encrypted_password = ""
    existing_config = target.get("email_config", {})
    if config.password:
        encrypted_password = encryption_service.encrypt(config.password)
    elif existing_config.get("encrypted_password"):
        encrypted_password = existing_config["encrypted_password"]

    email_config = {
        "email_address": config.email_address.strip().lower(),
        "imap_server": config.imap_server.strip(),
        "imap_port": config.imap_port,
        "smtp_server": config.smtp_server.strip(),
        "smtp_port": config.smtp_port,
        "encrypted_password": encrypted_password,
        "is_configured": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Preservar campos Google OAuth existentes (não os apagar ao guardar IMAP)
    if existing_config.get("google_refresh_token"):
        email_config["google_refresh_token"] = existing_config["google_refresh_token"]
    if existing_config.get("google_access_token"):
        email_config["google_access_token"] = existing_config["google_access_token"]
    if existing_config.get("google_email"):
        email_config["google_email"] = existing_config["google_email"]
    if existing_config.get("auth_method"):
        email_config["auth_method"] = existing_config["auth_method"]
    if existing_config.get("oauth_connected_at"):
        email_config["oauth_connected_at"] = existing_config["oauth_connected_at"]

    result = await db.users.update_one(
        {"id": user_id},
        {"$set": {"email_config": email_config}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Erro ao guardar configuração")

    # Audit log
    await _audit_log(
        "user_email_config_set",
        "user",
        user_id,
        admin,
        {
            "email_address": config.email_address.strip().lower(),
            "imap_server": config.imap_server.strip(),
            "smtp_server": config.smtp_server.strip(),
        }
    )

    return {
        "success": True,
        "message": f"Configuração de email guardada para {target.get('name', user_id)}",
        "is_configured": True,
    }


async def run_admin_test_user_email_config(user_id: str, admin: dict):
    """Testar ligação de email de um utilizador alvo (Admin/CEO) — Smart.

    Se o utilizador tem Google OAuth → testa Gmail API.
    Se tem password IMAP/SMTP → testa IMAP/SMTP.

    Args:
        user_id: ID do utilizador alvo.
        admin: Utilizador admin/CEO autenticado (injetado).

    Returns:
        dict: success, auth_method, gmail_api_connected/imap_connected/smtp_connected, error.

    Raises:
        HTTPException(404): Se utilizador não encontrado.
        HTTPException(400): Se configuração de email não existe.
    """
    from services.gmail_oauth import test_connection_smart

    target = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "email_config": 1, "name": 1}
    )
    if not target:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")

    config = target.get("email_config")
    if not config:
        raise HTTPException(
            status_code=400,
            detail=f"Configuração de email não encontrada para {target.get('name', user_id)}"
        )

    result = await test_connection_smart(config, user_id)
    result["target_user"] = {
        "id": user_id,
        "name": target.get("name"),
    }
    return result


