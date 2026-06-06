"""
====================================================================
MIDDLEWARE DE RASTREABILIDADE — Logging de Pedidos HTTP
====================================================================
Interceta TODOS os pedidos HTTP e regista:
  - Sucesso: logger.info com método, path, status, duração, user ID
  - Falha:   logger.error com traceback completo e contexto do utilizador

Formato de saída (sucesso):
  [Method: GET] [Path: /api/processos/123] [Status: 200] [Duration: 45ms] [User: admin@powercell.pt (5)]

Formato de saída (erro):
  [Method: POST] [Path: /api/processos] [Status: 500] [Duration: 1230ms] [User: admin@powercell.pt (5)]
  Traceback: ...

NOTA: Rotas de health check (/health, /health/ready) são ignoradas
para não poluir os logs com polling do Render a cada 30s.
====================================================================
"""

import time
import traceback
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from utils.logger import get_logger

logger = get_logger(__name__)

# Rotas a ignorar (health checks do Render, métricas, etc.)
SKIP_PATHS = {"/health", "/health/ready", "/metrics", "/favicon.ico"}


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware de rastreabilidade que regista todos os pedidos HTTP.

    Para pedidos bem-sucedidos (2xx/3xx/4xx): logger.info
    Para pedidos com erro interno (5xx): logger.error com traceback

    Extrai o User ID e role do request.state.user (populado pelo
    middleware de autenticação) para correlacionar ações a utilizadores.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Ignorar health checks e rotas estáticas
        if request.url.path in SKIP_PATHS:
            return await call_next(request)

        # Capturar timestamp de início
        start_time = time.perf_counter()

        # Variáveis para o contexto de erro
        status_code = 500
        exc_info = None

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception as exc:
            # Se o pedido lançou excepção (não tratada pelo exception handler),
            # capturamos aqui para garantir que é logada
            exc_info = exc
            status_code = 500
            raise  # Re-lançar para o exception handler global
        finally:
            # Calcular duração
            duration_ms = int((time.perf_counter() - start_time) * 1000)

            # Extrair informação do utilizador autenticado
            user_info = self._extract_user_info(request)

            # Formatar mensagem de log
            method = request.method
            path = request.url.path
            log_prefix = f"[Method: {method}] [Path: {path}] [Status: {status_code}] [Duration: {duration_ms}ms]"

            if status_code >= 500:
                # Erro interno — log detalhado com contexto
                if exc_info:
                    tb = traceback.format_exception(type(exc_info), exc_info, exc_info.__traceback__)
                    tb_str = "".join(tb)
                    logger.error(
                        f"{log_prefix} {user_info}\n"
                        f"  Ação: {method} {path}\n"
                        f"  Traceback:\n{tb_str}"
                    )
                else:
                    # Erro 500 veio do exception handler global (já logado lá)
                    # Ainda assim registamos o pedido para rastreabilidade
                    logger.error(
                        f"{log_prefix} {user_info}\n"
                        f"  Ação: {method} {path} (erro tratado pelo exception handler global)"
                    )
            elif status_code >= 400:
                # Erro de cliente (4xx) — log como warning para debugging
                logger.warning(f"{log_prefix} {user_info}")
            else:
                # Sucesso (2xx/3xx) — log informativo
                logger.info(f"{log_prefix} {user_info}")

    @staticmethod
    def _extract_user_info(request: Request) -> str:
        """
        Extrai informação do utilizador autenticado do request.state.

        O middleware de autenticação (get_current_user) popula
        request.state.user com o dict do utilizador.

        Returns:
            String formatada: "[User: email (id)]" ou "[User: anónimo]"
        """
        try:
            user = getattr(request.state, "user", None)
            if user and isinstance(user, dict):
                user_id = user.get("id", "?")
                email = user.get("email", "?")
                role = user.get("role", "")
                return f"[User: {email} ({user_id}) role={role}]"
        except Exception:
            pass

        return "[User: anónimo]"
