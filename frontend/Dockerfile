# ====================================================================
# DOCKERFILE - CREDITOIMO FRONTEND
# ====================================================================
# Multi-stage build para aplicação React
#
# Build: docker build -t creditoimo-frontend .
# ====================================================================

# -----------------------------
# STAGE 1: Build
# -----------------------------
FROM node:20-alpine AS builder

WORKDIR /app

# Copiar package files
COPY package.json yarn.lock ./

# Instalar dependências
RUN yarn install --frozen-lockfile

# Copiar código fonte
COPY . .

# Build arguments para variáveis de ambiente
ARG REACT_APP_BACKEND_URL
ENV REACT_APP_BACKEND_URL=${REACT_APP_BACKEND_URL}

# Build da aplicação
RUN yarn build


# -----------------------------
# STAGE 2: Production (serve)
# -----------------------------
FROM node:20-alpine AS production

WORKDIR /app

# Instalar serve para servir ficheiros estáticos
RUN npm install -g serve

# Copiar build do stage anterior
COPY --from=builder /app/build ./build

# Utilizador não-root
RUN addgroup -g 1001 -S nodejs && \
    adduser -S reactuser -u 1001 -G nodejs && \
    chown -R reactuser:nodejs /app

USER reactuser

# Expor porta
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:3000/ || exit 1

# Comando
CMD ["serve", "-s", "build", "-l", "3000"]


# -----------------------------
# STAGE 3: Development
# -----------------------------
FROM node:20-alpine AS development

WORKDIR /app

# Copiar package files
COPY package.json yarn.lock ./

# Instalar dependências (incluindo devDependencies)
RUN yarn install

# Copiar código fonte
COPY . .

# Expor porta
EXPOSE 3000

# Hot reload
CMD ["yarn", "start"]
