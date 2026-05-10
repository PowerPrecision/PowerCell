"""
====================================================================
RATE LIMITING POR UTILIZADOR AUTENTICADO
====================================================================
Sistema de rate limiting diferenciado por role do utilizador.
Usa cache in-memory com TTL para tracking de requests.

Limites por role:
- admin: 1000 req/min
- consultor/mediador: 200 req/min
- cliente: 100 req/min
====================================================================
"""
import time
import asyncio
from collections import defaultdict
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, Depends
from functools import wraps
import logging

logger = logging.getLogger(__name__)


# ====================================================================
# CONFIGURAÇÃO DE LIMITES POR ROLE
# ====================================================================
RATE_LIMITS_BY_ROLE = {
    # Administradores - limite alto
    "admin": {"requests": 2000, "window": 60},  # 2000 req/min
    "ceo": {"requests": 2000, "window": 60},
    "diretor": {"requests": 1500, "window": 60},
    
    # Staff operacional - limite elevado (CRM faz muitos pedidos por página)
    "consultor": {"requests": 600, "window": 60},  # 600 req/min
    "intermediario": {"requests": 600, "window": 60},
    "administrativo": {"requests": 600, "window": 60},
    "indexacao": {"requests": 600, "window": 60},
    
    # Parceiros - ghost users sem acesso à plataforma
    "parceiro": {"requests": 400, "window": 60},
    
    # Clientes - limite médio
    "cliente": {"requests": 400, "window": 60},  # 400 req/min
    
    # Default para roles desconhecidos
    "default": {"requests": 600, "window": 60},  # 600 req/min (generoso para JWT fallback)
}


class InMemoryRateLimiter:
    """
    Rate limiter in-memory com suporte a múltiplas janelas.
    Thread-safe usando locks assíncronos.
    """
    
    def __init__(self, cleanup_interval: int = 300):
        """
        Args:
            cleanup_interval: Intervalo em segundos para limpeza de entradas expiradas
        """
        # Estrutura: {user_id: {timestamp: count, ...}}
        self._requests: Dict[str, list] = defaultdict(list)
        self._lock = asyncio.Lock()
        self._cleanup_interval = cleanup_interval
        self._last_cleanup = time.time()
    
    async def is_allowed(
        self,
        user_id: str,
        role: str,
        endpoint: Optional[str] = None
    ) -> tuple[bool, Dict[str, Any]]:
        """
        Verifica se o request é permitido para o utilizador.
        
        Returns:
            (is_allowed, info_dict)
            info_dict contém: remaining, limit, reset_at
        """
        limits = RATE_LIMITS_BY_ROLE.get(role, RATE_LIMITS_BY_ROLE["default"])
        max_requests = limits["requests"]
        window_seconds = limits["window"]
        
        now = time.time()
        window_start = now - window_seconds
        
        async with self._lock:
            # Limpar entradas antigas deste utilizador
            self._requests[user_id] = [
                ts for ts in self._requests[user_id]
                if ts > window_start
            ]
            
            # Contar requests na janela actual
            current_count = len(self._requests[user_id])
            
            # Verificar se está dentro do limite
            if current_count >= max_requests:
                # Calcular quando reseta
                oldest_request = min(self._requests[user_id]) if self._requests[user_id] else now
                reset_at = oldest_request + window_seconds
                
                return False, {
                    "remaining": 0,
                    "limit": max_requests,
                    "reset_at": int(reset_at),
                    "retry_after": int(reset_at - now),
                }
            
            # Registar este request
            self._requests[user_id].append(now)
            
            # Limpeza periódica
            if now - self._last_cleanup > self._cleanup_interval:
                await self._cleanup_old_entries()
            
            return True, {
                "remaining": max_requests - current_count - 1,
                "limit": max_requests,
                "reset_at": int(now + window_seconds),
            }
    
    async def _cleanup_old_entries(self):
        """Remove entradas expiradas para libertar memória."""
        now = time.time()
        max_window = max(limits["window"] for limits in RATE_LIMITS_BY_ROLE.values())
        cutoff = now - max_window
        
        users_to_remove = []
        for user_id, timestamps in self._requests.items():
            self._requests[user_id] = [ts for ts in timestamps if ts > cutoff]
            if not self._requests[user_id]:
                users_to_remove.append(user_id)
        
        for user_id in users_to_remove:
            del self._requests[user_id]
        
        self._last_cleanup = now
        logger.debug(f"Rate limiter cleanup: removed {len(users_to_remove)} inactive users")
    
    async def get_status(self, user_id: str, role: str) -> Dict[str, Any]:
        """Retorna estado actual do rate limit para o utilizador."""
        limits = RATE_LIMITS_BY_ROLE.get(role, RATE_LIMITS_BY_ROLE["default"])
        max_requests = limits["requests"]
        window_seconds = limits["window"]
        
        now = time.time()
        window_start = now - window_seconds
        
        async with self._lock:
            # Contar requests válidos
            valid_requests = [
                ts for ts in self._requests.get(user_id, [])
                if ts > window_start
            ]
            current_count = len(valid_requests)
        
        return {
            "user_id": user_id,
            "role": role,
            "current_requests": current_count,
            "limit": max_requests,
            "remaining": max(0, max_requests - current_count),
            "window_seconds": window_seconds,
            "reset_at": int(now + window_seconds),
        }
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas gerais do rate limiter."""
        total_users = len(self._requests)
        total_requests = sum(len(ts) for ts in self._requests.values())
        
        return {
            "active_users": total_users,
            "tracked_requests": total_requests,
            "last_cleanup": self._last_cleanup,
        }


# Instância global do rate limiter
user_rate_limiter = InMemoryRateLimiter()


async def check_user_rate_limit(request: Request, user: Optional[dict] = None):
    """
    Middleware/dependency para verificar rate limit do utilizador.
    Adiciona headers X-RateLimit-* à resposta.
    """
    if not user:
        # Se não há utilizador autenticado, usa rate limit por IP
        return
    
    user_id = user.get("id", "unknown")
    role = user.get("role", "default")
    endpoint = request.url.path
    
    allowed, info = await user_rate_limiter.is_allowed(user_id, role, endpoint)
    
    # Guardar info para adicionar headers depois
    request.state.rate_limit_info = info
    
    if not allowed:
        logger.warning(
            f"Rate limit excedido | User: {user_id} | Role: {role} | "
            f"Endpoint: {endpoint} | Retry after: {info.get('retry_after')}s"
        )
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Demasiadas requisições",
                "message": f"Limite de {info['limit']} req/min excedido para o seu nível de acesso",
                "retry_after": info.get("retry_after", 60),
            },
            headers={
                "Retry-After": str(info.get("retry_after", 60)),
                "X-RateLimit-Limit": str(info["limit"]),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(info["reset_at"]),
            }
        )


def rate_limit_by_user():
    """
    Decorator para aplicar rate limit por utilizador autenticado.
    Usa em conjunto com Depends(get_current_user).
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = kwargs.get("request")
            user = kwargs.get("user")
            
            if request and user:
                await check_user_rate_limit(request, user)
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# Exportar configuração para documentação
def get_rate_limits_config() -> Dict[str, Dict[str, int]]:
    """Retorna configuração de limites por role (deep copy)."""
    import copy
    return copy.deepcopy(RATE_LIMITS_BY_ROLE)


__all__ = [
    "user_rate_limiter",
    "check_user_rate_limit",
    "rate_limit_by_user",
    "get_rate_limits_config",
    "RATE_LIMITS_BY_ROLE",
]
