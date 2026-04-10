"""
====================================================================
SERVIÇO DE PROCESSOS - CREDITOIMO
====================================================================
Lógica de negócio para gestão de processos.
Separado dos endpoints para facilitar manutenção e testes.

SEGURANÇA:
- Campos sensíveis (NIFs, telefones, moradas) são encriptados automaticamente
- A desencriptação é transparente na leitura
====================================================================
"""
import re
import uuid
import logging
import copy
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple

from database import db
from models.process import ProcessCreate, ProcessUpdate
from services.encryption import encryption_service

logger = logging.getLogger(__name__)


# ==== FUNÇÕES DE UTILIDADE ====

def sanitize_email(email: str) -> str:
    """
    Limpa emails com formatação markdown ou outros artefactos.
    Extrai o email puro de strings como '[email](mailto:email)' ou 'mailto:email'.
    """
    if not email:
        return ""
    
    email = email.strip()
    
    # Padrão: [texto](mailto:email) ou [email](mailto:email)
    markdown_link = re.search(r'\[.*?\]\(mailto:([^)]+)\)', email)
    if markdown_link:
        email = markdown_link.group(1)
    
    # Padrão: mailto:email
    if email.startswith('mailto:'):
        email = email.replace('mailto:', '')
    
    # Padrão: <email>
    angle_brackets = re.search(r'<([^>]+@[^>]+)>', email)
    if angle_brackets:
        email = angle_brackets.group(1)
    
    # Remover quaisquer caracteres markdown restantes
    email = re.sub(r'[\[\]\(\)]', '', email)
    
    # Validar formato básico de email
    email = email.strip().lower()
    if email and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email, re.IGNORECASE):
        logger.warning(f"Email inválido após sanitização: {email}")
        return ""
    
    return email


async def get_next_process_number() -> int:
    """
    Obtém o próximo número de processo baseado no maior existente.
    Usado para gerar referências como 'PROC-0001'.
    """
    latest = await db.processes.find_one(
        {"process_number": {"$exists": True}},
        sort=[("process_number", -1)],
        projection={"_id": 0, "process_number": 1}
    )
    if latest and latest.get("process_number"):
        return latest["process_number"] + 1
    return 1


# ==== FUNÇÕES DE VERIFICAÇÃO DE PERMISSÕES ====

def can_view_process(user: dict, process: dict) -> bool:
    """
    Verifica se o utilizador pode ver o processo baseado no seu papel.
    
    Regras:
    - Staff (admin, ceo, diretor, administrativo, consultor, mediador, intermediario, indexacao): 
      podem ver TODOS os processos da empresa
    - Indexação vê todos os processos para poder atribuir a consultores/intermediários
    - Clientes: apenas os seus próprios processos
    
    Args:
        user: Dados do utilizador actual
        process: Dados do processo
    
    Returns:
        True se pode ver, False caso contrário
    """
    user_role = user.get("role", "")
    user_id = user.get("id", "")
    
    # Todos os staff podem ver todos os processos
    # Indexação incluído pois precisa de ver todos para atribuir processos
    staff_roles = ["admin", "ceo", "diretor", "administrativo", "consultor", "mediador", "intermediario", "indexacao"]
    if user_role in staff_roles:
        return True
    
    # Cliente só vê os seus próprios processos
    if user_role == "cliente":
        return process.get("client_id") == user_id
    
    # Por defeito, negar acesso
    return False


def can_edit_process_data(user: dict, process: dict) -> tuple:
    """
    Verifica se o utilizador pode EDITAR dados do processo (dados pessoais, financeiros, etc.).
    
    Esta função é mais restritiva que can_view_process - apenas utilizadores
    com permissão de escrita podem modificar dados core do processo.
    
    SECURITY: Usada para prevenir IDOR em endpoints de resolução de conflitos
    e confirmação de dados de IA.
    
    Regras:
    - Staff com permissão 'edit_process': Podem editar processos atribuídos ou todos (admin/ceo)
    - INDEXACAO: NÃO pode editar dados core (apaz upload/atribuição)
    - CLIENTE: Apenas os seus próprios processos (se permitido pelo negócio)
    - PARCEIRO: Sem acesso
    
    Args:
        user: Dados do utilizador actual
        process: Dados do processo
    
    Returns:
        Tuple (can_edit: bool, reason: str)
    """
    user_role = user.get("role", "")
    user_id = user.get("id", "")
    user_permissions = user.get("permissions", {})
    user_actions = user_permissions.get("actions", []) if isinstance(user_permissions, dict) else []
    
    # Parceiros e clientes não têm permissão de edição via API
    if user_role in ["parceiro"]:
        return False, "Parceiros não têm acesso a esta funcionalidade"
    
    # Clientes só podem editar os seus próprios processos
    if user_role == "cliente":
        if process.get("client_id") != user_id:
            return False, "Apenas pode editar os seus próprios processos"
        # Clientes podem editar os seus dados - permitir
        return True, "OK"
    
    # INDEXACAO - Verificar se tem permissão explícita de edit_process
    # Por defeito, INDEXACAO não tem edit_process nas permissões padrão
    if user_role == "indexacao":
        # Verificar se tem permissão custom de edição
        if "edit_process" not in user_actions:
            return False, "Indexação não tem permissão para editar dados do processo"
    
    # Staff roles que podem editar (verificar se tem action edit_process)
    staff_edit_roles = ["admin", "ceo", "diretor", "administrativo", "consultor", "mediador", "intermediario"]
    
    if user_role in staff_edit_roles:
        # Admin e CEO podem editar qualquer processo
        if user_role in ["admin", "ceo"]:
            return True, "OK"
        
        # Diretor e Administrativo podem editar todos os processos
        if user_role in ["diretor", "administrativo"]:
            return True, "OK"
        
        # Consultor: pode editar se estiver atribuído ao processo
        if user_role == "consultor":
            assigned_consultor_ids = process.get("assigned_consultor_ids", [])
            assigned_consultor_id = process.get("assigned_consultor_id")
            if user_id in assigned_consultor_ids or user_id == assigned_consultor_id:
                return True, "OK"
            # Se não está atribuído, negar
            return False, "Apenas pode editar processos que lhe estão atribuídos"
        
        # Mediador/Intermediário: pode editar se estiver atribuído ao processo
        if user_role in ["mediador", "intermediario"]:
            assigned_mediador_ids = process.get("assigned_mediador_ids", [])
            assigned_mediador_id = process.get("assigned_mediador_id")
            if user_id in assigned_mediador_ids or user_id == assigned_mediador_id:
                return True, "OK"
            # Se não está atribuído, negar
            return False, "Apenas pode editar processos que lhe estão atribuídos"
        
        # Por defeito, permitir para staff
        return True, "OK"
    
    # Role não reconhecido - negar
    return False, f"Role '{user_role}' não tem permissão para editar dados do processo"


def build_query_filter(user: dict) -> dict:
    """
    Constrói o filtro de query baseado no papel do utilizador.
    
    Args:
        user: Dados do utilizador
        
    Returns:
        Filtro MongoDB para a query
    """
    user_role = user.get("role", "")
    user_id = user.get("id", "")
    
    # Staff (incluindo indexacao) veem todos os processos
    # Indexação precisa de ver todos para poder atribuir a consultores/intermediários
    staff_roles = ["admin", "ceo", "diretor", "administrativo", "consultor", "mediador", "intermediario", "indexacao"]
    if user_role in staff_roles:
        return {}
    
    # Clientes só veem os seus próprios processos
    return {"client_id": user_id}


# ==== FUNÇÕES DE CRIAÇÃO E ATUALIZAÇÃO ====

async def create_process_document(
    data: ProcessCreate,
    user: dict
) -> Tuple[dict, str]:
    """
    Cria um novo documento de processo.
    
    Args:
        data: Dados do processo do Pydantic model
        user: Utilizador que está a criar
        
    Returns:
        Tuple com (documento do processo, id do processo)
    """
    process_id = str(uuid.uuid4())
    process_number = await get_next_process_number()
    process_ref = f"PROC-{process_number:04d}"
    
    # Sanitizar email
    clean_email = ""
    if data.client_email:
        clean_email = sanitize_email(data.client_email)
    
    # Construir documento
    process_doc = {
        "id": process_id,
        "process_number": process_number,
        "process_ref": process_ref,
        "client_name": data.client_name,
        "client_email": clean_email,
        "client_phone": data.client_phone or "",
        "status": data.status or "clientes_espera",
        "process_type": data.process_type or "credito_habitacao",
        "service_type": data.service_type or "completo",
        "consultant_id": data.consultant_id or user.get("id"),
        "mediador_id": data.mediador_id,
        "priority": data.priority or "normal",
        "notes": data.notes or "",
        "assigned_users": [],
        "created_by": user.get("id"),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        # NOTA: history foi REMOVIDO do documento embebido
        # O histórico agora é guardado na coleção dedicada 'history'
        # através do serviço services/history.py
        # Isto evita:
        # - Limite de 16MB do documento MongoDB
        # - Degradação de I/O com arrays grandes
        # - Memory bloat nas listagens
        # Dados estruturados (inicialmente vazios)
        "personal_data": data.personal_data.model_dump() if data.personal_data else {},
        "titular2_data": data.titular2_data.model_dump() if data.titular2_data else {},
        "financial_data": data.financial_data.model_dump() if data.financial_data else {},
        "property_data": data.property_data.model_dump() if data.property_data else {},
        "credit_data": data.credit_data.model_dump() if data.credit_data else {},
        "documents": [],
        "tags": data.tags or [],
    }
    
    # Encriptar campos sensíveis antes de guardar
    process_doc = encrypt_sensitive_data(process_doc)
    
    return process_doc, process_id


async def update_process_document(
    process: dict,
    data: ProcessUpdate,
    user: dict
) -> Tuple[dict, list]:
    """
    Aplica atualizações a um documento de processo.
    
    Args:
        process: Documento existente
        data: Dados de atualização
        user: Utilizador que está a atualizar
        
    Returns:
        Tuple com (update_data dict, lista de mudanças para histórico)
    """
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    changes = []
    
    # Iterar sobre campos que podem ser atualizados
    updatable_fields = [
        "client_name", "client_phone", "status", "process_type",
        "service_type", "priority", "notes", "consultant_id", "mediador_id",
        "tags"
    ]
    
    for field in updatable_fields:
        value = getattr(data, field, None)
        if value is not None and value != process.get(field):
            old_value = process.get(field)
            update_data[field] = value
            changes.append({
                "field": field,
                "old": old_value,
                "new": value
            })
    
    # Email precisa de sanitização
    if data.client_email is not None:
        clean_email = sanitize_email(data.client_email)
        if clean_email != process.get("client_email"):
            update_data["client_email"] = clean_email
            changes.append({
                "field": "client_email",
                "old": process.get("client_email"),
                "new": clean_email
            })
    
    # Dados estruturados
    if data.personal_data:
        update_data["personal_data"] = data.personal_data.model_dump()
        changes.append({"field": "personal_data", "old": "...", "new": "atualizado"})
        
    if data.titular2_data:
        update_data["titular2_data"] = data.titular2_data.model_dump()
        changes.append({"field": "titular2_data", "old": "...", "new": "atualizado"})
        
    if data.financial_data:
        update_data["financial_data"] = data.financial_data.model_dump()
        changes.append({"field": "financial_data", "old": "...", "new": "atualizado"})
        
    if data.property_data:
        update_data["property_data"] = data.property_data.model_dump()
        changes.append({"field": "property_data", "old": "...", "new": "atualizado"})
        
    if data.credit_data:
        update_data["credit_data"] = data.credit_data.model_dump()
        changes.append({"field": "credit_data", "old": "...", "new": "atualizado"})
    
    return update_data, changes


# ==== QUERIES COMUNS ====

async def get_process_by_id(process_id: str) -> Optional[dict]:
    """
    Obtém um processo pelo ID.
    
    Os dados sensíveis são desencriptados automaticamente.
    """
    process = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0}
    )
    
    if process:
        return decrypt_sensitive_data(process)
    return None


async def get_processes_for_user(
    user: dict,
    status: Optional[str] = None,
    limit: int = 500
) -> list:
    """
    Obtém processos visíveis para o utilizador.
    
    Args:
        user: Dados do utilizador
        status: Filtrar por status específico
        limit: Limite de resultados
        
    Returns:
        Lista de processos com dados desencriptados
    """
    query = build_query_filter(user)
    
    if status:
        query["status"] = status
    
    cursor = db.processes.find(query, {"_id": 0}).sort("updated_at", -1).limit(limit)
    processes = await cursor.to_list(length=limit)
    
    # Desencriptar dados sensíveis
    return decrypt_processes_list(processes)


async def get_user_name(user_id: str) -> str:
    """Obtém o nome de um utilizador pelo ID."""
    if not user_id:
        return ""
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "name": 1})
    return user.get("name", "") if user else ""


# ==== FUNÇÕES DE ENCRIPTAÇÃO ====

def encrypt_sensitive_data(data: dict) -> dict:
    """
    Encripta campos sensíveis de um processo antes de guardar na BD.
    
    Campos encriptados:
    - personal_data.nif, documento_id, morada_fiscal, phone
    - titular2_data.nif, documento_id, phone
    - financial_data.portal_financas_senha, seg_social_senha, employer_nif
    - vendedor.nif, documento_id, phone
    - mediador.nif, phone
    - co_buyers[].nif, documento_id, phone
    - co_applicants[].nif
    - client_phone, client_nif (nível raiz)
    
    Args:
        data: Dicionário com dados do processo
        
    Returns:
        Dicionário com campos sensíveis encriptados
    """
    if not encryption_service.is_available() or not data:
        return data
    
    result = data.copy()
    
    # Encriptar campos no nível raiz
    root_fields = ["client_phone", "client_nif"]
    for field in root_fields:
        if field in result and result[field]:
            result[field] = encryption_service.encrypt(str(result[field]))
    
    # Encriptar sub-dicionários
    sections = {
        "personal_data": ["nif", "documento_id", "morada_fiscal", "phone", "telefone"],
        "titular2_data": ["nif", "documento_id", "phone", "telefone"],
        "financial_data": ["portal_financas_senha", "seg_social_senha", "employer_nif"],
        "vendedor": ["nif", "documento_id", "phone", "telefone"],
        "mediador": ["nif", "phone", "telefone"],
    }
    
    for section, fields in sections.items():
        if section in result and isinstance(result[section], dict):
            for field in fields:
                if field in result[section] and result[section][field]:
                    result[section][field] = encryption_service.encrypt(str(result[section][field]))
    
    # Encriptar listas de co-compradores/co-proponentes
    for list_field in ["co_buyers", "co_applicants"]:
        if list_field in result and isinstance(result[list_field], list):
            list_fields = ["nif", "documento_id", "phone", "telefone"]
            for i, item in enumerate(result[list_field]):
                if isinstance(item, dict):
                    for field in list_fields:
                        if field in item and item[field]:
                            result[list_field][i][field] = encryption_service.encrypt(str(item[field]))
    
    return result


def decrypt_sensitive_data(data: dict) -> dict:
    """
    Desencripta campos sensíveis de um processo após ler da BD.
    
    Args:
        data: Dicionário com dados encriptados
        
    Returns:
        Dicionário com campos sensíveis desencriptados
    """
    if not data:
        return data
    
    # Usar cópia profunda para evitar modificar o original
    result = copy.deepcopy(data)
    
    # Função auxiliar para desencriptar campo
    def decrypt_field(value):
        if not value or not isinstance(value, str):
            return value
        if not value.startswith("ENC:"):
            return value
        # Tentar desencriptar mesmo se o serviço não estiver "disponível"
        try:
            decrypted = encryption_service.decrypt(value)
            if decrypted and not decrypted.startswith("ENC:"):
                return decrypted
        except Exception as e:
            logger.warning(f"Erro ao desencriptar valor: {e}")
        return value
    
    # Desencriptar campos no nível raiz
    root_fields = ["client_phone", "client_nif"]
    for field in root_fields:
        if field in result and result[field]:
            result[field] = decrypt_field(result[field])
    
    # Desencriptar sub-dicionários
    sections = {
        "personal_data": ["nif", "documento_id", "morada_fiscal", "phone", "telefone"],
        "titular2_data": ["nif", "documento_id", "phone", "telefone"],
        "financial_data": ["portal_financas_senha", "seg_social_senha", "employer_nif"],
        "vendedor": ["nif", "documento_id", "phone", "telefone"],
        "mediador": ["nif", "phone", "telefone"],
    }
    
    for section, fields in sections.items():
        if section in result and isinstance(result[section], dict):
            for field in fields:
                if field in result[section] and result[section][field]:
                    result[section][field] = decrypt_field(result[section][field])
    
    # Desencriptar listas de co-compradores/co-proponentes
    for list_field in ["co_buyers", "co_applicants"]:
        if list_field in result and isinstance(result[list_field], list):
            list_fields = ["nif", "documento_id", "phone", "telefone"]
            for i, item in enumerate(result[list_field]):
                if isinstance(item, dict):
                    for field in list_fields:
                        if field in item and item[field]:
                            result[list_field][i][field] = decrypt_field(item[field])
    
    return result


def decrypt_processes_list(processes: list, fields_to_decrypt: list = None) -> list:
    """
    Desencripta uma lista de processos.
    
    OTIMIZAÇÃO: Só desencripta os campos especificados.
    Se fields_to_decrypt for None, desencripta todos (comportamento original).
    Se fields_to_decrypt for [], NÃO desencripta nada (útil para listagens).
    
    Args:
        processes: Lista de processos
        fields_to_decrypt: Lista de campos a desencriptar (None = todos, [] = nenhum)
        
    Returns:
        Lista com processos desencriptados
    """
    # Se a lista de campos a desencriptar estiver vazia, saltar desencriptação
    # Isto é útil quando a projeção já exclui campos sensíveis
    if fields_to_decrypt is not None and len(fields_to_decrypt) == 0:
        return processes
    
    # Se fields_to_decrypt for None, usar comportamento original (desencriptar tudo)
    if fields_to_decrypt is None:
        return [decrypt_sensitive_data(p) for p in processes]
    
    # Caso contrário, desencriptar apenas os campos especificados
    result = []
    for p in processes:
        decrypted = p.copy()
        for field in fields_to_decrypt:
            if field in decrypted and decrypted[field]:
                # Verificar se está encriptado
                value = str(decrypted[field])
                if value.startswith("ENC:"):
                    try:
                        decrypted[field] = encryption_service.decrypt(value)
                    except Exception as e:
                        logger.warning(f"Erro ao desencriptar {field}: {e}")
        result.append(decrypted)
    
    return result


# ==== PROJEÇÕES OTIMIZADAS PARA LISTAGENS ====

# Campos necessários para a tabela de processos (listagem geral)
PROCESS_LIST_PROJECTION = {
    "_id": 0,
    "id": 1,
    "process_number": 1,
    "client_name": 1,
    "client_email": 1,
    "client_phone": 1,
    "client_nif": 1,
    "status": 1,
    "priority": 1,
    "process_type": 1,
    "property_value": 1,
    "property_location": 1,
    "loan_amount": 1,
    "assigned_consultor_id": 1,
    "assigned_consultor_ids": 1,
    "assigned_mediador_id": 1,
    "assigned_mediador_ids": 1,
    "assigned_indexacao_id": 1,
    "created_at": 1,
    "updated_at": 1,
    "deed_date": 1,
    "tags": 1,
}

# Campos necessários para o Kanban (visualização em colunas)
PROCESS_KANBAN_PROJECTION = {
    "_id": 0,
    "id": 1,
    "process_number": 1,
    "client_name": 1,
    "client_email": 1,
    "client_phone": 1,
    "status": 1,
    "priority": 1,
    "under_35": 1,
    "process_type": 1,
    "property_value": 1,
    "assigned_consultor_id": 1,
    "assigned_consultor_ids": 1,
    "assigned_mediador_id": 1,
    "assigned_mediador_ids": 1,
    "assigned_indexacao_id": 1,
    "assigned_parceiro_id": 1,
    "created_at": 1,
    "updated_at": 1,
    "notes": 1,
    "tags": 1,
}

# Campos necessários para "Os Meus Clientes"
PROCESS_MY_CLIENTS_PROJECTION = {
    "_id": 0,
    "id": 1,
    "process_number": 1,
    "client_name": 1,
    "client_email": 1,
    "client_phone": 1,
    "status": 1,
    "process_type": 1,
    "assigned_consultor_id": 1,
    "assigned_mediador_id": 1,
    "created_at": 1,
    "updated_at": 1,
    "deed_date": 1,
    "property_id": 1,
}
