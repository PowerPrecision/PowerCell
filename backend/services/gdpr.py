"""
====================================================================
GDPR COMPLIANCE SERVICE - CREDITOIMO
====================================================================
Serviço de conformidade com o RGPD (Regulamento Geral de Proteção de Dados).

FUNCIONALIDADES:
- Anonimização de dados pessoais em processos antigos
- Direito ao esquecimento (right to be forgotten)
- Exportação de dados pessoais (data portability)
- Auditoria de acesso a dados sensíveis

CAMPOS ANONIMIZADOS:
- Nome completo → "CLIENTE_ANONIMO_XXXXX"
- Email → "deleted_XXXXX@anonimo.local"
- NIF → "XXXXXXXXX"
- Telefone → "XXXXXXXXX"
- Morada → "MORADA_ANONIMIZADA"
- Outros dados identificáveis

CAMPOS MANTIDOS (para estatísticas):
- Valores financeiros (montante, prestação, etc.)
- Datas (criação, actualização, etc.)
- Localização genérica (concelho, distrito)
- Estado do processo
- Tipo de processo/crédito

PERÍODO DE RETENÇÃO:
- Processos concluídos/desistidos: 2 anos (configurável)
- Documentos: removidos após anonimização

LEGAL:
- RGPD Artigo 17: Direito ao apagamento
- RGPD Artigo 5(1)(e): Limitação da conservação
====================================================================
"""
import os
import uuid
import hashlib
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass

from database import db

logger = logging.getLogger(__name__)


# ====================================================================
# CONFIGURAÇÃO
# ====================================================================
@dataclass
class GDPRConfig:
    """Configuração de retenção e anonimização."""
    
    # Período de retenção em dias (default: 2 anos = 730 dias)
    retention_period_days: int = int(os.environ.get("GDPR_RETENTION_DAYS", "730"))
    
    # Estados elegíveis para anonimização
    eligible_statuses: List[str] = None
    
    # Batch size para processamento
    batch_size: int = 100
    
    # Dry run (apenas logar, não anonimizar)
    dry_run: bool = os.environ.get("GDPR_DRY_RUN", "false").lower() == "true"
    
    def __post_init__(self):
        if self.eligible_statuses is None:
            self.eligible_statuses = [
                "desistencias",
                "desistência", 
                "desistencia",
                "concluido",
                "concluído",
                "escritura_realizada",
                "arquivado",
                "cancelado",
                "recusado"
            ]


# Instância global
gdpr_config = GDPRConfig()


# ====================================================================
# FUNÇÕES DE ANONIMIZAÇÃO
# ====================================================================
def generate_anonymous_id() -> str:
    """Gera ID anónimo único."""
    return hashlib.sha256(uuid.uuid4().bytes).hexdigest()[:12].upper()


def anonymize_name(original: str = None) -> str:
    """Anonimiza nome completo."""
    anon_id = generate_anonymous_id()
    return f"CLIENTE_ANONIMO_{anon_id}"


def anonymize_email(original: str = None) -> str:
    """Anonimiza email."""
    anon_id = generate_anonymous_id()
    return f"deleted_{anon_id}@anonimo.local"


def anonymize_phone(original: str = None) -> str:
    """Anonimiza telefone."""
    return "XXXXXXXXX"


def anonymize_nif(original: str = None) -> str:
    """Anonimiza NIF/número fiscal."""
    return "XXXXXXXXX"


def anonymize_address(original: str = None) -> str:
    """Anonimiza morada."""
    return "MORADA_ANONIMIZADA"


def anonymize_id_number(original: str = None) -> str:
    """Anonimiza número de documento de identificação."""
    return "XXXXXXXXX"


def anonymize_iban(original: str = None) -> str:
    """Anonimiza IBAN."""
    return "PTXX XXXX XXXX XXXX XXXX XXXXX"


# ====================================================================
# MAPEAMENTO DE CAMPOS A ANONIMIZAR
# ====================================================================
ANONYMIZATION_MAP = {
    # Campos de nível superior do processo
    "client_name": anonymize_name,
    "client_email": anonymize_email,
    "client_phone": anonymize_phone,
    
    # personal_data
    "personal_data.nome": anonymize_name,
    "personal_data.nome_completo": anonymize_name,
    "personal_data.email": anonymize_email,
    "personal_data.telefone": anonymize_phone,
    "personal_data.telemovel": anonymize_phone,
    "personal_data.nif": anonymize_nif,
    "personal_data.numero_cc": anonymize_id_number,
    "personal_data.numero_bi": anonymize_id_number,
    "personal_data.morada": anonymize_address,
    "personal_data.morada_completa": anonymize_address,
    "personal_data.codigo_postal": lambda x: "XXXX-XXX",
    
    # financial_data
    "financial_data.iban": anonymize_iban,
    "financial_data.conta_bancaria": anonymize_iban,
    
    # Dados do cônjuge/co-titular
    "personal_data.conjuge_nome": anonymize_name,
    "personal_data.conjuge_nif": anonymize_nif,
    "personal_data.conjuge_email": anonymize_email,
    "personal_data.conjuge_telefone": anonymize_phone,
    
    # Co-buyers (array)
    "co_buyers.*.nome": anonymize_name,
    "co_buyers.*.nif": anonymize_nif,
    "co_buyers.*.email": anonymize_email,
    "co_buyers.*.telefone": anonymize_phone,
    "co_buyers.*.morada": anonymize_address,
    
    # Vendedor (em CPCV)
    "vendedor.nome": anonymize_name,
    "vendedor.nif": anonymize_nif,
    "vendedor.email": anonymize_email,
    "vendedor.telefone": anonymize_phone,
    "vendedor.morada": anonymize_address,
    
    # Mediador
    "mediador.nome": anonymize_name,
    "mediador.nif": anonymize_nif,
    "mediador.email": anonymize_email,
    "mediador.contacto": anonymize_phone,
}

# Campos a REMOVER completamente (documentos, notas com dados pessoais)
FIELDS_TO_REMOVE = [
    "documents",           # Documentos anexados
    "analyzed_documents",  # Documentos analisados
    "ai_extracted_data",   # Dados extraídos por IA
    "notes_personal",      # Notas pessoais
    "attachments",         # Anexos
]


# ====================================================================
# FUNÇÕES PRINCIPAIS
# ====================================================================
def _set_nested_value(doc: dict, path: str, value: Any) -> dict:
    """Define valor num campo aninhado usando notação de pontos."""
    keys = path.split(".")
    current = doc
    
    for key in keys[:-1]:
        if key == "*":
            # Tratamento especial para arrays (feito noutra função)
            return doc
        if key not in current:
            return doc
        current = current[key]
    
    if keys[-1] in current:
        current[keys[-1]] = value
    
    return doc


def _get_nested_value(doc: dict, path: str) -> Any:
    """Obtém valor de um campo aninhado."""
    keys = path.split(".")
    current = doc
    
    for key in keys:
        if key == "*":
            return None
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    
    return current


def _anonymize_array_field(doc: dict, array_path: str, field_name: str, anonymize_func) -> dict:
    """Anonimiza campo dentro de um array."""
    keys = array_path.split(".")
    current = doc
    
    for key in keys:
        if key == "*":
            break
        if key not in current:
            return doc
        current = current[key]
    
    if isinstance(current, list):
        for item in current:
            if isinstance(item, dict) and field_name in item:
                item[field_name] = anonymize_func(item[field_name])
    
    return doc


async def anonymize_process_data(process_id: str, dry_run: bool = None) -> Dict[str, Any]:
    """
    Anonimiza dados pessoais de um processo.
    
    Args:
        process_id: ID do processo a anonimizar
        dry_run: Se True, apenas simula (não altera BD)
    
    Returns:
        Dict com resultado da operação
    """
    if dry_run is None:
        dry_run = gdpr_config.dry_run
    
    logger.info(f"[GDPR] {'[DRY RUN] ' if dry_run else ''}Iniciando anonimização do processo {process_id}")
    
    # Buscar processo
    process = await db.processes.find_one({"id": process_id})
    
    if not process:
        logger.warning(f"[GDPR] Processo não encontrado: {process_id}")
        return {
            "success": False,
            "process_id": process_id,
            "error": "Processo não encontrado"
        }
    
    # Verificar se já está anonimizado
    if process.get("is_anonymized"):
        logger.info(f"[GDPR] Processo já anonimizado: {process_id}")
        return {
            "success": True,
            "process_id": process_id,
            "already_anonymized": True
        }
    
    # Contar campos anonimizados
    fields_anonymized = []
    fields_removed = []
    
    # 1. Aplicar anonimização nos campos mapeados
    update_data = {}
    
    for field_path, anonymize_func in ANONYMIZATION_MAP.items():
        if "*" in field_path:
            # Campo em array
            parts = field_path.split(".*.")
            if len(parts) == 2:
                array_path, field_name = parts
                array_data = _get_nested_value(process, array_path)
                if array_data and isinstance(array_data, list):
                    for i, item in enumerate(array_data):
                        if isinstance(item, dict) and field_name in item:
                            update_data[f"{array_path}.{i}.{field_name}"] = anonymize_func(item.get(field_name))
                            fields_anonymized.append(f"{array_path}[{i}].{field_name}")
        else:
            # Campo simples ou aninhado
            current_value = _get_nested_value(process, field_path)
            if current_value is not None:
                new_value = anonymize_func(current_value)
                update_data[field_path] = new_value
                fields_anonymized.append(field_path)
    
    # 2. Remover campos sensíveis
    unset_data = {}
    for field in FIELDS_TO_REMOVE:
        if _get_nested_value(process, field) is not None:
            unset_data[field] = ""
            fields_removed.append(field)
    
    # 3. Adicionar metadados de anonimização
    anonymization_metadata = {
        "is_anonymized": True,
        "anonymized_at": datetime.now(timezone.utc),
        "anonymization_reason": "GDPR_RETENTION_PERIOD",
        "fields_anonymized": fields_anonymized,
        "fields_removed": fields_removed,
        "retention_days": gdpr_config.retention_period_days
    }
    update_data.update(anonymization_metadata)
    
    # 4. Executar actualização (se não for dry run)
    if not dry_run:
        update_query = {"$set": update_data}
        if unset_data:
            update_query["$unset"] = unset_data
        
        result = await db.processes.update_one(
            {"id": process_id},
            update_query
        )
        
        if result.modified_count == 0:
            logger.error(f"[GDPR] Falha ao anonimizar processo {process_id}")
            return {
                "success": False,
                "process_id": process_id,
                "error": "Falha na actualização"
            }
    
    logger.info(
        f"[GDPR] {'[DRY RUN] ' if dry_run else ''}Processo {process_id} anonimizado: "
        f"{len(fields_anonymized)} campos anonimizados, {len(fields_removed)} campos removidos"
    )
    
    # 5. Registar na auditoria
    if not dry_run:
        await db.gdpr_audit.insert_one({
            "action": "anonymize_process",
            "process_id": process_id,
            "fields_anonymized": fields_anonymized,
            "fields_removed": fields_removed,
            "timestamp": datetime.now(timezone.utc),
            "retention_days": gdpr_config.retention_period_days
        })
    
    return {
        "success": True,
        "process_id": process_id,
        "dry_run": dry_run,
        "fields_anonymized": len(fields_anonymized),
        "fields_removed": len(fields_removed),
        "details": {
            "anonymized": fields_anonymized,
            "removed": fields_removed
        }
    }


async def anonymize_user_data(user_id: str, dry_run: bool = None) -> Dict[str, Any]:
    """
    Anonimiza dados de um utilizador (para direito ao esquecimento).
    
    Args:
        user_id: ID do utilizador
        dry_run: Se True, apenas simula
    
    Returns:
        Dict com resultado
    """
    if dry_run is None:
        dry_run = gdpr_config.dry_run
    
    logger.info(f"[GDPR] {'[DRY RUN] ' if dry_run else ''}Anonimizando utilizador {user_id}")
    
    # Buscar utilizador
    user = await db.users.find_one({"id": user_id})
    
    if not user:
        return {"success": False, "error": "Utilizador não encontrado"}
    
    if user.get("is_anonymized"):
        return {"success": True, "already_anonymized": True}
    
    # Dados anonimizados
    anon_id = generate_anonymous_id()
    update_data = {
        "name": f"UTILIZADOR_ANONIMO_{anon_id}",
        "email": f"deleted_{anon_id}@anonimo.local",
        "phone": "XXXXXXXXX",
        "is_active": False,
        "is_anonymized": True,
        "anonymized_at": datetime.now(timezone.utc),
        "password": "",  # Invalida o login
    }
    
    if not dry_run:
        await db.users.update_one(
            {"id": user_id},
            {"$set": update_data}
        )
        
        # Auditoria
        await db.gdpr_audit.insert_one({
            "action": "anonymize_user",
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc)
        })
    
    return {
        "success": True,
        "user_id": user_id,
        "dry_run": dry_run
    }


# ====================================================================
# FUNÇÕES DE BUSCA E PROCESSAMENTO EM LOTE
# ====================================================================
async def find_processes_for_anonymization(
    retention_days: int = None,
    limit: int = None
) -> List[Dict[str, Any]]:
    """
    Encontra processos elegíveis para anonimização.
    
    Critérios:
    - Estado em lista de estados elegíveis
    - Data de actualização > período de retenção
    - Ainda não anonimizado
    
    Returns:
        Lista de processos elegíveis
    """
    if retention_days is None:
        retention_days = gdpr_config.retention_period_days
    
    if limit is None:
        limit = gdpr_config.batch_size
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
    
    query = {
        "status": {"$in": gdpr_config.eligible_statuses},
        "updated_at": {"$lt": cutoff_date},
        "$or": [
            {"is_anonymized": {"$exists": False}},
            {"is_anonymized": False}
        ]
    }
    
    processes = await db.processes.find(
        query,
        {"_id": 0, "id": 1, "client_name": 1, "status": 1, "updated_at": 1}
    ).limit(limit).to_list(limit)
    
    logger.info(f"[GDPR] Encontrados {len(processes)} processos para anonimização")
    
    return processes


async def run_anonymization_batch(
    retention_days: int = None,
    dry_run: bool = None,
    batch_size: int = None
) -> Dict[str, Any]:
    """
    Executa anonimização em lote.
    
    Returns:
        Estatísticas da execução
    """
    if dry_run is None:
        dry_run = gdpr_config.dry_run
    
    if batch_size is None:
        batch_size = gdpr_config.batch_size
    
    logger.info(f"[GDPR] Iniciando batch de anonimização (dry_run={dry_run})")
    
    # Encontrar processos elegíveis
    processes = await find_processes_for_anonymization(retention_days, batch_size)
    
    if not processes:
        logger.info("[GDPR] Nenhum processo para anonimizar")
        return {
            "success": True,
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "dry_run": dry_run
        }
    
    # Processar cada um
    results = {
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "errors": []
    }
    
    for process in processes:
        try:
            result = await anonymize_process_data(process["id"], dry_run)
            results["processed"] += 1
            
            if result.get("success"):
                results["succeeded"] += 1
            else:
                results["failed"] += 1
                results["errors"].append({
                    "process_id": process["id"],
                    "error": result.get("error")
                })
                
        except Exception as e:
            logger.error(f"[GDPR] Erro ao anonimizar {process['id']}: {str(e)}")
            results["failed"] += 1
            results["errors"].append({
                "process_id": process["id"],
                "error": str(e)
            })
    
    logger.info(
        f"[GDPR] Batch concluído: {results['succeeded']}/{results['processed']} sucesso, "
        f"{results['failed']} falhas"
    )
    
    return {
        "success": True,
        "dry_run": dry_run,
        **results
    }


# ====================================================================
# DIREITO À PORTABILIDADE (EXPORTAÇÃO DE DADOS)
# ====================================================================
async def export_personal_data(
    process_id: str = None,
    user_id: str = None
) -> Dict[str, Any]:
    """
    Exporta todos os dados pessoais de um cliente/utilizador.
    Implementa o direito à portabilidade (RGPD Art. 20).
    
    Returns:
        Dict com todos os dados pessoais em formato estruturado
    """
    export_data = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "format_version": "1.0",
        "data": {}
    }
    
    if process_id:
        process = await db.processes.find_one(
            {"id": process_id},
            {"_id": 0}
        )
        if process:
            # Remover campos internos
            process.pop("password", None)
            export_data["data"]["process"] = process
    
    if user_id:
        user = await db.users.find_one(
            {"id": user_id},
            {"_id": 0, "password": 0}
        )
        if user:
            export_data["data"]["user"] = user
    
    # Log de auditoria
    await db.gdpr_audit.insert_one({
        "action": "export_data",
        "process_id": process_id,
        "user_id": user_id,
        "timestamp": datetime.now(timezone.utc)
    })
    
    return export_data


# ====================================================================
# ESTATÍSTICAS GDPR
# ====================================================================
async def get_gdpr_statistics() -> Dict[str, Any]:
    """Obtém estatísticas de conformidade GDPR."""
    
    # Total de processos
    total_processes = await db.processes.count_documents({})
    
    # Processos anonimizados
    anonymized = await db.processes.count_documents({"is_anonymized": True})
    
    # Processos elegíveis para anonimização
    cutoff = datetime.now(timezone.utc) - timedelta(days=gdpr_config.retention_period_days)
    eligible = await db.processes.count_documents({
        "status": {"$in": gdpr_config.eligible_statuses},
        "updated_at": {"$lt": cutoff},
        "$or": [
            {"is_anonymized": {"$exists": False}},
            {"is_anonymized": False}
        ]
    })
    
    # Acções de auditoria recentes
    recent_audits = await db.gdpr_audit.count_documents({
        "timestamp": {"$gte": datetime.now(timezone.utc) - timedelta(days=30)}
    })
    
    return {
        "total_processes": total_processes,
        "anonymized_processes": anonymized,
        "eligible_for_anonymization": eligible,
        "anonymization_rate": round(anonymized / total_processes * 100, 2) if total_processes > 0 else 0,
        "recent_gdpr_actions": recent_audits,
        "retention_period_days": gdpr_config.retention_period_days,
        "dry_run_mode": gdpr_config.dry_run
    }
