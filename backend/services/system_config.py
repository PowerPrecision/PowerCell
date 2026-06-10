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
    SystemSettings, StorageProvider, CreditServicesConfig,
    DocumentRecipientsConfig, DSTIConfig, AutoDraftConfig, AuditTrailConfig,
    SystemSMTPConfig, SystemWebmailConfig
)

logger = logging.getLogger(__name__)

# Cache das configurações — agora suporta múltiplas empresas
# Chave: company_id (str), Valor: (SystemConfig, datetime)
_config_cache: Dict[str, tuple] = {}
CACHE_TTL_SECONDS = 60  # Recarregar a cada 60 segundos


def _config_doc_id(company_id: str = "default") -> str:
    """Converte company_id para _id do documento MongoDB.

    - "default" → "main" (retrocompatibilidade com config global existente)
    - qualquer outro → "company:<company_id>"
    """
    if company_id == "default" or not company_id:
        return "main"
    return f"company:{company_id}"


async def get_system_config(company_id: str = "default") -> SystemConfig:
    """
    Obter configurações do sistema para uma empresa específica.

    MULTI-EMPRESA:
      - company_id="default" → config global (retrocompatível, _id="main")
      - company_id="power_real_estate" → config específica dessa empresa
      - Se não existir config para a empresa, cria uma cópia da global
        com o company_id preenchido.
    """
    cache_key = company_id or "default"

    # Verificar cache
    if cache_key in _config_cache:
        cached_config, cache_time = _config_cache[cache_key]
        cache_age = (datetime.now(timezone.utc) - cache_time).total_seconds()
        if cache_age < CACHE_TTL_SECONDS:
            return cached_config

    doc_id = _config_doc_id(cache_key)

    # Carregar da BD
    config_doc = await db.system_config.find_one({"_id": doc_id})

    if config_doc:
        # Remover _id para não causar problemas com Pydantic
        config_doc.pop("_id", None)
        try:
            config = SystemConfig(**config_doc)
        except Exception as e:
            logger.warning(f"Erro ao carregar config da BD (company_id={cache_key}): {e}")
            config = _build_default_config(cache_key)
    else:
        if cache_key == "default":
            # Criar configuração inicial com valores do .env
            config = _build_default_config(cache_key)
            await save_system_config(config)
        else:
            # Empresa sem config própria → herdar da global e criar cópia
            global_config = await get_system_config("default")
            config_data = global_config.model_dump(mode='json')
            config_data["company_id"] = cache_key
            config_data.pop("setup_completed", None)  # Não copiar flag de setup
            config = SystemConfig(**config_data)
            await save_system_config(config)
            logger.info(f"Criada config para empresa '{cache_key}' (herdada da global)")

    # Actualizar cache
    _config_cache[cache_key] = (config, datetime.now(timezone.utc))

    return config


def _build_default_config(company_id: str = "default") -> SystemConfig:
    """
    Construir configuração por defeito usando variáveis de ambiente.
    """
    return SystemConfig(
        company_id=company_id,
        storage=StorageConfig(
            provider=StorageProvider.AWS_S3 if os.environ.get("AWS_ACCESS_KEY_ID") else (StorageProvider.ONEDRIVE if os.environ.get("ONEDRIVE_CLIENT_ID") else StorageProvider.NONE),
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            aws_bucket_name=os.environ.get("AWS_BUCKET_NAME"),
            aws_region=os.environ.get("AWS_REGION", "eu-west-3"),
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
        settings=SystemSettings(),
        setup_completed=False,
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


async def save_system_config(config: SystemConfig) -> bool:
    """
    Guardar configurações do sistema na BD.
    Usa o company_id para determinar o _id do documento.
    """
    try:
        config.updated_at = datetime.now(timezone.utc).isoformat()
        # mode='json' para garantir Enums são serializados como strings
        config_dict = config.model_dump(mode='json')
        doc_id = _config_doc_id(config.company_id or "default")
        config_dict["_id"] = doc_id

        await db.system_config.replace_one(
            {"_id": doc_id},
            config_dict,
            upsert=True
        )

        # Invalidar cache para forçar reload na próxima leitura
        cache_key = config.company_id or "default"
        _config_cache.pop(cache_key, None)

        logger.info(f"Configurações do sistema guardadas (company_id={cache_key})")
        return True
    except Exception as e:
        logger.error(f"Erro ao guardar configurações: {e}")
        return False


async def update_config_section(section: str, data: Dict[str, Any], company_id: str = "default") -> SystemConfig:
    """
    Actualizar uma secção específica da configuração.
    Ignora campos com valores mascarados (••••••••) para não sobrescrever credenciais.

    MULTI-EMPRESA: o parâmetro company_id determina qual config carregar/guardar.
    """
    config = await get_system_config(company_id)
    
    # Lista de campos sensíveis que são mascarados na API
    sensitive_fields = [
        "aws_secret_access_key", "onedrive_client_secret", "google_client_secret", 
        "dropbox_app_secret", "smtp_password", "imap_password",
        "smtp_password_2", "imap_password_2",
        "smtp_password_system", "app_password",
        "api_key", "api_token", "dropbox_access_token",
        "hcpro_password", "decisoes_password", "doutorfinancas_password", "custom_portal_password",
        "resend_api_key",  # system_smtp — impede sobrescrever API key com valor mascarado
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
        
        # ── SYNC: Reconfigurar S3Service em tempo real ──
        try:
            from services.s3_storage import s3_service
            storage = config.storage
            if (storage.provider == StorageProvider.AWS_S3 
                and storage.aws_access_key_id 
                and storage.aws_secret_access_key 
                and storage.aws_bucket_name):
                s3_service.reconfigure(
                    access_key=storage.aws_access_key_id,
                    secret_key=storage.aws_secret_access_key,
                    bucket_name=storage.aws_bucket_name,
                    region=storage.aws_region or "eu-west-3"
                )
                logger.info(f"S3Service reconfigurado via UI — Bucket: {storage.aws_bucket_name}")
            elif storage.provider != StorageProvider.AWS_S3:
                # Se mudou para outro provider, desativar S3
                s3_service.s3_client = None
                s3_service.bucket_name = None
                logger.info("S3Service desativado (provider alterado)")
        except ImportError:
            logger.warning("Não foi possível sincronizar com s3_service")
        except Exception as e:
            logger.warning(f"Erro ao sincronizar S3Service: {e}")
    elif section == "email":
        current = config.email.model_dump()
        current.update(filtered_data)
        config.email = EmailConfig(**current)
    elif section == "ai":
        current = config.ai.model_dump()
        current.update(filtered_data)
        config.ai = AIConfig(**current)
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
        # Se eligible_doc_types é uma string, converter para lista
        # Suporta tanto formato JSON como formato separado por vírgulas
        if isinstance(current.get("eligible_doc_types"), str):
            raw = current["eligible_doc_types"].strip()
            if not raw:
                current["eligible_doc_types"] = []
            else:
                # Tentar JSON primeiro (compatibilidade retroativa)
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        current["eligible_doc_types"] = parsed
                    else:
                        # Fallback: separar por vírgulas
                        current["eligible_doc_types"] = [s.strip() for s in raw.split(",") if s.strip()]
                except (json.JSONDecodeError, ValueError):
                    # Formato separado por vírgulas: "irs, recibo_vencimento, cc"
                    current["eligible_doc_types"] = [s.strip() for s in raw.split(",") if s.strip()]
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
            raw = current["critical_fields"].strip()
            if not raw:
                current["critical_fields"] = ["financial_data", "credit_data", "status"]
            else:
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, list):
                        current["critical_fields"] = parsed
                    else:
                        logger.warning(f"critical_fields não é uma lista: {type(parsed)}, a usar default")
                        current["critical_fields"] = ["financial_data", "credit_data", "status"]
                except json.JSONDecodeError:
                    logger.warning(f"critical_fields não é JSON válido: '{raw[:100]}', a usar default")
                    current["critical_fields"] = ["financial_data", "credit_data", "status"]
        # retention_days pode vir como string do frontend
        if isinstance(current.get("retention_days"), str):
            try:
                current["retention_days"] = int(current["retention_days"])
            except (ValueError, TypeError):
                current["retention_days"] = 365
        config.audit_trail = AuditTrailConfig(**current)
    elif section == "system_smtp":
        current = config.system_smtp.model_dump()
        current.update(filtered_data)
        config.system_smtp = SystemSMTPConfig(**current)
    elif section == "system_webmail":
        current = config.system_webmail.model_dump()
        current.update(filtered_data)
        config.system_webmail = SystemWebmailConfig(**current)
    else:
        raise ValueError(f"Secção desconhecida: {section}")
    
    save_result = await save_system_config(config)
    if not save_result:
        raise Exception(f"Falha ao guardar configuração '{section}' na base de dados")
    return config


async def get_storage_provider(company_id: str = "default"):
    """
    Obter o provider de armazenamento actualmente configurado.
    """
    config = await get_system_config(company_id)
    return config.storage.provider


async def get_ai_config(company_id: str = "default") -> AIConfig:
    """
    Obter configuração de IA.
    """
    config = await get_system_config(company_id)
    return config.ai


async def is_setup_completed(company_id: str = "default") -> bool:
    """
    Verificar se a configuração inicial foi concluída.
    """
    config = await get_system_config(company_id)
    return config.setup_completed


async def mark_setup_completed(company_id: str = "default"):
    """
    Marcar a configuração inicial como concluída.
    """
    config = await get_system_config(company_id)
    config.setup_completed = True
    await save_system_config(config)


def invalidate_config_cache(company_id: str = None):
    """
    Invalidar o cache de configurações.
    Se company_id for fornecido, invalida apenas essa empresa.
    Se for None, invalida todo o cache.
    """
    if company_id:
        _config_cache.pop(company_id, None)
    else:
        _config_cache.clear()


async def list_available_companies() -> list:
    """
    Lista os company_ids com configuração própria no sistema.
    Inclui sempre "default" (global).
    """
    docs = await db.system_config.find(
        {},
        {"_id": 1, "company_id": 1, "settings.company_name": 1}
    ).to_list(100)

    result = []
    for doc in docs:
        cid = doc.get("company_id", "default")
        company_name = doc.get("settings", {}).get("company_name", cid)
        result.append({
            "company_id": cid,
            "company_name": company_name,
        })

    # Garantir que "default" está presente
    if not any(r["company_id"] == "default" for r in result):
        result.insert(0, {"company_id": "default", "company_name": "Global (Padrão)"})

    return result
