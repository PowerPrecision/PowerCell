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

# Prevent interactive prompts (tzdata, etc.)
ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Etc/UTC

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

# Criar utilizador não-root para segurança
RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

# Copiar dependências do builder
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# ── Dependências de runtime básicas ──
# wget e gnupg necessários para Playwright install-deps (chaves de repositório)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    curl \
    wget \
    gnupg \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# ── Playwright: instalar browser + dependências de sistema (como root) ──
# ORDEM CRÍTICA:
#   1. Criar pasta do browser com permissões corretas
#   2. playwright install chromium   → descarrega o binário Chromium
#   3. playwright install-deps chromium → instala deps de OS via apt-get (auto-detecta Debian/Ubuntu)
#   4. Limpar cache do apt
#   5. Ajustar permissões para appuser
#
# NOTA: NÃO usamos --with-deps (esse flag invoca sudo, não existe em Docker).
# Em vez disso, usamos o comando separado "install-deps" que corre apt-get diretamente.
# O install-deps faz o seu próprio apt-get update, pelo que não precisamos de
# manter as listas de apt entre passos.

# 1. Criar pasta do browser ANTES da instalação
RUN mkdir -p /ms-playwright

# 2. Instalar Chromium (download do binário)
RUN playwright install chromium

# 3. Instalar dependências de sistema do Chromium (apt-get automático)
RUN playwright install-deps chromium

# 4. Limpar cache do apt (após install-deps ter corrido apt-get)
RUN rm -rf /var/lib/apt/lists/* && apt-get clean

# 5. Ajustar permissões do browser para o utilizador da aplicação
RUN chown -R appuser:appgroup /ms-playwright

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
