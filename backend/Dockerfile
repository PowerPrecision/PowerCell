# ====================================================================
# DOCKERFILE - POWERCELL BACKEND
# ====================================================================
# Utiliza a imagem oficial do Playwright com Chromium pré-instalado.
# Isto elimina a necessidade de instalar browsers manualmente no build
# e resolve os erros de exit code 1 no Render.
#
# A imagem base já inclui:
#   - Python 3.12
#   - Chromium + todas as dependências de sistema
#   - PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
#
# IMPORTANTE: a versão do pacote playwright em requirements.txt DEVE
# corresponder à versão desta imagem (v1.52.0) para garantir que o
# binário do browser pré-instalado é compatível com o package Python.
#
# Build: docker build -t powercell-backend .
# Run:   docker run -p 8001:8001 powercell-backend
# ====================================================================

FROM mcr.microsoft.com/playwright/python:v1.52.0-noble

# Prevent interactive prompts (tzdata, etc.)
ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Etc/UTC

# ── Variáveis de ambiente ──
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8001 \
    UVICORN_WORKERS=1 \
    APP_ENV=production \
    PORT=8001

# ── Dependências de runtime adicionais ──
# A imagem Playwright já inclui curl, wget, e TODAS as deps do Chromium.
# Só precisamos de adicionar libmagic1 para o python-magic.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean


# ── Working directory ──
WORKDIR /app

# ── Instalar dependências Python ──
# O pacote playwright em requirements.txt deve ser ==1.52.0 para
# compatibilidade com o Chromium pré-instalado na imagem base.
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copiar código da aplicação ──
# PACOTE AI: dockerContext é agora o repo root (para incluir worklog.md
# e CHANGELOG.md na raiz). Copia-se backend/ para /app/ e os ficheiros
# da raiz para /app/ também (para o changelog_service os encontrar).
COPY backend/ /app/
COPY worklog.md CHANGELOG.md /app/

# ── Permissões ──
# A imagem Playwright já traz o utilizador pwuser (UID/GID 1000).
# Atribuímos ownership de /app ao pwuser. Os browsers em /ms-playwright
# já têm permissões de leitura global (a imagem base garante isto).
RUN chown -R pwuser:pwuser /app

# ── Mudar para utilizador não-root (nativo da imagem Playwright) ──
USER pwuser

# ── Health check ──
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# ── Expor porta ──
EXPOSE 8001

# ── Comando de arranque ──
# DEV: 1 worker (poupar RAM — 512MB no Render)
# PROD: múltiplos workers (definir UVICORN_WORKERS no Render)
# Se ENVIRONMENT=dev, força 1 worker independentemente de UVICORN_WORKERS.
CMD ["sh", "-c", "if [ \"$ENVIRONMENT\" = 'dev' ] || [ \"$ENVIRONMENT\" = 'development' ]; then WORKERS=1; else WORKERS=${UVICORN_WORKERS:-1}; if [ \"$WORKERS\" -gt 2 ] 2>/dev/null; then echo 'WARNING: UVICORN_WORKERS capped to 2 (2GB RAM limit)'; WORKERS=2; fi; fi && echo \"Starting Uvicorn with $WORKERS workers\" && uvicorn server:app --host 0.0.0.0 --port ${PORT:-${UVICORN_PORT}} --workers $WORKERS"]
