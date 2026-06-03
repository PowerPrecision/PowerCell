"""
====================================================================
SERVIÇO DE CONFLITOS DE DADOS — OCR vs. Dados do Cliente
====================================================================
Quando o AI OCR extrai dados de um documento (CC, IRS, etc.), este
serviço compara os dados extraídos com os dados atuais do processo
e cria sugestões de conflito na coleção `data_suggestions`.

O DataConflictResolver no frontend lê estas sugestões e permite ao
utilizador escolher qual valor manter.

FLUXO:
1. Upload de documento → auto_categorize_document_background
2. OCR extrai entidades (NIF, Nome, Morada, etc.)
3. create_conflict_suggestions() compara e cria conflitos
4. Frontend faz polling de /processes/{id}/data-suggestions
5. Utilizador resolve conflitos via DataConflictResolver
6. PUT /clients/{id} actualiza a ficha do cliente
====================================================================
"""
import logging
import uuid
from datetime import datetime, timezone
from database import db

logger = logging.getLogger(__name__)


# Campos do processo que correspondem a chaves extraídas pelo OCR
FIELD_MAPPING = {
    "nome": ["personal_data.nome", "personal_data.nome_completo", "client_name"],
    "nome_completo": ["personal_data.nome_completo", "personal_data.nome", "client_name"],
    "nif": ["personal_data.nif", "client_nif"],
    "documento_id": ["personal_data.documento_id", "personal_data.cc"],
    "morada": ["personal_data.morada", "personal_data.morada_fiscal"],
    "morada_fiscal": ["personal_data.morada_fiscal", "personal_data.morada"],
    "data_nascimento": ["personal_data.data_nascimento", "personal_data.birth_date"],
    "birth_date": ["personal_data.birth_date", "personal_data.data_nascimento"],
    "estado_civil": ["personal_data.estado_civil"],
    "nacionalidade": ["personal_data.nacionalidade"],
    "naturalidade": ["personal_data.naturalidade"],
    "data_validade_cc": ["personal_data.data_validade_cc"],
    "sexo": ["personal_data.sexo"],
}


def _get_nested_value(data: dict, path: str):
    """Obtém valor aninhado via notação de ponto (ex: 'personal_data.nif')."""
    keys = path.split(".")
    value = data
    for key in keys:
        if isinstance(value, dict):
            value = value.get(key)
        else:
            return None
    return value


def _normalize_for_comparison(value) -> str:
    """Normaliza valor para comparação (lowercase, sem espaços extra, sem acentos básicos)."""
    if value is None:
        return ""
    s = str(value).strip().lower()
    # Remover espaços múltiplos
    import re
    s = re.sub(r'\s+', ' ', s)
    return s


async def create_conflict_suggestions(
    process_id: str,
    extracted_data: dict,
    filename: str,
    doc_id: str = None
) -> int:
    """
    Compara dados extraídos pelo OCR com dados atuais do processo
    e cria sugestões de conflito para campos que diferem.
    
    Args:
        process_id: ID do processo.
        extracted_data: Dict com dados extraídos pelo OCR.
        filename: Nome do ficheiro que originou os dados.
        doc_id: ID do documento nos metadados.
    
    Returns:
        Número de conflitos criados.
    """
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        return 0
    
    # Se os dados já foram confirmados, não criar conflitos
    if process.get("is_data_confirmed"):
        logger.info(f"[DATA-CONFLICT] Dados já confirmados para processo {process_id}, a saltar OCR")
        return 0
    
    now = datetime.now(timezone.utc).isoformat()
    conflicts_created = 0
    
    for ocr_key, ocr_value in extracted_data.items():
        if ocr_value is None or ocr_value == "":
            continue
        
        # Mapear chave OCR para campos do processo
        process_paths = FIELD_MAPPING.get(ocr_key, [])
        if not process_paths:
            # Tentar mapeamento directo
            process_paths = [f"personal_data.{ocr_key}"]
        
        # Obter valor atual do processo
        current_value = None
        matched_path = None
        for path in process_paths:
            val = _get_nested_value(process, path)
            if val is not None and val != "":
                current_value = val
                matched_path = path
                break
        
        # Se não há valor atual, não há conflito (é apenas novo dado)
        if current_value is None or current_value == "":
            continue
        
        # Comparar valores normalizados
        norm_current = _normalize_for_comparison(current_value)
        norm_ocr = _normalize_for_comparison(ocr_value)
        
        if norm_current == norm_ocr:
            continue  # Valores iguais, sem conflito
        
        # Verificar se já existe uma sugestão pendente para este campo
        existing = await db.data_suggestions.find_one({
            "process_id": process_id,
            "field": ocr_key,
            "resolved": False,
        })
        
        if existing:
            # Atualizar a sugestão existente com o novo valor OCR
            await db.data_suggestions.update_one(
                {"id": existing["id"]},
                {"$set": {
                    "suggested": str(ocr_value),
                    "document": filename,
                    "document_id": doc_id,
                    "detected_at": now,
                    "updated_at": now,
                }}
            )
            conflicts_created += 1
            continue
        
        # Criar nova sugestão de conflito
        suggestion = {
            "id": str(uuid.uuid4()),
            "process_id": process_id,
            "field": ocr_key,
            "field_path": matched_path,
            "current": str(current_value),
            "suggested": str(ocr_value),
            "document": filename,
            "document_id": doc_id,
            "resolved": False,
            "choice": None,
            "detected_at": now,
            "created_at": now,
            "updated_at": now,
        }
        
        await db.data_suggestions.insert_one(suggestion)
        conflicts_created += 1
        logger.info(f"[DATA-CONFLICT] Novo conflito: {ocr_key} = '{current_value}' vs OCR '{ocr_value}'")
    
    if conflicts_created > 0:
        logger.info(f"[DATA-CONFLICT] {conflicts_created} conflito(s) criado(s) para processo {process_id}")
    
    return conflicts_created


async def get_pending_suggestions(process_id: str) -> list:
    """Retorna sugestões pendentes para um processo."""
    suggestions = await db.data_suggestions.find(
        {"process_id": process_id, "resolved": False},
        {"_id": 0}
    ).sort("detected_at", -1).to_list(100)
    return suggestions


async def resolve_suggestion(suggestion_id: str, choice: str, user_id: str = None) -> dict:
    """
    Resolve uma sugestão de conflito e aplica a escolha ao processo.
    
    Args:
        suggestion_id: ID da sugestão.
        choice: 'current' (manter actual) ou 'ai' (aceitar valor da IA).
        user_id: ID do utilizador que resolveu o conflito.
    
    Returns:
        Dict com resultado da operação.
    """
    suggestion = await db.data_suggestions.find_one({"id": suggestion_id})
    if not suggestion:
        return {"success": False, "message": "Sugestão não encontrada"}
    
    now = datetime.now(timezone.utc).isoformat()
    
    if choice == "ai":
        # Aplicar o valor sugerido pela IA ao processo
        field_path = suggestion.get("field_path")
        if field_path and suggestion.get("suggested"):
            process = await db.processes.find_one({"id": suggestion["process_id"]}, {"_id": 0})
            if process:
                # Navegar e atualizar o campo aninhado
                keys = field_path.split(".")
                if len(keys) == 2:
                    parent_key, child_key = keys
                    parent_data = process.get(parent_key, {}) or {}
                    parent_data[child_key] = suggestion["suggested"]
                    await db.processes.update_one(
                        {"id": suggestion["process_id"]},
                        {"$set": {parent_key: parent_data, "updated_at": now}}
                    )
                elif len(keys) == 1:
                    await db.processes.update_one(
                        {"id": suggestion["process_id"]},
                        {"$set": {keys[0]: suggestion["suggested"], "updated_at": now}}
                    )
        
        final_value = suggestion["suggested"]
    else:
        final_value = suggestion["current"]
    
    # Marcar como resolvida
    await db.data_suggestions.update_one(
        {"id": suggestion_id},
        {"$set": {
            "resolved": True,
            "choice": choice,
            "resolved_by": user_id,
            "resolved_at": now,
            "updated_at": now,
        }}
    )
    
    return {
        "success": True,
        "message": f"Conflito resolvido: campo '{suggestion['field']}' = '{final_value}'",
        "field": suggestion["field"],
        "choice": choice,
        "final_value": final_value,
    }
