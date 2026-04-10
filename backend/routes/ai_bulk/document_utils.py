"""
Document Utilities Module
=========================
Utilitários para processamento de documentos na importação em massa.
Inclui hashing, detecção de duplicados, validação de NIF.
"""
import re
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Set, Any

logger = logging.getLogger(__name__)

# Tipos de documentos propensos a duplicados
DUPLICATE_PRONE_TYPES = {
    "recibo_vencimento",
    "extrato_bancario", 
    "irs",
    "contrato_trabalho",
    "cc",
    "declaracao_irs"
}

# Cache em memória para documentos analisados (por processo)
document_hash_cache: Dict[str, Dict[str, Dict[str, dict]]] = {}


def calculate_document_hash(content: bytes) -> str:
    """Calcular hash MD5 do conteúdo do documento."""
    return hashlib.md5(content, usedforsecurity=False).hexdigest()


def is_duplicate_document(process_id: str, document_type: str, content: bytes) -> Optional[dict]:
    """
    Verifica se o documento é duplicado de um já analisado (cache em memória).
    
    Returns:
        Dados extraídos anteriormente se for duplicado, None caso contrário
    """
    if document_type not in DUPLICATE_PRONE_TYPES:
        return None
    
    doc_hash = calculate_document_hash(content)
    
    if process_id in document_hash_cache:
        if document_type in document_hash_cache[process_id]:
            if doc_hash in document_hash_cache[process_id][document_type]:
                logger.info(f"Documento duplicado detectado (cache): {document_type} para {process_id}")
                return document_hash_cache[process_id][document_type][doc_hash]
    
    return None


def cache_document_analysis(process_id: str, document_type: str, content: bytes, extracted_data: dict):
    """Guardar resultado da análise em cache de memória para detectar duplicados futuros."""
    if document_type not in DUPLICATE_PRONE_TYPES:
        return
    
    doc_hash = calculate_document_hash(content)
    
    if process_id not in document_hash_cache:
        document_hash_cache[process_id] = {}
    if document_type not in document_hash_cache[process_id]:
        document_hash_cache[process_id][document_type] = {}
    
    document_hash_cache[process_id][document_type][doc_hash] = extracted_data


def clear_document_cache(process_id: str = None):
    """Limpar cache de documentos (para testes ou reset)."""
    if process_id:
        if process_id in document_hash_cache:
            del document_hash_cache[process_id]
    else:
        document_hash_cache.clear()


# ====================================================================
# VALIDAÇÃO DE NIF
# ====================================================================

# NIFs placeholder conhecidos
PLACEHOLDER_NIFS = {'123456789', '000000000', '111111111', '999999999', '12345678'}

# Primeiro dígito válido para pessoas singulares
VALID_PESSOA_SINGULAR_DIGITS = {'1', '2', '6', '9'}


def validate_nif(nif: str) -> bool:
    """
    Valida se o NIF é válido para pessoa singular.
    NIFs de pessoas singulares começam por 1, 2, 6 ou 9.
    NIFs começados por 5 são de empresas/colectividades - REJEITADOS.
    """
    if not nif:
        return True  # Permitir vazio
    
    # Remover espaços e caracteres não numéricos
    nif = re.sub(r'\D', '', str(nif))
    
    if len(nif) != 9:
        return False
    
    # Rejeitar NIFs placeholder
    if nif in PLACEHOLDER_NIFS:
        logger.warning(f"NIF {nif} é um placeholder - rejeitado")
        return False
    
    first_digit = nif[0]
    
    # 5 é para entidades colectivas - SEMPRE REJEITAR para clientes
    if first_digit == '5':
        logger.warning(f"NIF {nif} começa por 5 (entidade colectiva) - REJEITADO")
        return False
    
    # NIFs válidos para pessoas singulares: 1, 2, 6, 9
    if first_digit not in VALID_PESSOA_SINGULAR_DIGITS:
        logger.warning(f"NIF {nif} tem primeiro dígito inválido: {first_digit}")
        return False
    
    return True


def normalize_nif(nif: str) -> str:
    """Normalizar NIF removendo caracteres não numéricos."""
    if not nif:
        return ""
    return re.sub(r'\D', '', str(nif))


def is_empresa_nif(nif: str) -> bool:
    """Verificar se NIF é de empresa (começa por 5)."""
    nif = normalize_nif(nif)
    return len(nif) == 9 and nif[0] == '5'


# ====================================================================
# DETECÇÃO DE VALORES PLACEHOLDER
# ====================================================================

PLACEHOLDER_VALUES = {
    'YYYY-MM-DD', 'DD/MM/YYYY', 'DD-MM-YYYY',
    'N/A', 'NA', 'NULL', 'NONE', 'UNDEFINED',
    'XXX', 'TBD', 'TODO', '???'
}


def is_placeholder_value(value: Any) -> bool:
    """Verifica se um valor é um placeholder (não real)."""
    if not value:
        return False
    
    value_str = str(value).strip().upper()
    
    # Verificar lista de placeholders conhecidos
    if value_str in PLACEHOLDER_VALUES:
        return True
    
    # Verificar padrões de data placeholder
    if 'YYYY' in value_str or 'DD' in value_str and 'MM' in value_str:
        return True
    
    return False


# ====================================================================
# DETECÇÃO DE TIPO DE DOCUMENTO
# ====================================================================

# Padrões para identificação de documentos
DOCUMENT_PATTERNS = {
    'cc': ['cc', 'cartao_cidadao', 'cartão cidadão', 'cidadao', 'cartao cidadao'],
    'bi': ['bi', 'bilhete_identidade', 'bilhete identidade'],
    'passaporte': ['passaporte', 'passport'],
    'recibo_vencimento': ['recibo', 'vencimento', 'salario', 'ordenado', 'remuneracao'],
    'irs': ['irs', 'declaracao_rendimentos', 'modelo3', 'modelo 3'],
    'extrato_bancario': ['extrato', 'bancario', 'conta', 'movimento'],
    'contrato_trabalho': ['contrato', 'trabalho', 'emprego'],
    'comprovativo_morada': ['morada', 'residencia', 'comprovativo'],
    'caderneta_predial': ['caderneta', 'predial'],
    'cpcv': ['cpcv', 'promessa', 'compra e venda'],
}


def detect_document_type(filename: str) -> Optional[str]:
    """
    Detecta o tipo de documento baseado no nome do ficheiro.
    
    Returns:
        Tipo do documento ou None se não identificado
    """
    if not filename:
        return None
    
    filename_lower = filename.lower()
    
    for doc_type, patterns in DOCUMENT_PATTERNS.items():
        for pattern in patterns:
            if pattern in filename_lower:
                return doc_type
    
    return None


def detect_cc_side(filename: str) -> Optional[str]:
    """
    Detecta se é frente ou verso do Cartão de Cidadão.
    
    Returns:
        'frente', 'verso' ou None
    """
    if not filename:
        return None
    
    filename_lower = filename.lower()
    
    frente_patterns = ['frente', 'front', '_f.', '_f_', 'cc_1', 'cc1', 'ccf']
    verso_patterns = ['verso', 'back', 'tras', '_v.', '_v_', 'cc_2', 'cc2', 'ccv']
    
    for pattern in frente_patterns:
        if pattern in filename_lower:
            return 'frente'
    
    for pattern in verso_patterns:
        if pattern in filename_lower:
            return 'verso'
    
    return None


# ====================================================================
# EXTRACÇÃO DE MESES DE REFERÊNCIA
# ====================================================================

MONTH_NAMES_PT = {
    'janeiro': 1, 'jan': 1,
    'fevereiro': 2, 'fev': 2,
    'marco': 3, 'março': 3, 'mar': 3,
    'abril': 4, 'abr': 4,
    'maio': 5, 'mai': 5,
    'junho': 6, 'jun': 6,
    'julho': 7, 'jul': 7,
    'agosto': 8, 'ago': 8,
    'setembro': 9, 'set': 9,
    'outubro': 10, 'out': 10,
    'novembro': 11, 'nov': 11,
    'dezembro': 12, 'dez': 12
}


def extract_month_reference(text: str) -> Optional[str]:
    """
    Extrai mês de referência de um texto (ex: nome de ficheiro).
    
    Returns:
        String no formato 'YYYY-MM' ou None
    """
    if not text:
        return None
    
    text_lower = text.lower()
    
    # Procurar padrão ano-mês (ex: 2024-01, 2024_01)
    match = re.search(r'(20\d{2})[-_]?(0[1-9]|1[0-2])', text_lower)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    
    # Procurar nome do mês + ano
    for month_name, month_num in MONTH_NAMES_PT.items():
        if month_name in text_lower:
            year_match = re.search(r'(20\d{2})', text_lower)
            if year_match:
                return f"{year_match.group(1)}-{month_num:02d}"
    
    return None


# ====================================================================
# CATEGORIZAÇÃO DE CAMPOS EXTRAÍDOS
# ====================================================================

FIELD_CATEGORIES = {
    'personal_data': ['nome', 'nif', 'data_nascimento', 'nacionalidade', 'estado_civil'],
    'financial_data': ['salario', 'rendimento', 'despesas', 'encargos'],
    'employment_data': ['empresa', 'empregador', 'cargo', 'funcao', 'contrato'],
    'property_data': ['morada', 'endereco', 'imovel', 'valor_imovel'],
    'document_data': ['numero_documento', 'validade', 'emissao']
}


def categorize_extracted_field(field_name: str) -> str:
    """
    Categoriza um campo extraído.
    
    Returns:
        Nome da categoria
    """
    field_lower = field_name.lower()
    
    for category, keywords in FIELD_CATEGORIES.items():
        for keyword in keywords:
            if keyword in field_lower:
                return category
    
    return 'other'


def categorize_extracted_data(data: dict) -> Dict[str, dict]:
    """
    Categoriza todos os campos extraídos por categoria.
    
    Returns:
        Dicionário agrupado por categoria
    """
    categorized = {}
    
    for field, value in data.items():
        category = categorize_extracted_field(field)
        if category not in categorized:
            categorized[category] = {}
        categorized[category][field] = value
    
    return categorized
