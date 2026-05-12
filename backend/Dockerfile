# ====================================================================
# DOCKERFILE - POWERCELL BACKEND
# ====================================================================
# Utiliza a imagem oficial do Playwright com Chromium pré-instalado.
# Isto elimina a necessidade de instalar browsers manualmente no build
# e resolve os erros de exit code 1 no Render.
#
# A imagem base já inclui:
#   - Python 3.10
#   - Chromium + todas as dependências de sistema
#   - PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
#
# IMPORTANTE: a versão do pacote playwright em requirements.txt DEVE
# corresponder à versão desta imagem (v1.42.0) para garantir que o
# binário do browser pré-instalado é compatível com o package Python.
#
# Build: docker build -t powercell-backend .
# Run:   docker run -p 8001:8001 powercell-backend
# ====================================================================

FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

# Prevent interactive prompts (tzdata, etc.)
ENV DEBIAN_FRONTEND=noninteractive \
    TZ=Etc/UTC

# ── Variáveis de ambiente ──
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8001 \
    UVICORN_WORKERS=4 \
    APP_ENV=production \
    PORT=8001

# ── Dependências de runtime adicionais ──
# A imagem Playwright já inclui curl, wget, e TODAS as deps do Chromium.
# Só precisamos de adicionar libmagic1 para o python-magic.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# ── Criar utilizador não-root para segurança ──
RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

# ── Working directory ──
WORKDIR /app

# ── Instalar dependências Python ──
# O pacote playwright em requirements.txt deve ser ==1.42.0 para
# compatibilidade com o Chromium pré-instalado na imagem base.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copiar código da aplicação ──
COPY . .

# ── Permissões ──
# Apenas /app — os browsers em /ms-playwright já têm permissões
# de leitura global (a imagem base garante isto).
RUN chown -R appuser:appgroup /app

# ── Mudar para utilizador não-root ──
USER appuser

# ── Health check ──
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# ── Expor porta ──
EXPOSE 8001

# ── Comando de arranque ──
# Produção: múltiplos workers
# Render: usa a variável PORT se definida, senão usa UVICORN_PORT
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-${UVICORN_PORT}} --workers ${UVICORN_WORKERS}"]
