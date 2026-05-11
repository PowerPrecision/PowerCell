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

# ── Instalar TODAS as dependências de sistema + Playwright Chromium em 1 layer ──
# Lista de deps obtida com: playwright install-deps --dry-run chromium
# NÃO usamos --with-deps porque esse flag invoca sudo (não existe em Docker).
# Em vez disso, instalamos as deps manualmente e depois só o browser.
#
# NOTA: Os pacotes com sufixo t64 são pacotes de transição do Debian 12 (bookworm).
# O python:3.11-slim é baseado em bookworm, por isso precisa destes nomes.
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Runtime gerais
    libmagic1 \
    curl \
    # ── Playwright Chromium dependencies (Debian 12 / bookworm) ──
    # Core rendering (t64 = Debian 12 64-bit time_t transition packages)
    libasound2t64 \
    libatk-bridge2.0-0t64 \
    libatk1.0-0t64 \
    libatspi2.0-0t64 \
    libcairo2 \
    libcups2t64 \
    libdbus-1-3 \
    libdrm2 \
    libgbm1 \
    libglib2.0-0t64 \
    libnspr4 \
    libnss3 \
    libpango-1.0-0 \
    libx11-6 \
    libxcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxkbcommon0 \
    libxrandr2 \
    # Virtual framebuffer (Xvfb) — necessário para --headless=new em alguns ambientes
    xvfb \
    # Fonts (necessário para renderização de PDFs com caracteres especiais/CJK)
    fonts-noto-color-emoji \
    fonts-unifont \
    xfonts-scalable \
    fonts-liberation \
    fonts-ipafont-gothic \
    fonts-wqy-zenhei \
    fonts-tlwg-loma-otf \
    fonts-freefont-ttf \
    # Font rendering libraries
    libfontconfig1 \
    libfreetype6 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Instalar Playwright Chromium browser (apenas o browser, deps já instaladas acima)
# PLAYWRIGHT_BROWSERS_PATH garante que o browser fica em /ms-playwright (partilhado)
RUN playwright install chromium \
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
