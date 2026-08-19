"""Auth profile /me / preferences orchestration — extracted from `routes/auth.py`.

Do **not** overwrite existing `services/auth.py` (get_current_user, companies helpers).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from utils.input_sanitization import log_sanitization_rejection
from services.auth import get_user_companies, get_active_company_id_async

logger = logging.getLogger(__name__)


async def run_get_me(request, user: dict):
    """Retorna o utilizador atual incluindo info de impersonate e permissões se aplicável.

    Sincroniza as permissões com as defaults do role em cada request,
    garantindo que alterações a DEFAULT_PERMISSIONS_BY_ROLE são refletidas
    imediatamente para todos os utilizadores (resolve permissões legacy).

    INCLUI: Lista de empresas associadas (user_company_roles) e empresa ativa.
    """
    from services.permissions import sync_permissions_with_role_defaults

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
        # Determinar empresa ativa (X-Company-Id header ou default)
        # Fazemos isto SEMPRE (mesmo com user_companies vazio) para
        # que o sentinel "default" seja correctamente propagado.
        active_company_id = await get_active_company_id_async(request, user)
        if user_companies:
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
        "company_roles": user_companies or [],  # alias (Área Pessoal / Header)
        "active_company_id": active_company_id or user.get("company"),
    }

    # Popular campos detalhados da empresa activa
    #
    # IMPORTANTE: Os campos active_company_* usam None (não "") como fallback
    # para que o frontend possa distinguir entre:
    #   - None → sem dados da empresa, usar o valor global (email_signature)
    #   - "" → assinatura intencionalmente limpa pelo utilizador
    # Isto é crucial para o operador ?? do JS funcionar correctamente.
    if user_companies and active_assoc:
        company_role = active_assoc.get("role")
        effective_active_role = active_role_header if active_role_header else company_role
        response["active_company_role"] = effective_active_role
        response["active_company_name"] = active_assoc.get("company_name")
        # Usar None se o campo não existe no UCR (nunca foi definido)
        response["active_company_signature"] = active_assoc.get("signature") if "signature" in active_assoc else None
        response["active_company_professional_phone"] = active_assoc.get("professional_phone") if "professional_phone" in active_assoc else None
        response["active_company_job_title"] = active_assoc.get("job_title") if "job_title" in active_assoc else None
        response["active_company_display_name"] = active_assoc.get("display_name") if "display_name" in active_assoc else None
        # ── MERGE: Sobrepõe nome global com display_name da empresa activa ──
        if active_assoc.get("display_name"):
            response["name"] = active_assoc["display_name"]
    else:
        # Fallback: sem associação activa ou sem empresas
        response["active_company_role"] = active_role_header or user.get("role")
        response["active_company_name"] = None
        response["active_company_signature"] = None
        response["active_company_professional_phone"] = None
        response["active_company_job_title"] = None
        response["active_company_display_name"] = None

    # Incluir informação de impersonate se presente
    if user.get("is_impersonated"):
        response["is_impersonated"] = True
        response["impersonated_by"] = user.get("impersonated_by")
        response["impersonated_by_name"] = user.get("impersonated_by_name")

    return response


async def run_update_preferences(data: dict, request, user: dict):
    """
    Atualiza as preferências de notificação do utilizador.
    Sanitiza todas as chaves e valores string para prevenir stored XSS.

    PACOTE DF — Per-UCR: Se houver empresa ativa (X-Company-Id), as
    preferências são gravadas em `user_company_roles.notification_preferences`
    (keyed por user_id + company_id). Se não houver contexto de empresa,
    mantém o comportamento legacy e grava no documento global do user
    (`users.notification_preferences`). O consumidor (notification_service /
    email_v2) aplica fallback automático: UCR > global.
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

    # ── PACOTE DF — Resolver empresa ativa para gravação por-UCR ──
    # Se houver contexto de empresa (header X-Company-Id ou user.company),
    # gravar preferências no documento UCR. Caso contrário, manter o
    # comportamento legacy (gravação no documento global do user).
    active_company_id = None
    try:
        active_company_id = await get_active_company_id_async(request, user)
    except Exception as e:
        logger.warning(f"[auth/preferences] Erro ao resolver empresa ativa: {e}")

    # Sentinel "default" ou None → sem UCR específica → gravação global legacy
    if active_company_id and active_company_id != "default":
        try:
            ucr_update = {
                "notification_preferences": sanitized_notifications,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            ucr_result = await db.user_company_roles.update_one(
                {"user_id": user_id, "company_id": active_company_id},
                {"$set": ucr_update},
                upsert=True
            )
            logger.info(
                f"[auth/preferences] UCR gravação: company_id={active_company_id!r}, "
                f"matched={ucr_result.matched_count}, modified={ucr_result.modified_count}, "
                f"upserted={ucr_result.upserted_id}"
            )
            # Também gravar no global como backward-compat para consumidores
            # que ainda não tenham sido actualizados para o padrão per-UCR.
            await db.users.update_one(
                {"id": user_id},
                {"$set": {
                    "notification_preferences": sanitized_notifications,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            return {"success": True, "message": "Preferências atualizadas", "scope": "ucr", "company_id": active_company_id}
        except Exception as e:
            logger.warning(
                f"[auth/preferences] Erro ao gravar preferências na UCR "
                f"(company_id={active_company_id!r}): {e}. A tentar global."
            )
            # Fall-through para gravação global

    # ── Gravação global (legacy / fallback) ──
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

    return {"success": True, "message": "Preferências atualizadas", "scope": "global"}


async def run_get_preferences(request, user: dict):
    """
    Retorna as preferências de notificação do utilizador atual.

    PACOTE DF — Per-UCR: Lê primeiro da UCR ativa (user_company_roles.
    notification_preferences) se houver contexto de empresa; caso a UCR
    não tenha o campo (None/vazio), cai para o store global
    (`users.notification_preferences`) para backward compat.
    """
    user_id = user["id"]

    # ── PACOTE DF — Tentar ler da UCR ativa primeiro ──
    active_company_id = None
    try:
        active_company_id = await get_active_company_id_async(request, user)
    except Exception as e:
        logger.warning(f"[auth/preferences] Erro ao resolver empresa ativa: {e}")

    if active_company_id and active_company_id != "default":
        try:
            ucr_doc = await db.user_company_roles.find_one(
                {"user_id": user_id, "company_id": active_company_id},
                {"_id": 0, "notification_preferences": 1}
            )
            if ucr_doc and ucr_doc.get("notification_preferences"):
                return {
                    "notifications": ucr_doc["notification_preferences"],
                    "scope": "ucr",
                    "company_id": active_company_id
                }
        except Exception as e:
            logger.warning(f"[auth/preferences] Erro ao ler UCR: {e}")

    # ── Fallback: ler do store global ──
    user_data = await db.users.find_one({"id": user["id"]}, {"_id": 0, "notification_preferences": 1})

    notifications = user_data.get("notification_preferences", {}) if user_data else {}

    return {"notifications": notifications, "scope": "global"}


async def run_update_profile(data: dict, request, user: dict):
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
    # Ou sentinel "default" (quando o frontend envia X-Company-Id: default
    # porque o utilizador não tem empresas em user_company_roles).
    is_default_company = (
        not active_company_id
        or active_company_id == "default"
        or (active_assoc and active_assoc.get("is_default"))
        or active_company_id == user.get("company")
    )

    # ── Aviso quando não há contexto de empresa ──
    # Isto ajuda a diagnosticar problemas de gravação de assinatura.
    if not active_company_id:
        logger.warning(
            f"[auth/profile] active_company_id é None — a gravar campos "
            f"da empresa no documento global do utilizador. "
            f"X-Company-Id header={request.headers.get('X-Company-Id')!r}, "
            f"user.company={user.get('company')!r}"
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
        for k in ("signature", "professional_phone", "job_title", "display_name")
    )

    # ── Campos específicos por empresa — guardar em user_company_roles ──
    company_specific_fields = {}
    if "signature" in data and data["signature"] is not None:
        company_specific_fields["signature"] = data["signature"]
    if "professional_phone" in data and data["professional_phone"] is not None:
        company_specific_fields["professional_phone"] = str(data["professional_phone"]).strip()
    if "job_title" in data and data["job_title"] is not None:
        company_specific_fields["job_title"] = str(data["job_title"]).strip()
    if "display_name" in data and data["display_name"] is not None:
        company_specific_fields["display_name"] = str(data["display_name"]).strip()

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

        # ── email_signature: só redirecionar para UCR se não houver
        # `signature` explícito nos company_specific_fields ──
        # Quando o frontend envia AMBOS `signature` e `email_signature`
        # (handleSaveSignature), o `signature` já está nos
        # company_specific_fields. Nesse caso, NÃO fazemos .pop() —
        # o `email_signature` fica em update_data e é gravado no
        # documento global (users collection) para backward compat
        # com o email_service, que lê users.email_signature.
        # Quando só `email_signature` é enviado (sem `signature`), o
        # .pop() + redirecionamento para UCR continua a funcionar.
        if "signature" not in company_specific_fields:
            comp_sig = update_data.pop("email_signature", None)
            if comp_sig is not None:
                company_specific_fields["signature"] = comp_sig
        # else: signature já em company_specific_fields (veio do
        # frontend), email_signature fica em update_data → global

        logger.info(
            f"[auth/profile] Empresa não-default ({active_company_id!r}): "
            f"phone redirecionado para UCR. "
            f"email_signature em update_data={('email_signature' in update_data)}, "
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
    ucr_company_id = None

    if company_specific_fields:
        try:
            logger.info(
                f"[auth/profile] Campos empresa: {list(company_specific_fields.keys())}, "
                f"active_company_id={active_company_id!r}, user_id={user_id}, "
                f"is_default={is_default_company}"
            )
            # ── Garantir que active_company_id está definido ──
            # Se for None (sem X-Company-Id header e sem user.company),
            # usar "default" como fallback para que a assinatura seja sempre
            # guardada no UCR. Isto evita que a assinatura se perca quando
            # o utilizador não tem contexto de empresa explícito.
            ucr_company_id = active_company_id or user.get("company") or "default"
            company_specific_fields["updated_at"] = datetime.now(timezone.utc).isoformat()
            result = await db.user_company_roles.update_one(
                {"user_id": user_id, "company_id": ucr_company_id},
                {"$set": company_specific_fields},
                upsert=True
            )
            logger.info(
                f"[auth/profile] UCR update_one: matched={result.matched_count}, "
                f"modified={result.modified_count}, upserted={result.upserted_id}, "
                f"company_id={ucr_company_id!r}"
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
        # Usar ucr_company_id (que tem fallback) em vez de active_company_id
        # (que pode ser None) para procurar a associação actualizada
        lookup_company_id = ucr_company_id if company_specific_fields else active_company_id
        if lookup_company_id and refreshed_companies:
            active_assoc_refreshed = next(
                (c for c in refreshed_companies if c.get("company_id") == lookup_company_id),
                None
            )
            if active_assoc_refreshed:
                updated_user["active_company_id"] = active_company_id
                company_role = active_assoc_refreshed.get("role")
                updated_user["active_company_role"] = active_role_header_resp if active_role_header_resp else company_role
                updated_user["active_company_name"] = active_assoc_refreshed.get("company_name")
                updated_user["active_company_signature"] = active_assoc_refreshed.get("signature") if "signature" in active_assoc_refreshed else None
                updated_user["active_company_professional_phone"] = active_assoc_refreshed.get("professional_phone") if "professional_phone" in active_assoc_refreshed else None
                updated_user["active_company_job_title"] = active_assoc_refreshed.get("job_title") if "job_title" in active_assoc_refreshed else None
                updated_user["active_company_display_name"] = active_assoc_refreshed.get("display_name") if "display_name" in active_assoc_refreshed else None
                updated_user["companies"] = refreshed_companies
                # ── MERGE: Sobrepor campos globais com dados da empresa ativa ──
                if active_assoc_refreshed.get("professional_phone"):
                    updated_user["phone"] = active_assoc_refreshed["professional_phone"]
                if active_assoc_refreshed.get("signature"):
                    updated_user["email_signature"] = active_assoc_refreshed["signature"]
                if active_assoc_refreshed.get("display_name"):
                    updated_user["name"] = active_assoc_refreshed["display_name"]
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
