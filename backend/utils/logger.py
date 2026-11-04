"""
====================================================================
CONFIGURAÇÃO CENTRALIZADA DE LOGGING — Compatível com Render
====================================================================
Garante que todos os logs são enviados para sys.stdout (não stderr)
com formato limpo e imediato, essencial para o Render capturar
logs em tempo real.

Uso:
    from utils.logger import get_logger
    logger = get_logger(__name__)
    logger.info("Mensagem de info")
    logger.error("Algo falhou", exc_info=True)

NOTA: Este módulo deve ser importado o mais cedo possível no
server.py, ANTES do logging.basicConfig() ou de qualquer outro
módulo que crie loggers.
====================================================================
"""

import sys
import logging
import os
import re


# ── Formato do Log ──
# Timestamp ISO-8601 + Nível + Nome do módulo + Mensagem
# Exemplo: 2026-06-04 14:32:01,234 INFO  routes.auth Login bem-sucedido
LOG_FORMAT = "%(asctime)s %(levelname)-5s %(name)s %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Nível de log configurável via variável de ambiente (default: INFO)
LOG_LEVEL_STR = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_LEVEL = getattr(logging, LOG_LEVEL_STR, logging.INFO)


def _configure_root_logger() -> None:
    """
    Configura o root logger com um StreamHandler para sys.stdout.

    Esta função é idempotente — só configura uma vez, mesmo que
    seja chamada múltiplas vezes (e.g. em multiprocess workers).
    """
    root = logging.getLogger()

    # Evitar configuração dupla em workers Uvicorn com fork
    if root.handlers and any(
        isinstance(h, logging.StreamHandler) and h.stream == sys.stdout
        for h in root.handlers
    ):
        return

    # Remover handlers padrão (stderr) para evitar duplicação
    root.handlers.clear()

    # Criar handler para stdout (o Render captura stdout em tempo real)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(LOG_LEVEL)

    # Aplicar formato
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
    handler.setFormatter(formatter)

    # Registar no root logger
    root.addHandler(handler)
    root.setLevel(LOG_LEVEL)

    # Silenciar loggers de bibliotecas de terceiros que são muito verbosos
    for noisy_logger in [
        "uvicorn.access",       # Cada request HTTP gera 2 linhas (não preciso)
        "httpx",                # HTTP client verboso
        "httpcore",             # HTTP core verboso
        "multipart",            # Upload parsing verboso
        "pymongo",              # MongoDB driver
        "sentry_sdk",           # Sentry internals
        "botocore",             # AWS SDK
        "urllib3",              # HTTP connection pool
        "playwright",           # Playwright browser automation
    ]:
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Factory de loggers — retorna um logger configurado com o nome do módulo.

    Args:
        name: Nome do módulo (usar __name__)

    Returns:
        Logger configurado com o formato padronizado.

    Exemplo:
        logger = get_logger(__name__)
        logger.info("Processo criado", extra={"process_id": "abc123"})
    """
    # Garantir que o root logger está configurado antes de criar child loggers
    _configure_root_logger()

    return logging.getLogger(name)


# ── Segredos fora dos logs (Nov 2026) ──
# O uvicorn regista cada handshake de WebSocket com a query string inteira:
#   "WebSocket /api/ws/notifications?token=eyJhbGciOi…" [accepted]
# e o JWT completo (válido durante horas) ficava nos logs do Render, ao alcance de quem os lê.
_PARAMETRO_SECRETO = re.compile(
    r"(?i)\b((?:access_|refresh_|magic_|reset_)?token|api_key|apikey|password|secret)=([^&\s\"']+)"
)


def ocultar_segredos(texto: str) -> str:
    """`?token=eyJ…` → `?token=[oculto]` (e afins). Pura; usada pelo filtro e pelos testes."""
    return _PARAMETRO_SECRETO.sub(lambda m: f"{m.group(1)}=[oculto]", texto)


class FiltroDeSegredos(logging.Filter):
    """Reescreve a mensagem de um registo que leve um segredo numa query string. Nunca descarta registos."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            mensagem = record.getMessage()
        except Exception:  # noqa: BLE001 - um registo mal formado segue como está
            return True
        if "=" in mensagem:
            limpa = ocultar_segredos(mensagem)
            if limpa != mensagem:
                record.msg, record.args = limpa, None
        return True


_FILTRO_DE_SEGREDOS = FiltroDeSegredos()


def _instalar_filtro_de_segredos() -> None:
    """Idempotente. Nos loggers do uvicorn (têm handlers próprios e não propagam até ao root) e no root."""
    for nome in ("uvicorn.error", "uvicorn.access", "uvicorn", ""):
        alvo = logging.getLogger(nome)
        if _FILTRO_DE_SEGREDOS not in alvo.filters:
            alvo.addFilter(_FILTRO_DE_SEGREDOS)
    for handler in logging.getLogger().handlers:
        if _FILTRO_DE_SEGREDOS not in handler.filters:
            handler.addFilter(_FILTRO_DE_SEGREDOS)


# ── Auto-configuração na importação ──
# Quando este módulo é importado, configura o root logger automaticamente.
_configure_root_logger()
_instalar_filtro_de_segredos()
