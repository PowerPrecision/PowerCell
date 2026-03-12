"""
====================================================================
INPUT SANITIZATION UTILITIES - CREDITOIMO
====================================================================
Funções de sanitização de inputs para prevenir XSS e outros ataques.

Utiliza a biblioteca 'bleach' para limpeza segura de HTML.
====================================================================
"""
import re
import logging
import bleach
from typing import Optional

logger = logging.getLogger(__name__)

# Tags HTML permitidas (muito restritivas - apenas formatação básica)
ALLOWED_TAGS = []  # Nenhuma tag HTML permitida por defeito

# Atributos HTML permitidos (vazio por defeito)
ALLOWED_ATTRIBUTES = {}

# Protocolos permitidos em URLs
ALLOWED_PROTOCOLS = ['http', 'https', 'mailto']


def sanitize_string(value: str, max_length: int = 200) -> str:
    """
    Sanitiza uma string removendo HTML, caracteres perigosos e limitando tamanho.
    
    Args:
        value: String a sanitizar
        max_length: Tamanho máximo permitido (default 200)
    
    Returns:
        String sanitizada
    """
    if not value:
        return ""
    
    # Converter para string se necessário
    if not isinstance(value, str):
        value = str(value)
    
    # 1. Remover caracteres nulos
    value = value.replace('\x00', '')
    
    # 2. Strip HTML tags usando bleach
    value = bleach.clean(
        value,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=True
    )
    
    # 3. Remover entidades HTML que possam ter escapado
    value = re.sub(r'&[a-zA-Z]+;', '', value)
    value = re.sub(r'&#\d+;', '', value)
    value = re.sub(r'&#x[0-9a-fA-F]+;', '', value)
    
    # 4. Strip whitespace e normalizar espaços
    value = ' '.join(value.split())
    
    # 5. Truncar ao tamanho máximo
    if len(value) > max_length:
        value = value[:max_length]
    
    return value.strip()


def sanitize_html(value: str, allow_basic_formatting: bool = False) -> str:
    """
    Sanitiza HTML removendo tags e atributos perigosos.
    
    Args:
        value: HTML a sanitizar
        allow_basic_formatting: Se True, permite tags básicas como <b>, <i>, <p>
    
    Returns:
        HTML sanitizado
    """
    if not value:
        return ""
    
    if not isinstance(value, str):
        value = str(value)
    
    # Remover caracteres nulos
    value = value.replace('\x00', '')
    
    if allow_basic_formatting:
        # Permitir formatação básica
        allowed = ['b', 'i', 'u', 'strong', 'em', 'p', 'br', 'ul', 'ol', 'li']
        attrs = {}
    else:
        # Remover tudo
        allowed = []
        attrs = {}
    
    # Usar bleach para limpeza segura
    cleaned = bleach.clean(
        value,
        tags=allowed,
        attributes=attrs,
        protocols=ALLOWED_PROTOCOLS,
        strip=True
    )
    
    # Remover scripts/eventos que possam ter escapado
    # Padrões perigosos que queremos garantir que são removidos
    dangerous_patterns = [
        r'javascript:',
        r'vbscript:',
        r'data:',
        r'on\w+\s*=',  # Event handlers como onclick=, onload=
        r'<script',
        r'</script',
        r'<iframe',
        r'</iframe',
        r'<object',
        r'</object',
        r'<embed',
        r'</embed',
        r'<form',
        r'</form',
    ]
    
    for pattern in dangerous_patterns:
        cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE)
    
    return cleaned.strip()


def sanitize_email(email: str) -> str:
    """
    Sanitiza e valida formato de email.
    
    Args:
        email: Email a sanitizar
    
    Returns:
        Email sanitizado e em lowercase, ou string vazia se inválido
    """
    if not email:
        return ""
    
    # Sanitizar primeiro
    email = sanitize_string(email, max_length=100)
    
    # Converter para lowercase
    email = email.lower().strip()
    
    # Remover formatação markdown [texto](mailto:email)
    markdown_link = re.search(r'\[.*?\]\(mailto:([^)]+)\)', email)
    if markdown_link:
        email = markdown_link.group(1)
    
    # Remover mailto: prefix
    if email.startswith('mailto:'):
        email = email.replace('mailto:', '')
    
    # Remover angle brackets <email>
    angle_brackets = re.search(r'<([^>]+@[^>]+)>', email)
    if angle_brackets:
        email = angle_brackets.group(1)
    
    # Validar formato básico
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        logger.warning(f"Email inválido após sanitização: {email[:20]}...")
        return ""
    
    return email


def sanitize_phone(phone: str) -> str:
    """
    Sanitiza número de telefone, mantendo apenas dígitos e + inicial.
    
    Args:
        phone: Telefone a sanitizar
    
    Returns:
        Telefone sanitizado
    """
    if not phone:
        return ""
    
    # Sanitizar string base
    phone = sanitize_string(phone, max_length=20)
    
    # Manter apenas dígitos e + no início
    has_plus = phone.startswith('+')
    phone_digits = re.sub(r'[^\d]', '', phone)
    
    if has_plus:
        phone_digits = '+' + phone_digits
    
    # Validar tamanho mínimo (9 dígitos para PT)
    if len(re.sub(r'[^\d]', '', phone_digits)) < 9:
        return ""
    
    return phone_digits


def sanitize_nif(nif: str) -> Optional[str]:
    """
    Sanitiza e valida NIF português.
    
    Args:
        nif: NIF a sanitizar
    
    Returns:
        NIF sanitizado (9 dígitos) ou None se inválido
    """
    if not nif:
        return None
    
    # Remover tudo exceto dígitos
    nif_clean = re.sub(r'[^\d]', '', str(nif))
    
    # Validar tamanho
    if len(nif_clean) != 9:
        return None
    
    # Validar primeiro dígito (1,2,3,5,6,7,8,9 são válidos)
    # 5 é para empresas, mas é válido
    if nif_clean[0] not in '123456789':
        return None
    
    # Rejeitar placeholders conhecidos
    placeholders = ['123456789', '000000000', '111111111', '999999999']
    if nif_clean in placeholders:
        return None
    
    return nif_clean


def sanitize_name(name: str, max_length: int = 200) -> str:
    """
    Sanitiza nome de pessoa, removendo caracteres não alfabéticos.
    
    Args:
        name: Nome a sanitizar
        max_length: Tamanho máximo
    
    Returns:
        Nome sanitizado
    """
    if not name:
        return ""
    
    # Sanitização base
    name = sanitize_string(name, max_length)
    
    # Permitir apenas letras, espaços, hífens e apóstrofes
    # (para nomes como O'Brien, García-López)
    name = re.sub(r"[^a-zA-ZÀ-ÿ\s\-']", '', name)
    
    # Normalizar espaços
    name = ' '.join(name.split())
    
    # Capitalizar cada palavra
    name = ' '.join(word.capitalize() for word in name.split())
    
    return name.strip()


def sanitize_url(url: str, max_length: int = 2000) -> str:
    """
    Sanitiza URL, permitindo apenas protocolos seguros.
    
    Args:
        url: URL a sanitizar
        max_length: Tamanho máximo
    
    Returns:
        URL sanitizado ou string vazia se inválido
    """
    if not url:
        return ""
    
    # Sanitização base (sem strip de HTML neste caso)
    url = url.strip()[:max_length]
    
    # Remover caracteres perigosos
    url = url.replace('\x00', '')
    
    # Verificar protocolo
    url_lower = url.lower()
    if not any(url_lower.startswith(p + '://') for p in ['http', 'https']):
        # Adicionar https se não tiver protocolo
        if '://' not in url:
            url = 'https://' + url
        else:
            # Protocolo inválido
            logger.warning(f"URL com protocolo inválido: {url[:30]}...")
            return ""
    
    # Verificar padrões perigosos
    dangerous = ['javascript:', 'vbscript:', 'data:', '<script', 'onclick']
    for pattern in dangerous:
        if pattern in url_lower:
            logger.warning(f"URL com padrão perigoso: {url[:30]}...")
            return ""
    
    return url


def log_sanitization_rejection(field_name: str, original_value: str, reason: str):
    """
    Regista tentativa de input malicioso para análise.
    
    Args:
        field_name: Nome do campo
        original_value: Valor original (truncado)
        reason: Motivo da rejeição
    """
    # Truncar valor para log (não guardar payloads completos)
    truncated = original_value[:50] + '...' if len(original_value) > 50 else original_value
    logger.warning(f"[SECURITY] Input rejeitado - Campo: {field_name}, Razão: {reason}, Valor: {truncated}")
