"""
====================================================================
RATE LIMITING MIDDLEWARE - ENTERPRISE SECURITY
====================================================================
Sistema de rate limiting configurável por endpoint/IP/utilizador.
Protege contra ataques DDoS e abuso de API.
====================================================================
"""
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse
import logging
import os

from middleware.client_ip import ip_do_cliente

logger = logging.getLogger(__name__)


# ====================================================================
# CONFIGURAÇÃO DE LIMITES
# ====================================================================
# Formato: "X/period" onde period pode ser: second, minute, hour, day
# ====================================================================

# Limites por tipo de endpoint
RATE_LIMITS = {
    # Autenticação - mais restritivo para prevenir brute force
    "auth": os.environ.get("RATE_LIMIT_AUTH", "10/minute"),
    
    # Endpoints gerais de leitura
    "read": os.environ.get("RATE_LIMIT_READ", "120/minute"),
    
    # Endpoints de escrita/modificação
    "write": os.environ.get("RATE_LIMIT_WRITE", "60/minute"),
    
    # Endpoints de upload de ficheiros
    "upload": os.environ.get("RATE_LIMIT_UPLOAD", "20/minute"),
    
    # Endpoints de exportação/relatórios
    "export": os.environ.get("RATE_LIMIT_EXPORT", "10/minute"),
    
    # Endpoints de IA/processamento pesado
    "ai": os.environ.get("RATE_LIMIT_AI", "20/minute"),
    
    # Limite global default
    "default": os.environ.get("RATE_LIMIT_DEFAULT", "200/minute"),
}


def _get_client_ip(request: Request) -> str:
    """
    IP real do cliente. Conta o `X-Forwarded-For` a partir da DIREITA
    (`TRUSTED_PROXY_HOPS`, por omissão 1 — Render): o primeiro elemento é o
    que o cliente envia e quem ataca muda-o a cada pedido (D-4).
    Ver `middleware/client_ip.py`.
    """
    return ip_do_cliente(request)


def _get_rate_limit_key(request: Request) -> str:
    """
    Gera chave única para rate limiting.
    
    Para utilizadores autenticados: usa user_id (rate limit individual)
    Para não autenticados: usa IP (rate limit por IP)
    
    Isto evita que múltiplos utilizadores na mesma rede partilhem o mesmo limite.
    """
    # Tentar obter user_id do header Authorization
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            import jwt
            from config import JWT_SECRET, JWT_ALGORITHM
            from services.portal_jwt_secret import segredos_de_verificacao
            token = auth_header[7:]
            payload = None
            # O staff assina com o `JWT_SECRET`; o Portal pode ter segredo próprio (D-2) — a chave
            # por processo do Portal não pode degradar para o IP quando os segredos se separam.
            for segredo in dict.fromkeys([JWT_SECRET, *segredos_de_verificacao()]):
                try:
                    payload = jwt.decode(token, segredo, algorithms=[JWT_ALGORITHM])
                    break
                except Exception:
                    continue
            user_id = (payload or {}).get("sub")
            if user_id:
                return f"user:{user_id}"
        except Exception:
            pass
        # Portal do Parceiro: família de tokens própria (outro segredo), logo
        # a decodificação acima falha e caía no IP — que o cliente falsifica
        # (D-4). Quando a assinatura é a do parceiro, conta-se por parceiro.
        try:
            from services.partner_security import chave_de_limite_do_parceiro

            chave = chave_de_limite_do_parceiro(auth_header[7:])
            if chave:
                return chave
        except Exception:
            pass
    
    # Fallback: usar IP para utilizadores não autenticados
    client_ip = _get_client_ip(request)
    return f"ip:{client_ip}"


# Instância principal do limiter
# Usa _get_rate_limit_key que diferencia utilizadores autenticados de IPs
#
# NOTA: default_limits vazio — o user_rate_limit_middleware já faz rate limiting
# por role. Aqui aplicamos limites apenas em endpoints com decorador explícito
# (@limit_auth, @limit_write, etc.) para evitar double rate limiting.
limiter = Limiter(
    key_func=_get_rate_limit_key,
    default_limits=[],  # Sem limite default — delegado ao middleware por role
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