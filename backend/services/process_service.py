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
from typing import Optional, Tuple

from database import db
from models.process import ProcessCreate, ProcessUpdate
from services.encryption import encryption_service, generate_nif_hash, generate_email_hash, generate_telefone_hash

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
    staff_roles = ["admin", "ceo", "diretor", "administrativo", "consultor", "intermediario", "indexacao"]
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
    staff_edit_roles = ["admin", "ceo", "diretor", "administrativo", "consultor", "intermediario"]
    
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
        if user_role == "intermediario":
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
    staff_roles = ["admin", "ceo", "diretor", "administrativo", "consultor", "intermediario", "indexacao"]
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
    
    # Construir documento — modelo limpo (sem dados pessoais do cliente)
    process_doc = {
        "id": process_id,
        "process_number": process_number,
        "process_ref": process_ref,
        "client_id": data.client_id,
        "status": "clientes_espera",
        "process_type": data.process_type or "credito_habitacao",
        "service_type": data.service_type or "completo",
        "value": data.value,
        "loan_amount": data.loan_amount,
        "notes": data.notes or "",
        "is_active": True,
        "documents": [],
        "created_by": user.get("email", user.get("id")),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
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
    
    # Iterar sobre campos actualizáveis do modelo limpo
    updatable_fields = [
        "type", "process_type", "service_type", "status",
        "value", "loan_amount", "interest_rate", "monthly_payment",
        "loan_term_years", "bank_assigned", "honorarios", "comissao_banco",
        "capital_proprio", "bank_approval_date", "bank_approval_notes",
        "valuation_value", "valuation_date", "valuation_bank",
        "assigned_consultor_id", "assigned_mediador_id",
        "assigned_indexacao_id", "assigned_parceiro_id",
        "has_property", "notes", "prioridade", "is_active",
        "source", "s3_folder", "monitored_emails",
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
    
    # 2º Titular / Fiador e contrapartes (listas — substituição completa)
    for list_field in ["co_buyers", "co_applicants", "vendedor", "mediador"]:
        value = getattr(data, list_field, None)
        if value is not None:
            update_data[list_field] = value
            changes.append({"field": list_field, "old": "...", "new": "atualizado"})
    
    # Documentos e OneDrive
    for doc_field in ["documents", "onedrive_links"]:
        value = getattr(data, doc_field, None)
        if value is not None:
            update_data[doc_field] = value
            changes.append({"field": doc_field, "old": "...", "new": "atualizado"})
    
    # Labels (lista — substituição completa)
    if data.labels is not None:
        update_data["labels"] = data.labels
        changes.append({"field": "labels", "old": "...", "new": "atualizado"})



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


async def populate_client_data(process: dict) -> dict:
    """
    Popula o processo com dados do cliente (retrocompatibilidade Fase 2→3).

    Lê o documento do cliente na coleção `clients` via client_id e injeta
    os dados pessoais na estrutura antiga (personal_data, titular2_data,
    financial_data) que o Frontend ainda espera.

    Se existir second_client_id, popula também second_client_data com os
    dados do 2º titular (pesquisa na coleção `clients`).

    Isto garante que o Frontend NÃO quebra durante a Fase 3 (refactor do FE).
    Quando o FE for migrado, este helper deixa de ser necessário.

    Args:
        process: Documento do processo (já desencriptado)

    Returns:
        Processo com dados do cliente populados (cópia)
    """
    result = copy.deepcopy(process)
    client_id = result.get("client_id")
    if not client_id:
        return result

    # Buscar cliente na coleção clients
    client_doc = await db.clients.find_one({"id": client_id}, {"_id": 0})
    if not client_doc:
        logger.warning(f"Cliente {client_id} não encontrado para processo {result.get('id')}")
        return result

    # Desencriptar dados do cliente
    try:
        from services.encryption import decrypt_client_data
        client_doc = decrypt_client_data(client_doc)
    except Exception as e:
        logger.warning(f"Erro ao desencriptar dados do cliente {client_id}: {e}")

    contacto = client_doc.get("contacto") or {}
    dados_pessoais = client_doc.get("dados_pessoais") or {}

    # ── Preencher campos de nível raiz (retrocompatibilidade) ──────────
    # Após refatoração Fase 3 (Clientes separados de Processos), o campo
    # client_name pode existir como string vazia no processo — usamos
    # `if not get()` em vez de `setdefault` para forçar override quando
    # o valor armazenado está vazio mas o cliente tem nome.
    if not result.get("client_name"):
        result["client_name"] = client_doc.get("nome", "")
    if not result.get("client_email"):
        result["client_email"] = contacto.get("email", "")
    if not result.get("client_phone"):
        result["client_phone"] = contacto.get("telefone", "")
    if not result.get("client_nif"):
        result["client_nif"] = dados_pessoais.get("nif", "")

    # ── Montar personal_data (estrutura antiga do Frontend) ────────────
    # Só preencher se NÃO existir personal_data no processo
    # (dados antigos no processo têm precedência — migração gradual)
    if not result.get("personal_data") or not isinstance(result["personal_data"], dict):
        result["personal_data"] = {}
    pd = result["personal_data"]

    # Preencher campos em falta com dados do cliente
    pd.setdefault("nome", client_doc.get("nome", ""))
    pd.setdefault("name", client_doc.get("nome", ""))
    pd.setdefault("email", contacto.get("email", ""))
    pd.setdefault("phone", contacto.get("telefone", ""))
    pd.setdefault("telefone", contacto.get("telefone", ""))
    pd.setdefault("nif", dados_pessoais.get("nif", ""))
    pd.setdefault("documento_id", dados_pessoais.get("documento_id", ""))
    pd.setdefault("data_nascimento", dados_pessoais.get("data_nascimento") or None)
    pd.setdefault("birth_date", dados_pessoais.get("birth_date") or dados_pessoais.get("data_nascimento") or None)
    pd.setdefault("morada_fiscal", dados_pessoais.get("morada_fiscal") or None)
    pd.setdefault("estado_civil", dados_pessoais.get("estado_civil") or None)
    pd.setdefault("profissao", dados_pessoais.get("profissao") or None)
    pd.setdefault("nacionalidade", dados_pessoais.get("nacionalidade") or None)
    pd.setdefault("naturalidade", dados_pessoais.get("naturalidade") or None)
    pd.setdefault("sexo", dados_pessoais.get("sexo") or None)
    pd.setdefault("nome_pai", dados_pessoais.get("nome_pai") or None)
    pd.setdefault("nome_mae", dados_pessoais.get("nome_mae") or None)
    pd.setdefault("data_validade_cc", dados_pessoais.get("data_validade_cc") or None)
    pd.setdefault("menor_35_anos", dados_pessoais.get("menor_35_anos"))
    pd.setdefault("altura", dados_pessoais.get("altura", ""))

    # ── Montar titular2_data (se existir no cliente) ───────────────────
    if not result.get("titular2_data"):
        result["titular2_data"] = client_doc.get("titular2_data", {})

    # ── Montar financial_data (vazio — dados financeiros estão no processo) ──
    if not result.get("financial_data"):
        result["financial_data"] = {}

    # ── Popular second_client_data (2º titular ligado via second_client_id) ──
    second_client_id = result.get("second_client_id")
    if second_client_id:
        second_client_doc = await db.clients.find_one({"id": second_client_id}, {"_id": 0})
        if second_client_doc:
            try:
                from services.encryption import decrypt_client_data
                second_client_doc = decrypt_client_data(second_client_doc)
            except Exception as e:
                logger.warning(f"Erro ao desencriptar dados do 2º titular {second_client_id}: {e}")

            sc_contacto = second_client_doc.get("contacto") or {}
            sc_dados_pessoais = second_client_doc.get("dados_pessoais") or {}

            result["second_client_data"] = {
                "id": second_client_doc.get("id"),
                "nome": second_client_doc.get("nome", ""),
                "email": sc_contacto.get("email", ""),
                "telefone": sc_contacto.get("telefone", ""),
                "nif": sc_dados_pessoais.get("nif", ""),
                "documento_id": sc_dados_pessoais.get("documento_id") or None,
                "data_nascimento": sc_dados_pessoais.get("data_nascimento") or None,
                "birth_date": sc_dados_pessoais.get("birth_date") or sc_dados_pessoais.get("data_nascimento") or None,
                "morada_fiscal": sc_dados_pessoais.get("morada_fiscal") or None,
                "estado_civil": sc_dados_pessoais.get("estado_civil", ""),
                "profissao": sc_dados_pessoais.get("profissao", ""),
                "nacionalidade": sc_dados_pessoais.get("nacionalidade", ""),
                "naturalidade": sc_dados_pessoais.get("naturalidade", ""),
                "sexo": sc_dados_pessoais.get("sexo", ""),
                "nome_pai": sc_dados_pessoais.get("nome_pai", ""),
                "nome_mae": sc_dados_pessoais.get("nome_mae", ""),
                "financial_data": second_client_doc.get("financial_data", {}),
                "titular2_data": second_client_doc.get("titular2_data", {}),
            }

            # Sincronizar titular2_data do processo com dados do 2º cliente
            # (mantém retrocompatibilidade — o Frontend lê titular2_data)
            result["titular2_data"] = {
                "name": second_client_doc.get("nome", ""),
                "nome": second_client_doc.get("nome", ""),
                "email": sc_contacto.get("email", ""),
                "phone": sc_contacto.get("telefone", ""),
                "telefone": sc_contacto.get("telefone", ""),
                "nif": sc_dados_pessoais.get("nif", ""),
                "documento_id": sc_dados_pessoais.get("documento_id") or None,
                "birth_date": sc_dados_pessoais.get("birth_date") or sc_dados_pessoais.get("data_nascimento") or None,
                "data_nascimento": sc_dados_pessoais.get("data_nascimento") or None,
                "morada_fiscal": sc_dados_pessoais.get("morada_fiscal") or None,
                "estado_civil": sc_dados_pessoais.get("estado_civil", ""),
                "profissao": sc_dados_pessoais.get("profissao", ""),
                "nacionalidade": sc_dados_pessoais.get("nacionalidade", ""),
                "naturalidade": sc_dados_pessoais.get("naturalidade", ""),
                "sexo": sc_dados_pessoais.get("sexo", ""),
                "nome_pai": sc_dados_pessoais.get("nome_pai", ""),
                "nome_mae": sc_dados_pessoais.get("nome_mae", ""),
            }

            # Atualizar second_client_name para retrocompatibilidade
            result["second_client_name"] = second_client_doc.get("nome", "")
        else:
            logger.warning(f"2º titular {second_client_id} não encontrado na coleção clients")
            result["second_client_data"] = None

    return result


def extract_client_updates_from_body(body: dict) -> dict:
    """
    Extrai campos de dados pessoais do body do update (PUT).

    Na Fase 2, o Frontend ainda pode enviar dados pessoais no update do
    processo. Esta função separa os campos que pertencem ao Cliente
    daqueles que pertencem ao Processo.

    Args:
        body: Body raw do pedido PUT

    Returns:
        Dict com campos a atualizar no cliente (formato MongoDB $set)
    """
    client_updates = {}

    # personal_data → dados_pessoais do cliente
    pd = body.get("personal_data")
    if isinstance(pd, dict):
        dp_updates = {}
        field_map = {
            "nif": "nif",
            "documento_id": "documento_id",
            "data_nascimento": "data_nascimento",
            "birth_date": "data_nascimento",
            "morada_fiscal": "morada_fiscal",
            "estado_civil": "estado_civil",
            "profissao": "profissao",
            "nacionalidade": "nacionalidade",
            "naturalidade": "naturalidade",
            "sexo": "sexo",
            "nome_pai": "nome_pai",
            "nome_mae": "nome_mae",
            "data_validade_cc": "data_validade_cc",
            "phone": "telefone",
            "telefone": "telefone",
        }
        for src_key, dst_key in field_map.items():
            val = pd.get(src_key)
            if val is not None:
                dp_updates[dst_key] = val

        if dp_updates:
            for k, v in dp_updates.items():
                client_updates[f"dados_pessoais.{k}"] = v

        # Nome do cliente
        nome = pd.get("nome") or pd.get("name")
        if nome:
            client_updates["nome"] = nome
            client_updates["dados_pessoais.nome_completo"] = nome

        # Email
        email = pd.get("email")
        if email:
            client_updates["contacto.email"] = email.lower().strip()

    # titular2_data → titular2_data do cliente
    t2 = body.get("titular2_data")
    if isinstance(t2, dict):
        client_updates["titular2_data"] = t2

    # client_email / client_phone do body — o Frontend envia estes campos
    # directamente no update do processo quando o utilizador edita contactos
    client_email = body.get("client_email")
    if client_email:
        client_updates["contacto.email"] = client_email.lower().strip()

    client_phone = body.get("client_phone")
    if client_phone:
        client_updates["contacto.telefone"] = client_phone

    return client_updates


# ==== FUNÇÕES DE ENCRIPTAÇÃO ====

def _add_process_blind_indexes(data: dict) -> None:
    """
    Adiciona blind indexes ao documento do processo (modifica in-place).
    
    Gera SEMPRE (não apenas se ausente) para garantir que actualizações
    a email/NIF/telefone são refletidas imediatamente na pesquisa.
    
    Gera:
    - personal_data.nif_hash
    - personal_data.email_hash
    - personal_data.telefone_hash
    """
    if "personal_data" not in data or not isinstance(data["personal_data"], dict):
        return
    
    pd = data["personal_data"]
    
    # Hash do NIF
    nif = pd.get("nif")
    if nif:
        nif_clean = re.sub(r'[^\d]', '', str(nif))
        if len(nif_clean) == 9:
            pd["nif_hash"] = generate_nif_hash(nif_clean)
    
    # Hash do email para pesquisa
    email = pd.get("email")
    if email:
        pd["email_hash"] = generate_email_hash(email)
    
    # Hash do telefone para pesquisa
    telefone = pd.get("phone") or pd.get("telefone")
    if telefone:
        pd["telefone_hash"] = generate_telefone_hash(telefone)


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
    
    Blind indexes gerados (para pesquisa):
    - personal_data.nif_hash
    - personal_data.email_hash
    - personal_data.telefone_hash
    
    Args:
        data: Dicionário com dados do processo
        
    Returns:
        Dicionário com campos sensíveis encriptados e blind indexes actualizados
    """
    if not encryption_service.is_available() or not data:
        # Mesmo sem encriptação, gerar blind indexes
        result = copy.deepcopy(data)
        _add_process_blind_indexes(result)
        return result
    
    result = copy.deepcopy(data)
    
    # Gerar blind indexes ANTES de encriptar (hashes calculados a partir dos valores originais)
    _add_process_blind_indexes(result)
    
    # Encriptar campos no nível raiz
    root_fields = ["client_phone", "client_nif"]
    for field in root_fields:
        if field in result and result[field]:
            result[field] = encryption_service.encrypt(str(result[field]))
    
    # Encriptar sub-dicionários
    sections = {
        "personal_data": ["nif", "documento_id", "morada_fiscal", "phone", "telefone"],
        "titular2_data": ["nif", "documento_id", "phone", "telefone", "portal_financas_utilizador", "portal_financas_senha", "seg_social_utilizador", "seg_social_senha"],
        "financial_data": ["portal_financas_senha", "seg_social_senha", "employer_nif"],
        "vendedor": ["nif", "documento_id", "phone", "telefone"],
        "intermediario": ["nif", "phone", "telefone"],
    }
    
    for section, fields in sections.items():
        if section in result and isinstance(result[section], dict):
            for field in fields:
                if field in result[section] and result[section][field]:
                    result[section][field] = encryption_service.encrypt(str(result[section][field]))
    
    # Encriptar listas de 2º Titular / Fiador
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
        "titular2_data": ["nif", "documento_id", "phone", "telefone", "portal_financas_utilizador", "portal_financas_senha", "seg_social_utilizador", "seg_social_senha"],
        "financial_data": ["portal_financas_senha", "seg_social_senha", "employer_nif"],
        "vendedor": ["nif", "documento_id", "phone", "telefone"],
        "intermediario": ["nif", "phone", "telefone"],
    }
    
    for section, fields in sections.items():
        if section in result and isinstance(result[section], dict):
            for field in fields:
                if field in result[section] and result[section][field]:
                    result[section][field] = decrypt_field(result[section][field])
    
    # Desencriptar listas de 2º Titular / Fiador
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
                        decrypted_value = encryption_service.decrypt(value)
                        if decrypted_value and not decrypted_value.startswith("ENC:"):
                            decrypted[field] = decrypted_value
                        else:
                            logger.warning(f"Campo {field} não foi desencriptado - serviço pode não estar disponível")
                    except Exception as e:
                        logger.warning(f"Erro ao desencriptar {field}: {e}")
        result.append(decrypted)
    
    return result


# ==== PROJEÇÕES OTIMIZADAS PARA LISTAGENS ====

# Campos necessários para a tabela de processos (listagem geral)
PROCESS_LIST_PROJECTION = {
    "_id": 0,
    "id": 1,
    "client_id": 1,
    "process_number": 1,
    "client_name": 1,
    "client_email": 1,
    "client_phone": 1,
    "client_nif": 1,
    "status": 1,
    "priority": 1,
    "prioridade": 1,
    "process_type": 1,
    "property_value": 1,
    "property_location": 1,
    "loan_amount": 1,
    "is_indexed": 1,
    "indexed_at": 1,
    "assigned_consultor_id": 1,
    "assigned_consultor_ids": 1,
    "assigned_mediador_id": 1,
    "assigned_mediador_ids": 1,
    "assigned_indexacao_id": 1,
    "assigned_parceiro_id": 1,
    "consultor_name": 1,
    "mediador_name": 1,
    "indexacao_name": 1,
    "parceiro_name": 1,
    "created_at": 1,
    "updated_at": 1,
    "deed_date": 1,
    "tags": 1,
    "labels": 1,
}

# Campos necessários para o Kanban (visualização em colunas)
PROCESS_KANBAN_PROJECTION = {
    "_id": 0,
    "id": 1,
    "client_id": 1,
    "process_number": 1,
    "client_name": 1,
    "client_email": 1,
    "client_phone": 1,
    "client_nif": 1,
    "status": 1,
    "priority": 1,
    "prioridade": 1,
    "under_35": 1,
    "process_type": 1,
    "property_value": 1,
    "is_indexed": 1,
    "indexed_at": 1,
    "assigned_consultor_id": 1,
    "assigned_consultor_ids": 1,
    "assigned_mediador_id": 1,
    "assigned_mediador_ids": 1,
    "assigned_indexacao_id": 1,
    "assigned_parceiro_id": 1,
    "indexacao_name": 1,
    "parceiro_name": 1,
    "consultor_name": 1,
    "mediador_name": 1,
    "created_at": 1,
    "updated_at": 1,
    "notes": 1,
    "tags": 1,
    "labels": 1,
    "co_buyers": 1,
    "compradores": 1,
}

# Campos necessários para "Os Meus Clientes"
PROCESS_MY_CLIENTS_PROJECTION = {
    "_id": 0,
    "id": 1,
    "client_id": 1,
    "process_number": 1,
    "client_name": 1,
    "client_email": 1,
    "client_phone": 1,
    "client_nif": 1,
    "status": 1,
    "prioridade": 1,
    "process_type": 1,
    "is_indexed": 1,
    "assigned_consultor_id": 1,
    "assigned_mediador_id": 1,
    "consultor_name": 1,
    "mediador_name": 1,
    "created_at": 1,
    "updated_at": 1,
    "deed_date": 1,
    "property_id": 1,
    "tags": 1,
    "labels": 1,
}
