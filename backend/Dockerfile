# ====================================================================
# DOCKERFILE - CREDITOIMO BACKEND
# ====================================================================
# Imagem otimizada para produção com FastAPI
#
# Build: docker build -t creditoimo-backend .
# Run:   docker run -p 8001:8001 creditoimo-backend
# ====================================================================

# -----------------------------
# STAGE 1: Builder
# -----------------------------
FROM python:3.11-slim AS builder

# Prevenir criação de .pyc e buffering de output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Instalar dependências de build
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements e instalar dependências
COPY requirements.txt .
RUN pip install --user --no-warn-script-location -r requirements.txt


# -----------------------------
# STAGE 2: Production
# -----------------------------
FROM python:3.11-slim AS production

# Metadata
LABEL maintainer="CreditoIMO <dev@creditoimo.pt>" \
      version="2.0" \
      description="CreditoIMO Backend - Sistema de Gestão de Crédito Habitação"

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    # Uvicorn settings
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8001 \
    UVICORN_WORKERS=4 \
    # App settings
    APP_ENV=production \
    # Render porta (será sobrescrita pelo Render se disponível)
    PORT=8001 \
    # Playwright: instalar browsers em path partilhado (acessível pelo appuser)
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Instalar dependências de runtime (não-Chromium)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Criar utilizador não-root para segurança
RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

# Copiar dependências do builder
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# Instalar Playwright Chromium browser COM dependências de sistema automáticas
# --with-deps instala TODAS as libs de sistema necessárias (libnss3, libgbm1, etc.)
# Correr ANTES de mudar para utilizador não-root (requer apt-get)
# PLAYWRIGHT_BROWSERS_PATH garante que o browser fica em /ms-playwright (partilhado)
RUN playwright install --with-deps chromium \
    && chown -R appuser:appgroup /ms-playwright

# Criar diretórios da aplicação
WORKDIR /app
RUN mkdir -p /app/temp /app/logs && chown -R appuser:appgroup /app

# Copiar código da aplicação
COPY --chown=appuser:appgroup . .

# Mudar para utilizador não-root
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Expor porta
EXPOSE 8001

# Comando de arranque
# Produção: múltiplos workers
# Render: usa a variável PORT se definida, senão usa UVICORN_PORT
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-${UVICORN_PORT}} --workers ${UVICORN_WORKERS}"]


# -----------------------------
# STAGE 3: Development (opcional)
# -----------------------------
FROM production AS development

# Voltar a root para instalar dev dependencies
USER root

# Instalar ferramentas de desenvolvimento
RUN pip install --no-cache-dir \
    pytest \
    pytest-asyncio \
    pytest-cov \
    httpx \
    black \
    ruff \
    ipython

# Voltar ao utilizador app
USER appuser

# Override para development com hot reload
ENV UVICORN_WORKERS=1
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
