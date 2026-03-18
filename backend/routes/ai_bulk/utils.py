"""
Funções utilitárias para o módulo AI Bulk.
Extraído de ai_bulk.py para melhor organização (SonarQube).
"""
import re
import logging
from datetime import datetime, timezone
from typing import Optional, Dict

logger = logging.getLogger(__name__)


def sanitize_for_log(value: str, max_length: int = 50) -> str:
    """
    Sanitiza dados controlados pelo utilizador antes de logar.
    Remove carateres potencialmente perigosos e limita o tamanho.
    """
    if not value:
        return "[empty]"
    # Truncar e remover quebras de linha
    sanitized = str(value)[:max_length].replace('\n', ' ').replace('\r', '')
    return sanitized if sanitized else "[sanitized]"


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
    if nif in ['123456789', '000000000', '111111111', '999999999']:
        logger.warning("NIF placeholder - rejeitado")
        return False
    
    first_digit = nif[0]
    
    # 5 é para entidades colectivas - SEMPRE REJEITAR para clientes
    if first_digit == '5':
        logger.warning("NIF começa por 5 (entidade colectiva) - REJEITADO")
        return False
    
    # NIFs válidos para pessoas singulares: 1, 2, 6, 9
    if first_digit not in ['1', '2', '6', '9']:
        logger.warning("NIF tem primeiro dígito inválido")
        return False
    
    return True


def is_placeholder_value(value: str) -> bool:
    """Verifica se um valor é um placeholder (não real)."""
    if not value:
        return False
    
    value_str = str(value).strip().upper()
    
    # Datas placeholder
    if value_str in ['YYYY-MM-DD', 'DD/MM/YYYY', 'DD-MM-YYYY', 'N/A', 'NA', 'NULL', 'NONE', '']:
        return True
    
    # Valores numéricos placeholder
    if value_str in ['123456789', '000000000', '0', '00000000', '12345678']:
        return True
    
    # Se contém YYYY ou DD sem ser uma data real
    if 'YYYY' in value_str or value_str == 'DD':
        return True
    
    return False


def clean_extracted_value(value):
    """Limpa um valor extraído, removendo placeholders."""
    if value is None:
        return None
    
    if isinstance(value, str):
        if is_placeholder_value(value):
            return None
        return value.strip() if value.strip() else None
    
    return value


def is_cc_frente_or_verso(filename: str) -> Optional[str]:
    """
    Verificar se o ficheiro é frente ou verso do CC.
    
    Returns:
        "frente", "verso" ou None
    """
    from .constants import CC_FRENTE_PATTERNS, CC_VERSO_PATTERNS
    
    filename_lower = filename.lower()
    
    # Padrões para frente
    for p in CC_FRENTE_PATTERNS:
        if p in filename_lower:
            return "frente"
    
    # Padrões para verso
    for p in CC_VERSO_PATTERNS:
        if p in filename_lower:
            return "verso"
    
    return None


def get_normalized_filename(document_type: str) -> str:
    """Obter nome normalizado para o tipo de documento."""
    from .constants import NORMALIZED_NAMES
    return NORMALIZED_NAMES.get(document_type, NORMALIZED_NAMES["outro"])


def get_current_timestamp() -> str:
    """Obter timestamp atual em formato ISO."""
    return datetime.now(timezone.utc).isoformat()


def categorize_extracted_fields(extracted_data: dict, document_type: str) -> Dict[str, Dict[str, any]]:
    """
    Categorizar campos extraídos em: dados_pessoais, imovel, financiamento, outros.
    Baseado na estrutura da ficha de cliente.
    """
    categories = {
        "dados_pessoais": {},
        "imovel": {},
        "financiamento": {},
        "outros": {}
    }
    
    # Mapeamento de campos para categorias
    personal_fields = [
        "nome", "name", "nif", "NIF", "data_nascimento", "morada", "codigo_postal",
        "localidade", "telefone", "email", "estado_civil", "nacionalidade",
        "cc_numero", "cc_validade", "genero", "profissao", "entidade_empregadora",
        "tipo_contrato", "antiguidade", "rendimento_mensal", "outros_rendimentos"
    ]
    
    property_fields = [
        "tipo_imovel", "finalidade", "valor_imovel", "valor_escritura",
        "morada_imovel", "distrito", "concelho", "freguesia", "ano_construcao",
        "area_bruta", "area_util", "tipologia", "caderneta_predial", "artigo"
    ]
    
    finance_fields = [
        "valor_financiamento", "prazo", "taxa_esforco", "spread", "euribor",
        "prestacao", "lti", "ltv", "banco", "entidade_bancaria",
        "despesas_mensais", "encargos", "creditos_existentes"
    ]
    
    for key, value in extracted_data.items():
        if value is None or value == "":
            continue
            
        key_lower = key.lower()
        
        if key_lower in [f.lower() for f in personal_fields] or key_lower.startswith("personal"):
            categories["dados_pessoais"][key] = value
        elif key_lower in [f.lower() for f in property_fields] or key_lower.startswith("property") or key_lower.startswith("imovel"):
            categories["imovel"][key] = value
        elif key_lower in [f.lower() for f in finance_fields] or key_lower.startswith("financ"):
            categories["financiamento"][key] = value
        else:
            categories["outros"][key] = value
    
    # Remover categorias vazias
    return {k: v for k, v in categories.items() if v}
