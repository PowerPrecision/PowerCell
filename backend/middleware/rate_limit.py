"""
====================================================================
RATE LIMITING MIDDLEWARE - ENTERPRISE SECURITY
====================================================================
Sistema de rate limiting configurável por endpoint/IP/utilizador.
Protege contra ataques DDoS e abuso de API.
====================================================================
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse
import logging
import os

logger = logging.getLogger(__name__)


# ====================================================================
# CONFIGURAÇÃO DE LIMITES
# ====================================================================
# Formato: "X/period" onde period pode ser: second, minute, hour, day
# ====================================================================

# Limites por tipo de endpoint
RATE_LIMITS = {
    # Autenticação - mais restritivo para prevenir brute force
    "auth": os.environ.get("RATE_LIMIT_AUTH", "5/minute"),
    
    # Endpoints gerais de leitura
    "read": os.environ.get("RATE_LIMIT_READ", "60/minute"),
    
    # Endpoints de escrita/modificação
    "write": os.environ.get("RATE_LIMIT_WRITE", "30/minute"),
    
    # Endpoints de upload de ficheiros
    "upload": os.environ.get("RATE_LIMIT_UPLOAD", "10/minute"),
    
    # Endpoints de exportação/relatórios
    "export": os.environ.get("RATE_LIMIT_EXPORT", "5/minute"),
    
    # Endpoints de IA/processamento pesado
    "ai": os.environ.get("RATE_LIMIT_AI", "10/minute"),
    
    # Limite global default
    "default": os.environ.get("RATE_LIMIT_DEFAULT", "100/minute"),
}


def _get_client_ip(request: Request) -> str:
    """
    Obtém o IP real do cliente, considerando proxies.
    """
    # X-Forwarded-For contém lista de IPs quando há proxies
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    
    # X-Real-IP é usado por alguns proxies (ex: Nginx)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    
    # Fallback para IP directo
    return get_remote_address(request)


def _get_rate_limit_key(request: Request) -> str:
    """
    Gera chave única para rate limiting combinando IP e path.
    Permite limites diferentes por endpoint.
    """
    client_ip = _get_client_ip(request)
    # Normalizar path removendo IDs variáveis
    path = request.url.path
    # Simplificar paths com UUIDs ou IDs numéricos
    import re
    normalized_path = re.sub(r'/[a-f0-9-]{36}', '/{id}', path)  # UUIDs
    normalized_path = re.sub(r'/\d+', '/{id}', normalized_path)  # IDs numéricos
    
    return f"{client_ip}:{normalized_path}"


# Instância principal do limiter
limiter = Limiter(
    key_func=_get_client_ip,
    default_limits=[RATE_LIMITS["default"]],
    headers_enabled=True,  # Adiciona headers X-RateLimit-*
    strategy="fixed-window"  # Estratégia de janela fixa
)


# ====================================================================
# DECORADORES PARA TIPOS ESPECÍFICOS DE ENDPOINTS
# ====================================================================

def limit_auth():
    """Rate limit para endpoints de autenticação."""
    return limiter.limit(RATE_LIMITS["auth"])

def limit_read():
    """Rate limit para endpoints de leitura."""
    return limiter.limit(RATE_LIMITS["read"])

def limit_write():
    """Rate limit para endpoints de escrita."""
    return limiter.limit(RATE_LIMITS["write"])

def limit_upload():
    """Rate limit para endpoints de upload."""
    return limiter.limit(RATE_LIMITS["upload"])

def limit_export():
    """Rate limit para endpoints de exportação."""
    return limiter.limit(RATE_LIMITS["export"])

def limit_ai():
    """Rate limit para endpoints de IA."""
    return limiter.limit(RATE_LIMITS["ai"])


# ====================================================================
# HANDLER DE EXCEÇÃO
# ====================================================================

async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """
    Handler para quando o rate limit é excedido.
    Loga o evento e retorna resposta 429.
    """
    client_ip = _get_client_ip(request)
    path = request.url.path
    
    logger.warning(
        f"Rate limit excedido | IP: {client_ip} | Path: {path} | "
        f"Limite: {exc.detail}"
    )
    
    # Opcional: Registar em base de dados para análise de segurança
    # await log_rate_limit_violation(client_ip, path, exc.detail)
    
    return JSONResponse(
        status_code=429,
        content={
            "error": "Demasiadas requisições. Por favor aguarde.",
            "detail": str(exc.detail),
            "retry_after": "60 segundos"
        },
        headers={
            "Retry-After": "60",
            "X-RateLimit-Reset": "60"
        }
    )


# Log de configuração
logger.info(f"Rate limiting configurado: {RATE_LIMITS}")