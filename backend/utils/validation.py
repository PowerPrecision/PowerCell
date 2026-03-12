"""
====================================================================
UTILIDADES DE VALIDAÇÃO - CREDITOIMO
====================================================================
Funções unificadas de validação para NIF, email, telefone.
Centraliza lógica de validação que era duplicada no código.
====================================================================
"""
import re
from typing import Optional, Tuple


def validate_nif(nif: str) -> Tuple[bool, Optional[str]]:
    """
    Valida NIF português (9 dígitos com dígito de controlo).
    
    Args:
        nif: Número de Identificação Fiscal (pode ter espaços)
    
    Returns:
        (is_valid, error_message)
        Se válido: (True, None)
        Se inválido: (False, "mensagem de erro")
    
    Validações:
    - Deve ter exactamente 9 dígitos
    - Primeiro dígito válido: 1, 2, 3, 5, 6, 7, 8, 9
    - Dígito de controlo válido (algoritmo módulo 11)
    
    Example:
        >>> validate_nif("123456789")
        (True, None)
        >>> validate_nif("12345678A")
        (False, "NIF deve conter apenas dígitos")
    """
    if not nif:
        return False, "NIF é obrigatório"
    
    # Remover espaços e caracteres não numéricos
    nif_clean = re.sub(r'\D', '', str(nif))
    
    if len(nif_clean) != 9:
        return False, "NIF deve ter exactamente 9 dígitos"
    
    # Verificar se são todos dígitos
    if not nif_clean.isdigit():
        return False, "NIF deve conter apenas dígitos"
    
    # Verificar primeiro dígito (tipo de contribuinte)
    first_digit = int(nif_clean[0])
    valid_first_digits = [1, 2, 3, 5, 6, 7, 8, 9]
    if first_digit not in valid_first_digits:
        return False, f"NIF inválido: primeiro dígito deve ser {valid_first_digits}"
    
    # Calcular dígito de controlo (módulo 11)
    checksum = 0
    for i in range(8):
        checksum += int(nif_clean[i]) * (9 - i)
    
    remainder = checksum % 11
    check_digit = 0 if remainder < 2 else 11 - remainder
    
    if int(nif_clean[8]) != check_digit:
        return False, "NIF inválido: dígito de controlo incorrecto"
    
    return True, None


def validate_email(email: str) -> Tuple[bool, Optional[str]]:
    """
    Valida formato de email.
    
    Args:
        email: Endereço de email
    
    Returns:
        (is_valid, error_message)
    
    Validações:
    - Formato básico: user@domain.tld
    - Domínio com pelo menos um ponto
    - Sem espaços
    
    Example:
        >>> validate_email("user@example.com")
        (True, None)
        >>> validate_email("invalid-email")
        (False, "Email inválido: formato incorrecto")
    """
    if not email:
        return False, "Email é obrigatório"
    
    email_clean = str(email).strip().lower()
    
    # Verificar espaços
    if ' ' in email_clean:
        return False, "Email não pode conter espaços"
    
    # Regex para validação básica de email
    # Aceita: user@domain.tld, user.name@sub.domain.tld
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(email_pattern, email_clean):
        return False, "Email inválido: formato incorrecto"
    
    # Verificar múltiplos @ ou pontos consecutivos
    if email_clean.count('@') != 1:
        return False, "Email inválido: deve conter exactamente um @"
    
    if '..' in email_clean:
        return False, "Email inválido: pontos consecutivos não permitidos"
    
    return True, None


def validate_phone(phone: str, country_code: str = "PT") -> Tuple[bool, Optional[str]]:
    """
    Valida número de telefone português.
    
    Args:
        phone: Número de telefone
        country_code: Código do país (default: PT)
    
    Returns:
        (is_valid, error_message)
    
    Validações para PT:
    - 9 dígitos (sem indicativo)
    - Ou formato internacional: +351 xxx xxx xxx
    - Prefixos válidos: 9 (móvel), 2 (fixo)
    
    Example:
        >>> validate_phone("912345678")
        (True, None)
        >>> validate_phone("+351912345678")
        (True, None)
    """
    if not phone:
        return False, "Telefone é obrigatório"
    
    # Remover espaços, hífens, parênteses
    phone_clean = re.sub(r'[\s\-\(\)]', '', str(phone))
    
    # Remover prefixo internacional PT se presente
    if phone_clean.startswith('+351'):
        phone_clean = phone_clean[4:]
    elif phone_clean.startswith('00351'):
        phone_clean = phone_clean[5:]
    elif phone_clean.startswith('351') and len(phone_clean) == 12:
        phone_clean = phone_clean[3:]
    
    # Verificar comprimento
    if len(phone_clean) != 9:
        return False, "Telefone deve ter 9 dígitos"
    
    # Verificar se são todos dígitos
    if not phone_clean.isdigit():
        return False, "Telefone deve conter apenas dígitos"
    
    # Validar prefixo português
    first_digit = phone_clean[0]
    if first_digit == '9':
        # Móvel - verificar segundo dígito
        second_digit = phone_clean[1]
        valid_mobile_prefixes = ['1', '2', '3', '4', '5', '6']
        if second_digit not in valid_mobile_prefixes:
            return False, f"Prefixo móvel inválido: 9{second_digit}"
    elif first_digit == '2':
        # Fixo - OK
        pass
    elif first_digit == '3':
        # Números especiais/voip - OK
        pass
    else:
        return False, f"Prefixo de telefone inválido: {first_digit}"
    
    return True, None


def format_nif(nif: str) -> str:
    """
    Formata NIF no padrão português: XXX XXX XXX
    
    Args:
        nif: NIF (com ou sem formatação)
    
    Returns:
        NIF formatado ou string original se inválido
    """
    nif_clean = re.sub(r'\D', '', str(nif))
    
    if len(nif_clean) != 9:
        return nif
    
    return f"{nif_clean[:3]} {nif_clean[3:6]} {nif_clean[6:9]}"


def format_phone(phone: str, include_country: bool = False) -> str:
    """
    Formata telefone no padrão: XXX XXX XXX ou +351 XXX XXX XXX
    
    Args:
        phone: Número de telefone
        include_country: Se True, inclui indicativo +351
    
    Returns:
        Telefone formatado ou string original se inválido
    """
    phone_clean = re.sub(r'\D', '', str(phone))
    
    # Remover prefixo PT se presente
    if phone_clean.startswith('351') and len(phone_clean) == 12:
        phone_clean = phone_clean[3:]
    
    if len(phone_clean) != 9:
        return phone
    
    formatted = f"{phone_clean[:3]} {phone_clean[3:6]} {phone_clean[6:9]}"
    
    if include_country:
        return f"+351 {formatted}"
    
    return formatted


def sanitize_email(email: str) -> str:
    """
    Sanitiza email: lowercase e trim.
    
    Args:
        email: Email a sanitizar
    
    Returns:
        Email sanitizado
    """
    if not email:
        return ""
    return str(email).strip().lower()


def normalize_phone(phone: str) -> str:
    """
    Normaliza telefone para formato sem espaços e sem indicativo.
    
    Args:
        phone: Telefone a normalizar
    
    Returns:
        9 dígitos ou string original se inválido
    """
    if not phone:
        return ""
    
    phone_clean = re.sub(r'\D', '', str(phone))
    
    # Remover prefixo PT
    if phone_clean.startswith('351') and len(phone_clean) == 12:
        phone_clean = phone_clean[3:]
    
    return phone_clean


__all__ = [
    "validate_nif",
    "validate_email", 
    "validate_phone",
    "format_nif",
    "format_phone",
    "sanitize_email",
    "normalize_phone",
]
