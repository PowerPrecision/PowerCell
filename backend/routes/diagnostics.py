"""
====================================================================
ROTAS DE DIAGNÓSTICO - SISTEMA
====================================================================
Endpoints para verificar o estado e configuração dos serviços.

Fornece informações sobre:
- Estado de configuração de cada serviço
- Últimas operações/erros
- Estatísticas de uso
====================================================================
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from database import db
from models.auth import UserRole
from services.auth import require_roles, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diagnostics", tags=["Diagnósticos"])


def datetime_to_str(value: Any) -> Optional[str]:
    """Converte datetime ou qualquer valor para string ISO segura."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class ServiceStatus(BaseModel):
    """Estado de um serviço."""
    name: str
    configured: bool
    status: str  # "ok", "warning", "error", "not_configured"
    message: str
    last_activity: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None
    config_fields: Optional[List[str]] = None  # Campos que faltam configurar


class SystemDiagnostics(BaseModel):
    """Diagnóstico completo do sistema."""
    timestamp: str
    services: Dict[str, ServiceStatus]
    recent_errors: List[Dict[str, Any]]
    summary: Dict[str, int]


async def check_email_service() -> ServiceStatus:
    """Verificar estado do serviço de email."""
    config = await db.system_config.find_one({}, {"_id": 0, "email": 1})
    email_config = config.get("email", {}) if config else {}
    
    # Verificar campos obrigatórios (usar nomes corretos do modelo)
    # Nota: smtp_server é o nome correto (não smtp_host)
    required = ["smtp_server", "smtp_port", "smtp_user", "smtp_password"]
    missing = [f for f in required if not email_config.get(f)]
    
    # Se não tem configuração completa, verificar se tem pelo menos uma conta secundária
    if missing:
        # Verificar conta secundária (smtp_server_2, etc.)
        required_2 = ["smtp_server_2", "smtp_port_2", "smtp_user_2", "smtp_password_2"]
        has_secondary = all(email_config.get(f) for f in required_2)
        
        if not has_secondary:
            return ServiceStatus(
                name="Email (SMTP)",
                configured=False,
                status="not_configured",
                message=f"Campos em falta: {', '.join(missing)}",
                config_fields=missing
            )
    
    # Contar emails enviados
    total_emails = await db.emails.count_documents({})
    last_email = await db.emails.find_one(
        {},
        {"_id": 0, "created_at": 1, "subject": 1},
        sort=[("created_at", -1)]
    )
    
    return ServiceStatus(
        name="Email (SMTP)",
        configured=True,
        status="ok",
        message="Serviço configurado",
        last_activity=datetime_to_str(last_email.get("created_at")) if last_email else None,
        stats={
            "total_emails": total_emails,
            "last_email_subject": last_email.get("subject", "N/A") if last_email else None
        }
    )


async def check_storage_service() -> ServiceStatus:
    """Verificar estado do serviço de armazenamento (S3 ou OneDrive)."""
    config = await db.system_config.find_one({}, {"_id": 0, "storage": 1})
    storage_config = config.get("storage", {}) if config else {}
    
    provider = storage_config.get("provider", "")
    
    if provider == "aws_s3":
        required = ["aws_access_key_id", "aws_secret_access_key", "aws_bucket_name"]
        missing = [f for f in required if not storage_config.get(f)]
        
        if missing:
            return ServiceStatus(
                name="Armazenamento (AWS S3)",
                configured=False,
                status="not_configured",
                message=f"Campos em falta: {', '.join(missing)}",
                config_fields=missing
            )
        
        # Contar documentos
        total_docs = await db.documents.count_documents({})
        
        return ServiceStatus(
            name="Armazenamento (AWS S3)",
            configured=True,
            status="ok",
            message=f"Bucket: {storage_config.get('aws_bucket_name', 'N/A')}",
            stats={"total_documents": total_docs}
        )
    
    elif provider == "onedrive":
        # OneDrive é opcional - apenas mostrar status informativo
        if not storage_config.get("onedrive_shared_url"):
            return ServiceStatus(
                name="Armazenamento (OneDrive)",
                configured=False,
                status="not_configured",
                message="OneDrive não configurado (opcional - use AWS S3 como principal)",
                config_fields=["onedrive_shared_url"]
            )
        
        return ServiceStatus(
            name="Armazenamento (OneDrive)",
            configured=True,
            status="ok",
            message="OneDrive configurado"
        )
    
    elif provider == "none" or not provider:
        # Nenhum provider configurado - mostrar como informação
        return ServiceStatus(
            name="Armazenamento",
            configured=False,
            status="not_configured",
            message="Configure AWS S3 para armazenamento de documentos",
            config_fields=["provider"]
        )
    
    # Outros providers
    return ServiceStatus(
        name=f"Armazenamento ({provider})",
        configured=True,
        status="ok",
        message=f"Provider: {provider}"
    )


async def check_ai_service() -> ServiceStatus:
    """Verificar estado do serviço de IA."""
    config = await db.system_config.find_one({}, {"_id": 0, "ai": 1})
    ai_config = config.get("ai", {}) if config else {}
    
    if not ai_config.get("api_key"):
        return ServiceStatus(
            name="Inteligência Artificial",
            configured=False,
            status="not_configured",
            message="Chave API não configurada",
            config_fields=["api_key"]
        )
    
    provider = ai_config.get("provider", "openai")
    model = ai_config.get("model", "gpt-4o-mini")
    
    # Contar análises feitas
    total_analyses = await db.ai_analyses.count_documents({}) if "ai_analyses" in await db.list_collection_names() else 0
    
    return ServiceStatus(
        name="Inteligência Artificial",
        configured=True,
        status="ok",
        message=f"Provider: {provider}, Modelo: {model}",
        stats={"total_analyses": total_analyses}
    )


async def check_trello_service() -> ServiceStatus:
    """Verificar estado do serviço Trello (DEPRECIADO - sempre desativado)."""
    # Trello foi removido como integração obrigatória
    # Retornar como desativado intencionalmente
    return ServiceStatus(
        name="Integração Trello",
        configured=True,
        status="disabled",
        message="Integração Trello desativada (não é necessária)",
    )


async def check_backup_service() -> ServiceStatus:
    """Verificar estado do serviço de backup."""
    # Verificar último backup
    last_backup = await db.backup_history.find_one(
        {"status": "completed"},
        {"_id": 0, "completed_at": 1, "result": 1},
        sort=[("completed_at", -1)]
    )
    
    total_backups = await db.backup_history.count_documents({"status": "completed"})
    
    if not last_backup:
        return ServiceStatus(
            name="Sistema de Backup",
            configured=True,
            status="warning",
            message="Nenhum backup realizado ainda",
            stats={"total_backups": 0}
        )
    
    # Verificar se o último backup foi há mais de 2 dias
    last_date_raw = last_backup.get("completed_at")
    last_date_str = None
    
    if last_date_raw:
        # Converter datetime para string se necessário
        if isinstance(last_date_raw, datetime):
            last_date_str = last_date_raw.isoformat()
        else:
            last_date_str = str(last_date_raw)
        
        try:
            # Parse para calcular dias
            if isinstance(last_date_raw, datetime):
                last_dt = last_date_raw
            else:
                last_dt = datetime.fromisoformat(str(last_date_raw).replace("Z", "+00:00"))
            
            # Garantir timezone awareness
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            
            days_ago = (datetime.now(timezone.utc) - last_dt).days
            
            if days_ago > 2:
                return ServiceStatus(
                    name="Sistema de Backup",
                    configured=True,
                    status="warning",
                    message=f"Último backup há {days_ago} dias",
                    last_activity=last_date_str,
                    stats={"total_backups": total_backups, "days_since_last": days_ago}
                )
        except Exception as e:
            logger.warning(f"Erro ao processar data do backup: {e}")
    
    return ServiceStatus(
        name="Sistema de Backup",
        configured=True,
        status="ok",
        message="Backup automático activo (03:00 UTC)",
        last_activity=last_date_str,
        stats={
            "total_backups": total_backups,
            "s3_uploaded": last_backup.get("result", {}).get("uploaded", False)
        }
    )


async def check_notifications_service() -> ServiceStatus:
    """Verificar estado do serviço de notificações."""
    # Verificar notificações recentes
    recent_count = await db.notifications.count_documents({
        "created_at": {"$gte": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()}
    }) if "notifications" in await db.list_collection_names() else 0
    
    total_count = await db.notifications.count_documents({}) if "notifications" in await db.list_collection_names() else 0
    
    return ServiceStatus(
        name="Notificações",
        configured=True,
        status="ok",
        message="Sistema de notificações activo",
        stats={
            "total": total_count,
            "last_7_days": recent_count
        }
    )


@router.get("", response_model=SystemDiagnostics)
async def get_system_diagnostics(
    _current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Obtém diagnóstico completo do sistema.
    
    Retorna o estado de todos os serviços e últimos erros.
    """
    services = {}
    
    # Verificar cada serviço com tratamento de erros
    try:
        services["email"] = await check_email_service()
    except Exception as e:
        logger.error(f"Erro ao verificar email: {e}")
        services["email"] = ServiceStatus(
            name="Email (SMTP)",
            configured=False,
            status="error",
            message=f"Erro ao verificar: {str(e)}"
        )
    
    try:
        services["storage"] = await check_storage_service()
    except Exception as e:
        logger.error(f"Erro ao verificar storage: {e}")
        services["storage"] = ServiceStatus(
            name="Armazenamento",
            configured=False,
            status="error",
            message=f"Erro ao verificar: {str(e)}"
        )
    
    try:
        services["ai"] = await check_ai_service()
    except Exception as e:
        logger.error(f"Erro ao verificar AI: {e}")
        services["ai"] = ServiceStatus(
            name="Inteligência Artificial",
            configured=False,
            status="error",
            message=f"Erro ao verificar: {str(e)}"
        )
    
    try:
        services["trello"] = await check_trello_service()
    except Exception as e:
        logger.error(f"Erro ao verificar Trello: {e}")
        services["trello"] = ServiceStatus(
            name="Integração Trello",
            configured=False,
            status="error",
            message=f"Erro ao verificar: {str(e)}"
        )
    
    try:
        services["backup"] = await check_backup_service()
    except Exception as e:
        logger.error(f"Erro ao verificar Backup: {e}")
        services["backup"] = ServiceStatus(
            name="Sistema de Backup",
            configured=False,
            status="error",
            message=f"Erro ao verificar: {str(e)}"
        )
    
    try:
        services["notifications"] = await check_notifications_service()
    except Exception as e:
        logger.error(f"Erro ao verificar Notifications: {e}")
        services["notifications"] = ServiceStatus(
            name="Notificações",
            configured=False,
            status="error",
            message=f"Erro ao verificar: {str(e)}"
        )
    
    # Buscar erros recentes
    recent_errors = []
    try:
        collections = await db.list_collection_names()
        if "system_error_logs" in collections:
            errors = await db.system_error_logs.find(
                {},
                {"_id": 0}
            ).sort("timestamp", -1).limit(10).to_list(10)
            recent_errors = errors
    except Exception as e:
        logger.error(f"Erro ao buscar logs de erros: {e}")
    
    # Resumo - não contar serviços desativados intencionalmente
    summary = {
        "ok": sum(1 for s in services.values() if s.status == "ok"),
        "warning": sum(1 for s in services.values() if s.status == "warning"),
        "error": sum(1 for s in services.values() if s.status == "error"),
        "not_configured": sum(1 for s in services.values() if s.status == "not_configured"),
        "disabled": sum(1 for s in services.values() if s.status == "disabled")
    }
    
    return SystemDiagnostics(
        timestamp=datetime.now(timezone.utc).isoformat(),
        services=services,
        recent_errors=recent_errors,
        summary=summary
    )


@router.get("/service/{service_name}")
async def get_service_diagnostics(
    service_name: str,
    _current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Obtém diagnóstico detalhado de um serviço específico.
    """
    checkers = {
        "email": check_email_service,
        "storage": check_storage_service,
        "ai": check_ai_service,
        "trello": check_trello_service,
        "backup": check_backup_service,
        "notifications": check_notifications_service
    }
    
    if service_name not in checkers:
        return {"error": f"Serviço '{service_name}' não encontrado", "available": list(checkers.keys())}
    
    status = await checkers[service_name]()
    
    # Adicionar informação extra dependendo do serviço
    extra_info = {}
    
    if service_name == "email":
        # Últimos 5 emails
        emails = await db.emails.find(
            {},
            {"_id": 0, "id": 1, "subject": 1, "to_address": 1, "created_at": 1, "status": 1}
        ).sort("created_at", -1).limit(5).to_list(5)
        extra_info["recent_emails"] = emails
        
    elif service_name == "backup":
        # Últimos 5 backups
        backups = await db.backup_history.find(
            {},
            {"_id": 0, "id": 1, "status": 1, "started_at": 1, "completed_at": 1, "trigger_type": 1}
        ).sort("started_at", -1).limit(5).to_list(5)
        extra_info["recent_backups"] = backups
    
    elif service_name == "trello":
        # Info de mapeamentos
        mappings_count = await db.trello_member_mappings.count_documents({}) if "trello_member_mappings" in await db.list_collection_names() else 0
        extra_info["member_mappings"] = mappings_count
    
    return {
        "service": status.dict(),
        "extra": extra_info,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/quick-check")
async def quick_system_check(
    _current_user: dict = Depends(get_current_user)
):
    """
    Verificação rápida do sistema (para qualquer utilizador staff).
    
    Retorna apenas o resumo sem detalhes sensíveis.
    Ignora serviços desativados intencionalmente (Trello).
    """
    services = {}
    
    # Verificar cada serviço (apenas status básico)
    services["email"] = (await check_email_service()).status
    services["storage"] = (await check_storage_service()).status
    services["ai"] = (await check_ai_service()).status
    # Trello ignorado - não é mais necessário
    services["backup"] = (await check_backup_service()).status
    
    # Contagens básicas
    stats = {
        "processes": await db.processes.count_documents({}),
        "users": await db.users.count_documents({}),
        "documents": await db.documents.count_documents({}) if "documents" in await db.list_collection_names() else 0
    }
    
    return {
        "status": "healthy" if all(s in ["ok", "warning"] for s in services.values()) else "issues",
        "services": services,
        "stats": stats,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/encryption")
async def check_encryption_status(
    _current_user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO]))
):
    """
    Verifica o estado do serviço de encriptação.
    
    Testa se a encriptação/desencriptação está a funcionar corretamente.
    """
    import os
    from services.encryption import encryption_service
    
    result = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "crypto_available": False,
        "fernet_initialized": False,
        "encryption_key_source": None,
        "test_encryption": None,
        "test_decryption": None,
        "can_decrypt_existing": None,
        "errors": []
    }
    
    # Verificar se cryptography está disponível
    try:
        from cryptography.fernet import Fernet
        result["crypto_available"] = True
    except ImportError:
        result["errors"].append("Biblioteca cryptography não instalada")
        return result
    
    # Verificar se Fernet está inicializado
    result["fernet_initialized"] = encryption_service._fernet is not None
    
    # Verificar origem da chave
    if os.environ.get("ENCRYPTION_KEY"):
        result["encryption_key_source"] = "ENCRYPTION_KEY"
        result["encryption_key_length"] = len(os.environ.get("ENCRYPTION_KEY"))
    elif os.environ.get("JWT_SECRET"):
        result["encryption_key_source"] = "JWT_SECRET"
        result["encryption_key_length"] = len(os.environ.get("JWT_SECRET"))
    else:
        result["encryption_key_source"] = "default"
        result["encryption_key_length"] = 0
        result["errors"].append("ENCRYPTION_KEY e JWT_SECRET não definidas - usando chave por defeito!")
    
    # Testar encriptação/desencriptação
    if encryption_service._fernet:
        try:
            test_value = "123456789"
            encrypted = encryption_service.encrypt(test_value)
            result["test_encryption"] = {
                "success": encrypted.startswith("ENC:"),
                "encrypted_length": len(encrypted)
            }
            
            # Testar desencriptação
            decrypted = encryption_service.decrypt(encrypted)
            result["test_decryption"] = {
                "success": decrypted == test_value,
                "decrypted_value": decrypted[:3] + "..." if decrypted else None
            }
        except Exception as e:
            result["errors"].append(f"Erro no teste de encriptação: {str(e)}")
    
    # Tentar desencriptar um valor existente da base de dados
    try:
        # Buscar um cliente com NIF encriptado
        client = await db.clients.find_one(
            {"dados_pessoais.nif": {"$regex": "^ENC:"}},
            {"_id": 0, "id": 1, "nome": 1, "dados_pessoais.nif": 1}
        )
        
        if client:
            encrypted_nif = client.get("dados_pessoais", {}).get("nif", "")
            if encrypted_nif and encrypted_nif.startswith("ENC:"):
                decrypted_nif = encryption_service.decrypt(encrypted_nif)
                result["can_decrypt_existing"] = {
                    "found": True,
                    "client_id": client.get("id"),
                    "client_name": client.get("nome"),
                    "encrypted_prefix": encrypted_nif[:20] + "...",
                    "decrypted_length": len(decrypted_nif) if decrypted_nif else 0,
                    "decryption_success": not decrypted_nif.startswith("ENC:") if decrypted_nif else False
                }
        else:
            result["can_decrypt_existing"] = {"found": False, "message": "Nenhum cliente com NIF encriptado encontrado"}
    except Exception as e:
        result["errors"].append(f"Erro ao testar desencriptação de dados existentes: {str(e)}")
    
    return result
