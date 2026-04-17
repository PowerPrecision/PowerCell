"""
Serviço para gestão de configurações do sistema
Carrega configurações da BD e permite actualizações via API
"""
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from database import db
from models.system_config import (
    SystemConfig, StorageConfig, EmailConfig, AIConfig, 
    TrelloConfig, SystemSettings, StorageProvider, CreditServicesConfig,
    DocumentRecipientsConfig, DSTIConfig, AutoDraftConfig, AuditTrailConfig
)

logger = logging.getLogger(__name__)

# Cache das configurações
_config_cache: Optional[SystemConfig] = None
_config_cache_time: Optional[datetime] = None
CACHE_TTL_SECONDS = 60  # Recarregar a cada 60 segundos


async def get_system_config() -> SystemConfig:
    """
    Obter configurações do sistema.
    Primeiro tenta carregar da BD, se não existir usa valores por defeito + env vars.
    """
    global _config_cache, _config_cache_time
    
    # Verificar cache
    if _config_cache and _config_cache_time:
        cache_age = (datetime.now(timezone.utc) - _config_cache_time).total_seconds()
        if cache_age < CACHE_TTL_SECONDS:
            return _config_cache
    
    # Carregar da BD
    config_doc = await db.system_config.find_one({"_id": "main"})
    
    if config_doc:
        # Remover _id para não causar problemas com Pydantic
        config_doc.pop("_id", None)
        try:
            config = SystemConfig(**config_doc)
        except Exception as e:
            logger.warning(f"Erro ao carregar config da BD: {e}")
            config = _build_default_config()
    else:
        # Criar configuração inicial com valores do .env
        config = _build_default_config()
        await save_system_config(config)
    
    # Actualizar cache
    _config_cache = config
    _config_cache_time = datetime.now(timezone.utc)
    
    return config


def _build_default_config() -> SystemConfig:
    """
    Construir configuração por defeito usando variáveis de ambiente.
    """
    return SystemConfig(
        storage=StorageConfig(
            provider=StorageProvider.ONEDRIVE if os.environ.get("ONEDRIVE_CLIENT_ID") else StorageProvider.NONE,
            onedrive_client_id=os.environ.get("ONEDRIVE_CLIENT_ID"),
            onedrive_client_secret=os.environ.get("ONEDRIVE_CLIENT_SECRET"),
            onedrive_tenant_id=os.environ.get("ONEDRIVE_TENANT_ID", "common"),
            onedrive_redirect_uri=os.environ.get("ONEDRIVE_REDIRECT_URI"),
            onedrive_shared_url=os.environ.get("ONEDRIVE_SHARED_URL"),
        ),
        email=EmailConfig(
            provider="smtp" if os.environ.get("SMTP_SERVER") else "none",
            smtp_server=os.environ.get("SMTP_SERVER"),
            smtp_port=int(os.environ.get("SMTP_PORT", "465")),
            smtp_user=os.environ.get("SMTP_USER"),
            smtp_password=os.environ.get("SMTP_PASSWORD"),
            imap_server=os.environ.get("IMAP_SERVER"),
            imap_port=int(os.environ.get("IMAP_PORT", "993")),
            imap_user=os.environ.get("IMAP_USER"),
            imap_password=os.environ.get("IMAP_PASSWORD"),
        ),
        ai=AIConfig(
            provider="openai",
            api_key=os.environ.get("OPENAI_API_KEY") or os.environ.get("EMERGENT_LLM_KEY"),
            model="gpt-4o-mini",
        ),
        trello=TrelloConfig(
            enabled=bool(os.environ.get("TRELLO_API_KEY")),
            api_key=os.environ.get("TRELLO_API_KEY"),
            api_token=os.environ.get("TRELLO_API_TOKEN"),
            board_id=os.environ.get("TRELLO_BOARD_ID"),
            webhook_base_url=os.environ.get("WEBHOOK_BASE_URL"),
        ),
        settings=SystemSettings(),
        setup_completed=False,
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


async def save_system_config(config: SystemConfig) -> bool:
    """
    Guardar configurações do sistema na BD.
    """
    global _config_cache, _config_cache_time
    
    try:
        config.updated_at = datetime.now(timezone.utc).isoformat()
        # mode='json' para garantir Enums são serializados como strings
        config_dict = config.model_dump(mode='json')
        config_dict["_id"] = "main"
        
        await db.system_config.replace_one(
            {"_id": "main"},
            config_dict,
            upsert=True
        )
        
        # Invalidar cache para forçar reload na próxima leitura
        _config_cache = None
        _config_cache_time = None
        
        logger.info("Configurações do sistema guardadas")
        return True
    except Exception as e:
        logger.error(f"Erro ao guardar configurações: {e}")
        return False


async def update_config_section(section: str, data: Dict[str, Any]) -> SystemConfig:
    """
    Actualizar uma secção específica da configuração.
    Ignora campos com valores mascarados (••••••••) para não sobrescrever credenciais.
    """
    config = await get_system_config()
    
    # Lista de campos sensíveis que são mascarados na API
    sensitive_fields = [
        "aws_secret_access_key", "onedrive_client_secret", "google_client_secret", 
        "dropbox_app_secret", "smtp_password", "imap_password",
        "smtp_password_2", "imap_password_2",
        "api_key", "api_token", "dropbox_access_token",
        "hcpro_password", "decisoes_password", "doutorfinancas_password", "custom_portal_password"
    ]
    
    # Remover campos mascarados dos dados recebidos
    # Assim não sobrescrevemos as credenciais reais com o valor mascarado
    filtered_data = {
        k: v for k, v in data.items() 
        if not (k in sensitive_fields and v == "••••••••")
    }
    
    if section == "storage":
        # Actualizar campos de storage
        current = config.storage.model_dump()
        current.update(filtered_data)
        config.storage = StorageConfig(**current)
    elif section == "email":
        current = config.email.model_dump()
        current.update(filtered_data)
        config.email = EmailConfig(**current)
    elif section == "ai":
        current = config.ai.model_dump()
        current.update(filtered_data)
        config.ai = AIConfig(**current)
    elif section == "trello":
        current = config.trello.model_dump()
        current.update(filtered_data)
        config.trello = TrelloConfig(**current)
        
        # Sincronizar com trello_service em tempo real
        try:
            from services.trello import trello_service
            if config.trello.enabled:
                # Actualizar a instância global do TrelloService
                if config.trello.api_key:
                    trello_service.api_key = config.trello.api_key
                if config.trello.api_token:
                    trello_service.token = config.trello.api_token
                if config.trello.board_id:
                    trello_service.board_id = config.trello.board_id
                logger.info(f"TrelloService atualizado com novas credenciais - Board: {config.trello.board_id}")
        except ImportError:
            logger.warning("Não foi possível sincronizar com trello_service")
    elif section == "settings":
        current = config.settings.model_dump()
        current.update(filtered_data)
        config.settings = SystemSettings(**current)
    elif section == "credit_services":
        current = config.credit_services.model_dump()
        current.update(filtered_data)
        config.credit_services = CreditServicesConfig(**current)
    elif section == "document_recipients":
        import json
        current = config.document_recipients.model_dump()
        current.update(filtered_data)
        # Se recipients é uma lista, converter para JSON string
        if isinstance(current.get("recipients"), list):
            current["recipients"] = json.dumps(current["recipients"], ensure_ascii=False)
        # Garantir que default_to_emails é uma string JSON válida
        dto = current.get("default_to_emails")
        if isinstance(dto, list):
            current["default_to_emails"] = json.dumps(dto, ensure_ascii=False)
        elif isinstance(dto, str) and dto.strip():
            try:
                parsed = json.loads(dto)
                if not isinstance(parsed, list):
                    logger.warning(f"default_to_emails não é lista: {dto[:100]}")
            except json.JSONDecodeError:
                logger.warning(f"default_to_emails inválido: {dto[:100]}")
        logger.info(f"Saving document_recipients: default_to_emails={str(current.get('default_to_emails', 'MISSING'))[:200]}")
        config.document_recipients = DocumentRecipientsConfig(**current)
    elif section == "auto_draft":
        current = config.auto_draft.model_dump()
        current.update(filtered_data)
        # Se eligible_doc_types é uma string, tentar parsear para lista
        if isinstance(current.get("eligible_doc_types"), str):
            import json
            try:
                current["eligible_doc_types"] = json.loads(current["eligible_doc_types"])
            except json.JSONDecodeError:
                logger.warning("eligible_doc_types não é um JSON válido, a manter valor original")
        config.auto_draft = AutoDraftConfig(**current)
    elif section == "dsti_analysis":
        current = config.dsti_analysis.model_dump()
        current.update(filtered_data)
        config.dsti_analysis = DSTIConfig(**current)
    elif section == "audit_trail":
        current = config.audit_trail.model_dump()
        current.update(filtered_data)
        # Se critical_fields é uma string, tentar parsear para lista
        if isinstance(current.get("critical_fields"), str):
            import json
            try:
                current["critical_fields"] = json.loads(current["critical_fields"])
            except json.JSONDecodeError:
                logger.warning("critical_fields não é um JSON válido, a manter valor original")
        config.audit_trail = AuditTrailConfig(**current)
    else:
        raise ValueError(f"Secção desconhecida: {section}")
    
    save_result = await save_system_config(config)
    if not save_result:
        raise Exception(f"Falha ao guardar configuração '{section}' na base de dados")
    return config


async def get_storage_provider():
    """
    Obter o provider de armazenamento actualmente configurado.
    """
    config = await get_system_config()
    return config.storage.provider


async def get_ai_config() -> AIConfig:
    """
    Obter configuração de IA.
    """
    config = await get_system_config()
    return config.ai


async def is_setup_completed() -> bool:
    """
    Verificar se a configuração inicial foi concluída.
    """
    config = await get_system_config()
    return config.setup_completed


async def mark_setup_completed():
    """
    Marcar a configuração inicial como concluída.
    """
    config = await get_system_config()
    config.setup_completed = True
    await save_system_config(config)


def invalidate_config_cache():
    """
    Invalidar o cache de configurações.
    Útil após actualizações.
    """
    global _config_cache, _config_cache_time
    _config_cache = None
    _config_cache_time = None
