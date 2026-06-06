import uuid
import re
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, Response, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

from database import db
from models.auth import (
    UserRole, UserRegister, UserLogin, UserResponse, TokenResponse
)
from services.auth import (
    hash_password, verify_password, needs_rehash, create_token, get_current_user,
    validate_password_strength
)
from utils.input_sanitization import (
    sanitize_string, log_sanitization_rejection
)
from middleware.rate_limit import limiter
from services.refresh_token_service import (
    create_access_token,
    create_refresh_token_db,
    rotate_refresh_token,
    revoke_refresh_token,
    revoke_all_user_tokens,
    get_active_sessions,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)


router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=TokenResponse)
@limiter.limit("3/hour")
async def register(request: Request, response: Response, data: UserRegister):
    """Regista um novo utilizador a partir do formulário público.

    Este endpoint é acessível sem autenticação e permite que novos
    utilizadores se registem no sistema. O role padrão é CLIENTE.

    Porquê sem autenticação: este é o ponto de entrada para novos
    utilizadores que ainda não têm conta. A validação é feita via
    campos obrigatórios (email, nome) e verificação de unicidade.

    Args:
        request: Objeto Request do FastAPI (para definir cookies).
        response: Objeto Response do FastAPI (para definir cookies).
        data: Dados de registo (UserRegister com email, name, phone, password).

    Returns:
        dict: Dados do utilizador registado com access_token.

    Raises:
        HTTPException(400): Se email em falta, já existe, ou dados inválidos.
    """
    # Normalizar inputs (sem validação de formato)
    clean_email = (data.email or "").strip().lower()
    if not clean_email:
        raise HTTPException(status_code=400, detail="Email é obrigatório")
    
    clean_name = (data.name or "").strip()
    clean_phone = (data.phone or "").strip() if data.phone else None
    
    existing = await db.users.find_one({"email": clean_email})
    if existing:
        raise HTTPException(status_code=400, detail="Email já registado")
    
    # Validar força da password
    is_valid, error_msg = validate_password_strength(data.password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    user_doc = {
        "id": user_id,
        "email": clean_email,
        "password": hash_password(data.password),
        "name": clean_name,
        "phone": clean_phone,
        "role": UserRole.CLIENTE,
        "is_active": True,
        "onedrive_folder": clean_name,
        "created_at": now
    }
    
    await db.users.insert_one(user_doc)
    token = create_token(user_id, clean_email, UserRole.CLIENTE)
    
    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user_id,
            email=clean_email,
            name=clean_name,
            phone=clean_phone,
            role=UserRole.CLIENTE,
            created_at=now,
            onedrive_folder=clean_name
        )
    )


@router.post("/login", deprecated=True)
@limiter.limit("10/minute")
async def login(request: Request, data: UserLogin, response: Response):
    """
    DEPRECATED: Esta rota foi descontinuada.
    Utilize /auth/login-v2 para autenticação segura com refresh tokens.
    
    Esta rota será removida em futuras versões.
    """
    raise HTTPException(
        status_code=410, 
        detail="Esta rota de login foi descontinuada. Utilize /auth/login-v2 para autenticação segura com refresh tokens."
    )


@router.get("/me")
async def get_me(request: Request, user: dict = Depends(get_current_user)):
    """Retorna o utilizador atual incluindo info de impersonate e permissões se aplicável.
    
    Sincroniza as permissões com as defaults do role em cada request,
    garantindo que alterações a DEFAULT_PERMISSIONS_BY_ROLE são refletidas
    imediatamente para todos os utilizadores (resolve permissões legacy).
    
    INCLUI: Lista de empresas associadas (user_company_roles) e empresa ativa.
    """
    from services.permissions import get_default_permissions_for_role, sync_permissions_with_role_defaults
    from services.auth import get_user_companies, get_active_company_id_async
    
    # Sincronizar permissões: garantir que actions novas no role são adicionadas
    user_perms = user.get("permissions")
    role = user.get("role", "cliente")
    synced_perms = sync_permissions_with_role_defaults(user_perms, role)
    
    # Verificar se houve alterações (nova action adicionada) e persistir
    if user_perms is not None and synced_perms != user_perms:
        try:
            await db.users.update_one(
                {"id": user["id"]},
                {"$set": {"permissions": synced_perms}}
            )
        except Exception:
            pass  # Falha silenciosa — não bloqueia o request
    
    # Determinar email_configured usando o resolver (suporta configs nested por role)
    email_configured = False
    raw_email_config = user.get("email_config", {})
    if raw_email_config:
        # Verificar se é uma config nested (per-role) ou flat (legacy)
        from services.email_config_resolver import _is_nested_email_config, _extract_role_email_config
        if _is_nested_email_config(raw_email_config):
            # Nested: verificar se qualquer sub-config tem is_configured=True
            for key, value in raw_email_config.items():
                if isinstance(value, dict) and value.get("is_configured"):
                    email_configured = True
                    break
        elif raw_email_config.get("is_configured"):
            # Flat (legacy): verificar diretamente
            email_configured = True
        # Também verificar se tem credenciais (password ou OAuth) sem flag is_configured
        if not email_configured:
            from services.email_config_resolver import _extract_role_email_config
            flat_config = _extract_role_email_config(raw_email_config)
            if flat_config.get("encrypted_password") or flat_config.get("google_refresh_token"):
                email_configured = True

    # Para admin/ceo/diretor/administrativo, também verificar se existe config global (SystemConfigPage)
    if not email_configured and user.get("role") in ("admin", "ceo", "diretor", "administrativo"):
        try:
            config = await db.system_config.find_one({"_id": "main"}, {"_id": 0, "email": 1, "system_smtp": 1, "system_webmail": 1})
            if config:
                # Verificar Bloco A (system_smtp — Resend API ou SMTP legado)
                system_smtp_block = config.get("system_smtp", {})
                has_resend_api = bool(
                    system_smtp_block.get("resend_api_key") and
                    system_smtp_block.get("resend_api_key") != "••••••••"
                )
                has_legacy_smtp = bool(
                    system_smtp_block.get("smtp_host") and
                    system_smtp_block.get("smtp_username")
                )
                # Verificar Bloco B (email legacy — dupla conta)
                email_config_block = config.get("email", {})
                has_smtp_config = bool(
                    email_config_block.get("provider") == "smtp" and
                    email_config_block.get("smtp_host") and
                    email_config_block.get("smtp_user")
                )
                # Verificar Bloco C (system_webmail — indexação IMAP)
                system_webmail_block = config.get("system_webmail", {})
                has_webmail_config = bool(
                    system_webmail_block.get("imap_host") and
                    system_webmail_block.get("email_user") and
                    system_webmail_block.get("app_password")
                )
                # Também verificar contas de email via env vars (get_email_accounts)
                # e provider transacional via email_v2 (EMAIL_API_KEY)
                if has_resend_api or has_legacy_smtp or has_smtp_config or has_webmail_config:
                    email_configured = True
                else:
                    from services.email_service import get_email_accounts
                    if get_email_accounts():
                        email_configured = True
                    else:
                        import os
                        if os.environ.get("EMAIL_API_KEY"):
                            email_configured = True
        except Exception:
            pass  # Falha silenciosa — não bloqueia o request

    # ── Multi-Empresa: empresas associadas e empresa ativa ──
    # ── Multi-Perfil: Ler X-Active-Role para context switching ──
    active_role_header = request.headers.get("X-Active-Role", "")

    # Valores por defeito (dados globais do user)
    effective_phone = user.get("phone")
    effective_email_signature = user.get("email_signature", "")
    active_company_id = None
    active_assoc = None

    try:
        user_companies = await get_user_companies(user["id"])
        if user_companies:
            # Determinar empresa ativa (X-Company-Id header ou default)
            active_company_id = await get_active_company_id_async(request, user)
            # Encontrar a associação na empresa ativa
            active_assoc = next(
                (c for c in user_companies if c.get("company_id") == active_company_id),
                None
            )
            if active_assoc:
                # ── MERGE: Sobrepor campos globais com dados da empresa ativa ──
                # Se houver professional_phone para a empresa ativa, sobrepõe o
                # phone global. Se houver signature, sobrepõe o email_signature.
                # Isto garante que o frontend vê sempre os dados correctos
                # independentemente de ler user.phone ou user.email_signature.
                if active_assoc.get("professional_phone"):
                    effective_phone = active_assoc["professional_phone"]
                if active_assoc.get("signature"):
                    effective_email_signature = active_assoc["signature"]
    except Exception as e:
        logger.warning(f"[auth/me] Erro ao carregar empresas do utilizador: {e}")
        # Não bloquear o request — empresas são opcional
        user_companies = []

    # Construir resposta com os valores mergeados
    # IMPORTANTE: 'companies' e 'active_company_id' devem estar SEMPRE presentes
    # na resposta, mesmo que vazios, para que o React possa saber os IDs das
    # empresas e alternar entre elas no ContextSwitcher.
    response = {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "phone": effective_phone,  # ← Mergeado: professional_phone da empresa ativa ou phone global
        "role": user["role"],
        "company": user.get("company"),
        "created_at": user["created_at"],
        "onedrive_folder": user.get("onedrive_folder"),
        "is_active": user.get("is_active", True),
        "permissions": synced_perms,
        "additional_roles": user.get("additional_roles", []),
        "email_configured": email_configured,
        "email_signature": effective_email_signature,  # ← Mergeado: signature da empresa ativa ou global
        # ── Multi-empresa: SEMPRE presentes (fallback vazio) ──
        "companies": user_companies or [],
        "active_company_id": active_company_id or user.get("company"),
    }

    # Popular campos detalhados da empresa activa
    if user_companies and active_assoc:
        company_role = active_assoc.get("role")
        effective_active_role = active_role_header if active_role_header else company_role
        response["active_company_role"] = effective_active_role
        response["active_company_name"] = active_assoc.get("company_name")
        response["active_company_signature"] = active_assoc.get("signature", "")
        response["active_company_professional_phone"] = active_assoc.get("professional_phone", "")
        response["active_company_job_title"] = active_assoc.get("job_title", "")
    else:
        # Fallback: sem associação activa ou sem empresas
        response["active_company_role"] = active_role_header or user.get("role")
        response["active_company_name"] = ""
        response["active_company_signature"] = ""
        response["active_company_professional_phone"] = ""
        response["active_company_job_title"] = ""
    
    # Incluir informação de impersonate se presente
    if user.get("is_impersonated"):
        response["is_impersonated"] = True
        response["impersonated_by"] = user.get("impersonated_by")
        response["impersonated_by_name"] = user.get("impersonated_by_name")
    
    return response



@router.put("/preferences")
async def update_preferences(
    data: dict,
    user: dict = Depends(get_current_user)
):
    """
    Atualiza as preferências de notificação do utilizador.
    Sanitiza todas as chaves e valores string para prevenir stored XSS.
    """
    user_id = user["id"]
    
    # Extrair preferências de notificação
    notifications = data.get("notifications", {})
    
    # Sanitizar: apenas permitir chaves esperadas e limpar valores
    ALLOWED_NOTIFICATION_KEYS = {
        "email_new_process", "email_status_change", "email_document_upload",
        "email_task_assigned", "email_deadline_reminder", "email_urgent_only",
        "email_daily_summary", "email_weekly_report",
        "inapp_new_process", "inapp_status_change", "inapp_document_upload",
        "inapp_task_assigned", "inapp_comments",
        "is_test_user"
    }
    
    sanitized_notifications = {}
    for key, value in notifications.items():
        # Rejeitar chaves não esperadas (previne injection de campos arbitrários)
        if key not in ALLOWED_NOTIFICATION_KEYS:
            log_sanitization_rejection(f"preferences.{key}", str(key), "chave de notificação não permitida")
            continue
        # Valores devem ser booleanos
        if isinstance(value, bool):
            sanitized_notifications[key] = value
        elif isinstance(value, str):
            # Strings: aceitar apenas "true"/"false"
            sanitized_notifications[key] = value.lower() in ("true", "1", "yes")
        else:
            sanitized_notifications[key] = bool(value)
    
    update_data = {
        "notification_preferences": sanitized_notifications,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    result = await db.users.update_one(
        {"id": user_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    return {"success": True, "message": "Preferências atualizadas"}


@router.get("/preferences")
async def get_preferences(user: dict = Depends(get_current_user)):
    """
    Retorna as preferências de notificação do utilizador atual.
    """
    user_data = await db.users.find_one({"id": user["id"]}, {"_id": 0, "notification_preferences": 1})
    
    notifications = user_data.get("notification_preferences", {}) if user_data else {}
    
    return {"notifications": notifications}


@router.put("/profile")
async def update_profile(
    data: dict,
    request: Request,
    user: dict = Depends(get_current_user)
):
    """
    Permite ao utilizador atualizar o seu próprio perfil.
    
    MULTI-EMPRESA — Lógica de Separação (sem fuga de dados):
    
    - Empresa DEFAULT (ou sem contexto):  phone e email_signature gravam-se
      normalmente no documento global do utilizador (users collection).
    
    - Empresa NÃO-DEFAULT: phone e email_signature são EXTRAÍDOS do
      update_data via .pop() e redirecionados para a tabela
      user_company_roles (como professional_phone e signature).
      Isto impede que dados específicos de uma empresa secundária
      sobrescrevam os dados globais do utilizador.
    
    - Campos explicitamente da empresa (signature, professional_phone,
      job_title) vão sempre para user_company_roles, independentemente
      da empresa activa.
    
    - O campo "name" é sempre global (não varia por empresa).
    """
    user_id = user["id"]
    
    # ── Determinar o contexto de empresa ativa ──
    from services.auth import get_active_company_id_async, get_user_companies
    active_company_id = None
    active_assoc = None
    user_companies = []
    try:
        active_company_id = await get_active_company_id_async(request, user)
        user_companies = await get_user_companies(user_id)
        if active_company_id and user_companies:
            active_assoc = next(
                (c for c in user_companies if c.get("company_id") == active_company_id),
                None
            )
    except Exception as e:
        logger.warning(f"[auth/profile] Erro ao determinar empresa ativa: {e}")
    
    # Empresa default = sem contexto, ou is_default=True, ou company_id = user.company
    is_default_company = (
        not active_company_id
        or (active_assoc and active_assoc.get("is_default"))
        or active_company_id == user.get("company")
    )

    # ── Recolher campos globais permitidos ──
    allowed_fields = ["name", "phone", "email_signature"]
    update_data = {}
    
    for field in allowed_fields:
        if field in data and data[field] is not None:
            if field == "email_signature":
                update_data[field] = data[field]
            else:
                update_data[field] = str(data[field]).strip()

    # Verificar se há campos específicos da empresa (enviados explicitamente)
    has_company_fields = any(
        k in data and data[k] is not None
        for k in ("signature", "professional_phone", "job_title")
    )
    
    # ── Campos específicos por empresa — guardar em user_company_roles ──
    company_specific_fields = {}
    if "signature" in data and data["signature"] is not None:
        company_specific_fields["signature"] = data["signature"]
    if "professional_phone" in data and data["professional_phone"] is not None:
        company_specific_fields["professional_phone"] = str(data["professional_phone"]).strip()
    if "job_title" in data and data["job_title"] is not None:
        company_specific_fields["job_title"] = str(data["job_title"]).strip()

    # ── SEPARAÇÃO: Empresa não-default → extrair campos do global ──
    # Quando a empresa activa NÃO é a default, phone e email_signature
    # NÃO devem ser gravados no documento global (fuga de dados!).
    # Em vez disso, são redirecionados para user_company_roles.
    if active_company_id and not is_default_company:
        # .pop() remove do update_data (não será gravado no global)
        # e adiciona ao company_specific_fields (será gravado no UCR)
        prof_phone = update_data.pop("phone", None)
        if prof_phone is not None and "professional_phone" not in company_specific_fields:
            company_specific_fields["professional_phone"] = prof_phone
        
        comp_sig = update_data.pop("email_signature", None)
        if comp_sig is not None and "signature" not in company_specific_fields:
            company_specific_fields["signature"] = comp_sig
        
        logger.info(
            f"[auth/profile] Empresa não-default ({active_company_id!r}): "
            f"phone/email_signature redirecionados para UCR. "
            f"update_data restante={list(update_data.keys())}, "
            f"company_fields={list(company_specific_fields.keys())}"
        )

    # ── Validação final: tem de haver algo para gravar ──
    if not update_data and not has_company_fields and not company_specific_fields:
        raise HTTPException(status_code=400, detail="Nenhum campo válido para atualizar")
    
    # ── Gravação Global Segura ──
    # Só gravar no documento global se ainda houver campos (ex: name,
    # ou phone/email_signature quando a empresa É a default).
    # Se update_data ficou vazio após os .pop(), saltamos esta gravação.
    if update_data:
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        
        result = await db.users.update_one(
            {"id": user_id},
            {"$set": update_data}
        )
        
        if result.modified_count == 0 and result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Utilizador não encontrado")

    # ── Gravação Específica (user_company_roles) ──
    profile_warnings = []

    if company_specific_fields:
        try:
            logger.info(
                f"[auth/profile] Campos empresa: {list(company_specific_fields.keys())}, "
                f"active_company_id={active_company_id!r}, user_id={user_id}, "
                f"is_default={is_default_company}"
            )
            if active_company_id:
                company_specific_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
                result = await db.user_company_roles.update_one(
                    {"user_id": user_id, "company_id": active_company_id},
                    {"$set": company_specific_fields},
                    upsert=True
                )
                logger.info(
                    f"[auth/profile] UCR update_one: matched={result.matched_count}, "
                    f"modified={result.modified_count}, upserted={result.upserted_id}"
                )
            else:
                profile_warnings.append(
                    "Não foi possível determinar a empresa ativa. "
                    "Os dados profissionais não foram guardados por empresa. "
                    "Tente recarregar a página e repetir."
                )
                logger.warning(
                    f"[auth/profile] active_company_id é None — campos da empresa NÃO guardados! "
                    f"X-Company-Id header={request.headers.get('X-Company-Id')!r}, "
                    f"user.company={user.get('company')!r}"
                )
        except Exception as e:
            profile_warnings.append(f"Erro ao guardar dados da empresa: {e}")
            logger.warning(f"[auth/profile] Erro ao guardar campos específicos da empresa: {e}")

    # ── Retornar o utilizador actualizado COM merge (igual ao GET /auth/me) ──
    updated_user = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})

    # Adicionar campos da empresa ativa + MERGE (igual ao GET /auth/me)
    # Re-ler o UCR para obter os dados actualizados (o upsert acima pode
    # ter modificado professional_phone e signature)
    active_role_header_resp = request.headers.get("X-Active-Role", "")
    try:
        # Re-ler empresas para obter dados actualizados após o upsert
        refreshed_companies = await get_user_companies(user_id)
        if active_company_id and refreshed_companies:
            active_assoc_refreshed = next(
                (c for c in refreshed_companies if c.get("company_id") == active_company_id),
                None
            )
            if active_assoc_refreshed:
                updated_user["active_company_id"] = active_company_id
                company_role = active_assoc_refreshed.get("role")
                updated_user["active_company_role"] = active_role_header_resp if active_role_header_resp else company_role
                updated_user["active_company_name"] = active_assoc_refreshed.get("company_name")
                updated_user["active_company_signature"] = active_assoc_refreshed.get("signature", "")
                updated_user["active_company_professional_phone"] = active_assoc_refreshed.get("professional_phone", "")
                updated_user["active_company_job_title"] = active_assoc_refreshed.get("job_title", "")
                updated_user["companies"] = refreshed_companies
                # ── MERGE: Sobrepor campos globais com dados da empresa ativa ──
                if active_assoc_refreshed.get("professional_phone"):
                    updated_user["phone"] = active_assoc_refreshed["professional_phone"]
                if active_assoc_refreshed.get("signature"):
                    updated_user["email_signature"] = active_assoc_refreshed["signature"]
    except Exception as e:
        logger.warning(f"[auth/profile] Erro ao adicionar campos da empresa na resposta: {e}")

    response_data = {
        "success": True,
        "message": "Perfil atualizado com sucesso",
        "user": updated_user
    }
    if profile_warnings:
        response_data["warnings"] = profile_warnings
    return response_data


@router.post("/change-password")
async def change_password(
    data: dict,
    user: dict = Depends(get_current_user)
):
    """
    Permite ao utilizador alterar a sua própria password.
    """
    current_password = data.get("current_password")
    new_password = data.get("new_password")
    
    if not current_password or not new_password:
        raise HTTPException(status_code=400, detail="Password atual e nova password são obrigatórias")
    
    # Validar força da nova password
    is_valid, error_msg = validate_password_strength(new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    # Buscar utilizador com password
    user_data = await db.users.find_one({"id": user["id"]})
    if not user_data:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    
    # Verificar password atual
    password_field = user_data.get("password") or user_data.get("hashed_password", "")
    if not verify_password(current_password, password_field):
        raise HTTPException(status_code=400, detail="Password atual incorreta")
    
    # Actualizar password
    new_hashed = hash_password(new_password)
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {
            "password": new_hashed,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {"success": True, "message": "Password alterada com sucesso"}


# ====================================================================
# REFRESH TOKENS ENDPOINTS
# ====================================================================

@router.post("/login-v2")
@limiter.limit("10/minute")
async def login_v2(request: Request, data: UserLogin, response: Response):
    """
    Login com suporte a refresh tokens.
    Retorna access_token (2h) + refresh_token (7 dias).
    """
    try:
        # Normalizar email (sem bleach/sanitize_email — simples e seguro)
        clean_email = str(data.email).strip().lower() if data.email else ""
        if not clean_email or "@" not in clean_email:
            logger.warning(f"Login falhou: email vazio ou sem @")
            raise HTTPException(status_code=401, detail="Credenciais inválidas")
        
        # Case-insensitive query (MongoDB é case-sensitive por default)
        user = await db.users.find_one(
            {"email": {"$regex": f"^{clean_email}$", "$options": "i"}},
            {"_id": 0}
        )
        if not user:
            logger.warning(f"Login falhou: utilizador não encontrado para email={clean_email}")
            raise HTTPException(status_code=401, detail="Credenciais inválidas")
        
        password_field = user.get("password") or user.get("hashed_password", "")
        if not password_field:
            logger.error(f"Login falhou: utilizador {user['id']} sem password")
            raise HTTPException(status_code=401, detail="Credenciais inválidas")
        
        if not verify_password(data.password, password_field):
            logger.warning(f"Login falhou: password incorrecta para user={user['id']}")
            raise HTTPException(status_code=401, detail="Credenciais inválidas")

        # Re-hash automático: se a password está em formato legacy (SHA-256),
        # re-hashar para bcrypt de forma transparente após login bem-sucedido
        if needs_rehash(password_field):
            try:
                new_hash = hash_password(data.password)
                pw_field_name = "password" if user.get("password") else "hashed_password"
                await db.users.update_one(
                    {"id": user["id"]},
                    {"$set": {pw_field_name: new_hash}}
                )
                logger.info(f"Auto-rehash: user={user['id']} password migrada para bcrypt")
            except Exception as e:
                logger.error(f"Auto-rehash falhou para user={user['id']}: {e}")
                # Não bloquear o login — o utilizador consegue entrar de qualquer forma
        
        if not user.get("is_active", True):
            logger.warning(f"Login falhou: conta desactivada user={user['id']}")
            raise HTTPException(status_code=401, detail="Conta desativada")
        
        logger.info(f"Login bem-sucedido: user={user['id']} email={clean_email} role={user['role']}")
        
        # Sincronizar permissões com defaults do role (resolve permissões legacy)
        from services.permissions import sync_permissions_with_role_defaults
        user_perms = user.get("permissions")
        user_role = user.get("role", "cliente")
        synced_perms = sync_permissions_with_role_defaults(user_perms, user_role)
        if user_perms is not None and synced_perms != user_perms:
            await db.users.update_one(
                {"id": user["id"]},
                {"$set": {"permissions": synced_perms}}
            )
        
        # Criar access token
        access_token = create_access_token(
            user["id"],
            user["email"],
            user["role"]
        )
        
        # Criar refresh token
        device_info = str(request.headers.get("User-Agent", ""))[:200]
        client_host = ""
        try:
            client_host = request.client.host if request.client else ""
        except Exception:
            pass
        ip_address = str(request.headers.get("X-Forwarded-For", client_host))[:45]
        
        _, refresh_token = await create_refresh_token_db(
            user["id"],
            device_info=device_info,
            ip_address=ip_address
        )
        
        return JSONResponse(
            status_code=200,
            content={
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                "user": {
                    "id": user["id"],
                    "email": user["email"],
                    "name": user["name"],
                    "phone": user.get("phone"),
                    "role": user["role"],
                    "created_at": user["created_at"],
                    "onedrive_folder": user.get("onedrive_folder"),
                    "additional_roles": user.get("additional_roles", []),
                    "permissions": synced_perms,
                }
            }
        )
    except HTTPException:
        raise  # Re-lançar HTTPExceptions (401, 403, etc.)
    except Exception as e:
        logger.exception(f"Login crash inesperado: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro interno: {type(e).__name__}")


@router.post("/refresh")
async def refresh_tokens(request: Request, data: dict):
    """
    Renova tokens usando refresh token.
    Implementa rotação segura: token antigo é invalidado, novo é criado.
    Preserva metadados de impersonate do token anterior, se existirem.
    """
    import jwt as pyjwt
    
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="refresh_token é obrigatório")
    
    device_info = sanitize_string(request.headers.get("User-Agent", ""), max_length=200)
    ip_address = sanitize_string(request.headers.get("X-Forwarded-For", request.client.host if request.client else ""), max_length=45)
    
    result = await rotate_refresh_token(
        refresh_token,
        device_info=device_info,
        ip_address=ip_address
    )
    
    if not result:
        raise HTTPException(status_code=401, detail="Refresh token inválido ou expirado")
    
    _, new_refresh_token, user = result
    
    # Preservar metadados de impersonate do token anterior (se existirem)
    additional_data = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        old_token = auth_header[7:]
        try:
            old_payload = pyjwt.decode(old_token, options={"verify_signature": False, "verify_exp": False})
            if old_payload.get("is_impersonated"):
                additional_data = {
                    "impersonated_by": old_payload.get("impersonated_by"),
                    "impersonated_by_name": old_payload.get("impersonated_by_name"),
                    "is_impersonated": True,
                }
        except Exception:
            pass  # Token ilegível — continuar sem metadados de impersonate
    
    # Criar novo access token
    access_token = create_access_token(
        user["id"],
        user["email"],
        user["role"],
        additional_data=additional_data
    )
    
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/logout")
async def logout(data: dict, user: dict = Depends(get_current_user)):
    """
    Logout - revoga refresh token.
    Se refresh_token não fornecido, revoga todos os tokens do utilizador.
    """
    refresh_token = data.get("refresh_token")
    
    if refresh_token:
        # Revogar token específico
        revoked = await revoke_refresh_token(refresh_token)
        return {
            "success": revoked,
            "message": "Token revogado" if revoked else "Token não encontrado ou já revogado"
        }
    else:
        # Revogar todos os tokens do utilizador
        count = await revoke_all_user_tokens(user["id"])
        return {
            "success": True,
            "message": f"{count} sessão(ões) terminada(s)",
            "revoked_count": count
        }


@router.get("/sessions")
async def list_sessions(user: dict = Depends(get_current_user)):
    """
    Lista sessões activas do utilizador.
    """
    sessions = await get_active_sessions(user["id"])
    return {
        "sessions": sessions,
        "total": len(sessions)
    }


@router.delete("/sessions/{session_id}")
async def revoke_session(session_id: str, user: dict = Depends(get_current_user)):
    """
    Revoga uma sessão específica pelo ID.
    """
    # Buscar token pelo ID e verificar se pertence ao utilizador
    token_doc = await db.refresh_tokens.find_one(
        {"id": session_id, "user_id": user["id"]},
        {"_id": 0}
    )
    
    if not token_doc:
        raise HTTPException(status_code=404, detail="Sessão não encontrada")
    
    if token_doc.get("revoked"):
        raise HTTPException(status_code=400, detail="Sessão já terminada")
    
    await db.refresh_tokens.update_one(
        {"id": session_id},
        {
            "$set": {
                "revoked": True,
                "revoked_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    return {"success": True, "message": "Sessão terminada"}


@router.post("/validate-password")
async def validate_password_endpoint(data: dict):
    """
    Endpoint público para validar a força de uma password.
    Usado pelo frontend para feedback em tempo real.
    """
    password = data.get("password", "")
    
    is_valid, error_msg = validate_password_strength(password)
    
    # Calcular pontuação de força
    score = 0
    feedback = []
    
    if len(password) >= 8:
        score += 20
    else:
        feedback.append("Pelo menos 8 caracteres")
    
    if len(password) >= 12:
        score += 10
    
    if re.search(r'[a-z]', password):
        score += 15
    else:
        feedback.append("Pelo menos uma letra minúscula")
    
    if re.search(r'[A-Z]', password):
        score += 15
    else:
        feedback.append("Pelo menos uma letra maiúscula")
    
    if re.search(r'\d', password):
        score += 15
    else:
        feedback.append("Pelo menos um dígito")
    
    if re.search(r'[@$!%*?&#^()\-_=+\[\]{}|;:,.<>~`]', password):
        score += 25
    else:
        feedback.append("Pelo menos um carácter especial")
    
    # Determinar nível de força
    if score < 40:
        strength = "muito_fraca"
    elif score < 60:
        strength = "fraca"
    elif score < 80:
        strength = "media"
    elif score < 95:
        strength = "forte"
    else:
        strength = "muito_forte"
    
    return {
        "valid": is_valid,
        "error": error_msg if not is_valid else None,
        "score": min(score, 100),
        "strength": strength,
        "feedback": feedback
    }

