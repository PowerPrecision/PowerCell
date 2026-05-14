import os
import subprocess
import logging
from datetime import datetime, timezone

# v2025-01-webmail-sync

# Garantir que libmagic está instalado (necessário para python-magic)
def ensure_libmagic():
    try:
        import magic
        magic.Magic()  # Testa se consegue criar instância
    except (ImportError, OSError) as e:
        logging.warning(f"libmagic não encontrado, a instalar... ({e})")
        try:
            subprocess.run(
                ["apt-get", "update"], 
                check=True, capture_output=True, timeout=60
            )
            subprocess.run(
                ["apt-get", "install", "-y", "libmagic1"], 
                check=True, capture_output=True, timeout=60
            )
            logging.info("libmagic instalado com sucesso")
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as install_error:
            logging.error(f"Erro ao instalar libmagic: {install_error}")

ensure_libmagic()

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.integrations.pymongo import PyMongoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from config import (
    CORS_ORIGINS, CORS_ORIGIN_REGEX, CORS_ALLOW_CREDENTIALS, CORS_ALLOW_METHODS, 
    CORS_ALLOW_HEADERS, CORS_MAX_AGE,
    SENTRY_DSN, SENTRY_ENVIRONMENT, SENTRY_TRACES_SAMPLE_RATE,
    SENTRY_PROFILES_SAMPLE_RATE, SENTRY_SEND_DEFAULT_PII
)
from database import db, client
from middleware.rate_limit import limiter
from routes import (
    auth_router, processes_router, admin_router, users_router,
    deadlines_router, activities_router,
    public_router, stats_router, ai_router, documents_router
)
# Outras rotas
from routes.alerts import router as alerts_router
from routes.websocket import router as websocket_router
from routes.push_notifications import router as push_notifications_router
from routes.tasks import router as tasks_router
from routes.emails import router as emails_router  # doc_router removido - rotas agora no router principal
from routes.trello import router as trello_router
from routes.ai_bulk import router as ai_bulk_router
from routes.leads import router as leads_router
from routes.match import router as match_router
from routes.system_config import router as system_config_router
from routes.properties import router as properties_router
from routes.clients import router as clients_router
from routes.gdpr import router as gdpr_router
from routes.backup import router as backup_router
from routes.scraper import router as scraper_router
from routes.minutas import router as minutas_router
from routes.ai_agent import router as ai_agent_router
from routes.templates import router as templates_router
from routes.onedrive import router as onedrive_router
from routes.search import router as search_router
from routes.storage import router as storage_router
from routes.ai_import_logs import router as ai_import_logs_router
from routes.chat import router as chat_router
from routes.my_clients import router as my_clients_router
from routes.admin_ai import router as admin_ai_router
from routes.admin_storage import router as admin_storage_router
from routes.diagnostics import router as diagnostics_router
from routes.rgpd import router as rgpd_router
from routes.temp_links import router as temp_links_router
from routes.admin_encryption import router as admin_encryption_router
from routes.restore import router as restore_router
from routes.automation import router as automation_router
from routes.form_config import router as form_config_router
from routes.async_jobs import router as async_jobs_router
from routes.audit import router as audit_router
from routes.annotations import router as annotations_router
from routes.finance import router as finance_router
from routes.admin_migration import router as admin_migration_router
from routes.task_logs import router as task_logs_router
from routes.portal import router as portal_router
from routes.google_auth import router as google_auth_router
from routes.shared_email import router as shared_email_router
from routes.companies import router as companies_router
from routes.portal_settings import router as portal_settings_router
from routes.ai_analysis import router as ai_analysis_router
from routes.announcements import router as announcements_router

# Configuração Sentry
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        profiles_sample_rate=SENTRY_PROFILES_SAMPLE_RATE,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            StarletteIntegration(transaction_style="endpoint"),
            PyMongoIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        send_default_pii=SENTRY_SEND_DEFAULT_PII,
        attach_stacktrace=True,
    )

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Sistema de Gestão de Processos")

# Background tasks storage to prevent garbage collection
_background_tasks: set = set()


# ====================================================================
# SECURITY HEADERS MIDDLEWARE
# Adiciona headers de segurança a todas as respostas HTTP
# ====================================================================
@app.middleware("http")
async def add_security_headers(request, call_next):
    """
    Middleware para adicionar headers de segurança HTTP.
    
    Headers implementados:
    - X-Frame-Options: Previne clickjacking
    - X-Content-Type-Options: Previne MIME-type sniffing
    - X-XSS-Protection: Activa filtro XSS do browser
    - Strict-Transport-Security: Força HTTPS
    - Referrer-Policy: Controla informação de referrer
    - Content-Security-Policy: Controla recursos permitidos
    - Permissions-Policy: Restringe funcionalidades do browser
    """
    response = await call_next(request)
    
    # Prevenir clickjacking - não permite embedding em frames
    response.headers["X-Frame-Options"] = "DENY"
    
    # Prevenir MIME-type sniffing
    response.headers["X-Content-Type-Options"] = "nosniff"
    
    # Activar filtro XSS do browser (legacy, mas ainda útil)
    response.headers["X-XSS-Protection"] = "1; mode=block"
    
    # Forçar HTTPS por 1 ano, incluir subdomínios
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    
    # Controlar informação de referrer
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    
    # Content Security Policy - restritiva mas permitindo API funcionar
    # Permite: self para scripts/styles, data: para imagens base64
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "connect-src 'self' https:; "
        "frame-ancestors 'none';"
    )
    
    # Permissions Policy - restringir funcionalidades do browser
    response.headers["Permissions-Policy"] = (
        "accelerometer=(), "
        "camera=(), "
        "geolocation=(), "
        "gyroscope=(), "
        "magnetometer=(), "
        "microphone=(), "
        "payment=(), "
        "usb=()"
    )
    
    # Prevenir cache de endpoints da API
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    
    return response


# ====================================================================
# USER-BASED RATE LIMITING MIDDLEWARE
# Aplica limites diferenciados por role do utilizador
# ====================================================================
from middleware.user_rate_limit import user_rate_limiter
import jwt
from config import JWT_SECRET, JWT_ALGORITHM

@app.middleware("http")
async def user_rate_limit_middleware(request, call_next):
    """
    Middleware para rate limiting baseado no utilizador autenticado.
    
    Limites por role (ver middleware/user_rate_limit.py):
    - admin/ceo: 2000 req/min
    - diretor: 1500 req/min
    - consultor/mediador/staff: 600 req/min
    - cliente/parceiro: 400 req/min
    - default (JWT fallback): 600 req/min
    """
    # Nunca rate-limitar pedidos OPTIONS/HEAD (CORS preflight + health checks)
    if request.method in ("OPTIONS", "HEAD"):
        return await call_next(request)
    
    # Apenas aplicar a endpoints da API (não a estáticos, docs, etc.)
    if not request.url.path.startswith("/api/"):
        return await call_next(request)
    
    # Extrair token do header Authorization
    auth_header = request.headers.get("Authorization", "")
    user_id = None
    role = "default"
    
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = payload.get("sub")
            role = payload.get("role", "default")
        except jwt.ExpiredSignatureError:
            # Token expirado - deixar passar para o handler de auth
            pass
        except jwt.InvalidTokenError:
            # Token inválido - usar IP como fallback
            pass
    
    # Se não há user_id, usar IP como identificador
    if not user_id:
        user_id = f"ip:{request.headers.get('X-Forwarded-For', request.client.host if request.client else 'unknown')}"
        role = "default"
    
    # Verificar rate limit
    allowed, info = await user_rate_limiter.is_allowed(user_id, role)
    
    if not allowed:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=429,
            content={
                "detail": f"Limite de {info['limit']} requisições/minuto excedido",
                "retry_after": info.get("retry_after", 60)
            },
            headers={
                "Retry-After": str(info.get("retry_after", 60)),
                "X-RateLimit-Limit": str(info["limit"]),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(info["reset_at"]),
            }
        )
    
    # Executar request
    response = await call_next(request)
    
    # Adicionar headers de rate limit à resposta
    response.headers["X-RateLimit-Limit"] = str(info["limit"])
    response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
    response.headers["X-RateLimit-Reset"] = str(info["reset_at"])
    
    return response


# CONFIGURAÇÃO DE RATE LIMIT
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORREÇÃO: Se estiver em testes, desativar o limitador completamente
if os.getenv("TESTING") == "true":
    limiter.enabled = False


# ====================================================================
# EXCEPTION HANDLER GLOBAL - Registar erros no sistema de logs
# ====================================================================
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import HTTPException, RequestValidationError

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """
    Handler global para HTTPExceptions.
    Regista erros 4xx e 5xx no sistema de logs para análise.
    Inclui headers CORS para garantir que erros não bloqueiam o frontend.
    """
    # Só registar erros significativos (não 401/403 de autenticação normal)
    if exc.status_code >= 500 or exc.status_code in [400, 404]:
        try:
            from services.system_error_logger import system_error_logger
            
            # Determinar severidade baseada no código
            if exc.status_code >= 500:
                severity = "error"
            elif exc.status_code == 404:
                severity = "warning"
            else:
                severity = "info"
            
            # Extrair user_id do request se disponível
            user_id = None
            if hasattr(request.state, 'user'):
                user_id = request.state.user.get('id')
            
            await system_error_logger.log_error(
                error_type=f"http_{exc.status_code}",
                message=str(exc.detail),
                component="api",
                details={
                    "path": str(request.url.path),
                    "method": request.method,
                    "status_code": exc.status_code,
                    "query_params": dict(request.query_params),
                },
                severity=severity,
                user_id=user_id,
                request_path=str(request.url.path)
            )
        except (IOError, OSError) as log_error:
            logger.warning(f"Erro ao registar log: {log_error}")
    
    # Obter origin do request para CORS
    origin = request.headers.get("origin", "*")
    
    # Verificar se a origin é permitida
    allowed_origin = None
    if origin in CORS_ORIGINS:
        allowed_origin = origin
    elif CORS_ORIGIN_REGEX:
        import re
        for pattern in CORS_ORIGIN_REGEX:
            if re.match(pattern, origin):
                allowed_origin = origin
                break
    
    headers = {}
    if allowed_origin:
        headers = {
            "Access-Control-Allow-Origin": allowed_origin,
            "Access-Control-Allow-Credentials": "true",
        }
    
    # Prevenir cache de respostas de erro (evita browser servir 404 cached)
    headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    headers["Pragma"] = "no-cache"
    headers["Expires"] = "0"
    
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers=headers
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Handler para erros de validação Pydantic (422).
    Loga os detalhes do erro para debug sem expor dados sensíveis ao cliente.

    NOTA: exc.errors() pode conter 'ctx' com excepções Python (ex: ValueError)
    que não são JSON-serializáveis. Usamos json.loads(exc.json()) para
    obter uma representação segura para JSON.
    """
    import json as _json

    # Usar exc.json() do Pydantic para obter JSON seguro (serializa ctx correctamente)
    # e depois fazer parse de volta para dict para o JSONResponse
    try:
        safe_errors = _json.loads(exc.json())
    except Exception:
        # Fallback: extrair campos seguros manualmente
        safe_errors = []
        for err in exc.errors():
            safe_err = {
                "type": err.get("type"),
                "loc": err.get("loc"),
                "msg": err.get("msg"),
                "input": err.get("input") if isinstance(err.get("input"), (str, int, float, bool, type(None), list, dict)) else str(err.get("input")),
            }
            safe_errors.append(safe_err)

    logger.warning(
        f"Validation error on {request.method} {request.url.path}: "
        f"errors={safe_errors}"
    )
    # Retornar erro formatado ao cliente
    return JSONResponse(
        status_code=422,
        content={"detail": safe_errors},
        headers={"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Credentials": "true"}
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """
    Handler para excepções não tratadas.
    Regista o erro e retorna 500.
    Inclui headers CORS para garantir que erros não bloqueiam o frontend.
    """
    try:
        from services.system_error_logger import system_error_logger
        
        await system_error_logger.log_error(
            error_type="unhandled_exception",
            message=str(exc),
            component="api",
            details={
                "path": str(request.url.path),
                "method": request.method,
                "exception_type": type(exc).__name__,
            },
            severity="critical",
            request_path=str(request.url.path)
        )
    except (IOError, OSError) as log_error:
        logger.error(f"Erro ao registar excepção: {log_error}")
    
    logger.exception(f"Unhandled exception: {exc}")
    
    # Obter origin do request para CORS
    origin = request.headers.get("origin", "*")
    
    # Construir detalhe do erro com info de debug (sem expor stack trace)
    error_detail = "Erro interno do servidor"
    exception_type = type(exc).__name__
    
    # Incluir tipo de excepção para facilitar diagnóstico
    # (não incluímos str(exc) para evitar leak de info sensível)
    if exception_type not in ("HTTPException", "ValidationError", "RequestValidationError"):
        error_detail = f"Erro interno do servidor [{exception_type}]"
    
    # === DIAGNÓSTICO TEMPORÁRIO: Para TypeErrors, incluir traceback e linha exata ===
    if exception_type == "TypeError":
        import traceback as _tb
        full_tb = _tb.format_exc()
        logger.error(f"!!! TypeError DETALHADO:\n{full_tb}")
        # Extrair a linha relevante do traceback
        error_line = ""
        for line in full_tb.split('\n'):
            if '.py"' in line or '.py' in line:
                error_line = line.strip()
        # Incluir traceback parcial na resposta para diagnóstico
        error_detail = f"TypeError: {str(exc)} | Linha: {error_line} | TB: {full_tb[-800:]}"
    
    # Verificar se a origin é permitida
    allowed_origin = None
    if origin in CORS_ORIGINS:
        allowed_origin = origin
    elif CORS_ORIGIN_REGEX:
        import re
        for pattern in CORS_ORIGIN_REGEX:
            if re.match(pattern, origin):
                allowed_origin = origin
                break
    
    headers = {}
    if allowed_origin:
        headers = {
            "Access-Control-Allow-Origin": allowed_origin,
            "Access-Control-Allow-Credentials": "true",
        }
    
    return JSONResponse(
        status_code=500,
        content={"detail": error_detail},
        headers=headers
    )

# Rotas
app.include_router(auth_router, prefix="/api")
app.include_router(public_router, prefix="/api")
app.include_router(processes_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(deadlines_router, prefix="/api")
app.include_router(activities_router, prefix="/api")
app.include_router(stats_router, prefix="/api")
app.include_router(ai_router, prefix="/api")
app.include_router(documents_router, prefix="/api")
app.include_router(alerts_router, prefix="/api")
app.include_router(websocket_router, prefix="/api")
app.include_router(push_notifications_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
# emails_doc_router removido — send-documentation e document-recipients agora no router principal (antes de /{email_id})
app.include_router(emails_router, prefix="/api")
app.include_router(trello_router, prefix="/api")
app.include_router(ai_bulk_router, prefix="/api")
app.include_router(leads_router, prefix="/api")
app.include_router(match_router, prefix="/api")
app.include_router(system_config_router, prefix="/api")
app.include_router(properties_router, prefix="/api")
app.include_router(clients_router, prefix="/api")
app.include_router(gdpr_router, prefix="/api")
app.include_router(backup_router, prefix="/api")
app.include_router(scraper_router, prefix="/api")
app.include_router(minutas_router, prefix="/api")
app.include_router(ai_agent_router, prefix="/api")
app.include_router(templates_router, prefix="/api")
app.include_router(onedrive_router, prefix="/api")
app.include_router(search_router, prefix="/api")
app.include_router(storage_router, prefix="/api")
app.include_router(ai_import_logs_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(my_clients_router, prefix="/api")
app.include_router(admin_ai_router, prefix="/api")
app.include_router(admin_storage_router, prefix="/api")
app.include_router(diagnostics_router, prefix="/api")
app.include_router(rgpd_router, prefix="/api")
app.include_router(temp_links_router, prefix="/api")
app.include_router(admin_encryption_router, prefix="/api")
app.include_router(automation_router, prefix="/api")
app.include_router(form_config_router, prefix="/api")
app.include_router(restore_router, prefix="/api")
app.include_router(async_jobs_router, prefix="/api")
app.include_router(audit_router, prefix="/api")
app.include_router(annotations_router, prefix="/api")
app.include_router(finance_router, prefix="/api")
app.include_router(admin_migration_router, prefix="/api")
app.include_router(task_logs_router, prefix="/api")
app.include_router(portal_router, prefix="/api")
app.include_router(google_auth_router, prefix="/api")
app.include_router(shared_email_router, prefix="/api")
app.include_router(companies_router, prefix="/api")
app.include_router(portal_settings_router, prefix="/api")
app.include_router(ai_analysis_router, prefix="/api")
app.include_router(announcements_router, prefix="/api")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}


# Root path — Render health check uses HEAD / by default
@app.get("/")
@app.head("/")
async def root_health():
    """Health check para Render (usa HEAD / por padrão)."""
    return {"status": "ok"}


# ====================================================================
# BACKGROUND JOB MONITOR - Detecção automática de jobs stuck (P2)
# ====================================================================
async def send_stuck_job_email(stuck_jobs: list):
    """Enviar email quando jobs ficam stuck."""
    try:
        # Buscar configuração de email do sistema
        config = await db.system_config.find_one({"type": "email_notifications"})
        if not config or not config.get("enabled"):
            logger.info("Notificações por email desactivadas")
            return
        
        admin_emails = config.get("admin_emails", [])
        if not admin_emails:
            # Buscar emails de admins
            from services.role_query import deep_role_filter
            admins = await db.users.find(deep_role_filter("admin"), {"email": 1}).to_list(10)
            admin_emails = [a["email"] for a in admins if a.get("email")]
        
        if not admin_emails:
            logger.warning("Nenhum email de admin configurado para notificações")
            return
        
        # Construir mensagem
        job_details = "\n".join([
            f"- {job.get('name', job.get('id', 'N/A'))} ({job.get('job_type', 'desconhecido')})"
            for job in stuck_jobs[:10]
        ])
        
        subject = f"⚠️ {len(stuck_jobs)} Jobs Bloqueados Detectados - CRM"
        body = f"""
Olá,

O sistema detectou {len(stuck_jobs)} job(s) bloqueado(s) que foram automaticamente marcados como falhados.

Jobs afectados:
{job_details}

Por favor verifique a página de Background Jobs para mais detalhes.

---
Esta é uma notificação automática do CRM.
        """.strip()
        
        # Tentar enviar email usando o serviço existente
        from services.email_service import send_email
        for email in admin_emails[:3]:  # Máximo 3 destinatários
            try:
                await send_email(
                    to_email=email,
                    subject=subject,
                    body=body
                )
                logger.info(f"Email de jobs stuck enviado para {email}")
            except (IOError, OSError, ValueError, ConnectionError) as email_err:
                logger.warning(f"Falha ao enviar email para {email}: {email_err}")
                
    except (IOError, OSError, ValueError, ConnectionError, KeyError) as email_global_err:
        logger.error(f"Erro ao enviar emails de jobs stuck: {email_global_err}")


async def background_job_monitor():
    """
    Tarefa de background que verifica periodicamente se há jobs stuck.
    Executa a cada 30 minutos.
    
    Se encontrar jobs sem actualização há mais de 2 horas:
    1. Marca-os como "failed"
    2. Cria uma notificação de sistema
    3. Envia email para admins (se configurado)
    4. Regista no log
    """
    import asyncio
    from datetime import timedelta
    
    STUCK_THRESHOLD_HOURS = 2  # Jobs sem update há mais de 2h são considerados stuck
    CHECK_INTERVAL_SECONDS = 1800  # Verificar a cada 30 minutos
    
    logger.info("🔍 Background Job Monitor iniciado - verificação a cada 30 minutos")
    
    while True:
        try:
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)
            
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=STUCK_THRESHOLD_HOURS)
            cutoff_iso = cutoff_time.isoformat()
            
            # Buscar jobs stuck na base de dados
            stuck_jobs = await db.background_jobs.find({
                "status": {"$in": ["running", "pending"]},
                "updated_at": {"$lt": cutoff_iso}
            }).to_list(100)
            
            if stuck_jobs:
                logger.warning(f"⚠️ Encontrados {len(stuck_jobs)} jobs bloqueados há mais de {STUCK_THRESHOLD_HOURS}h")
                
                job_ids = [job.get("id") for job in stuck_jobs]
                
                # Marcar como failed
                await db.background_jobs.update_many(
                    {"id": {"$in": job_ids}},
                    {"$set": {
                        "status": "failed",
                        "error": f"Job marcado automaticamente como stuck após {STUCK_THRESHOLD_HOURS}h sem actividade",
                        "auto_cleaned_at": datetime.now(timezone.utc).isoformat()
                    }}
                )
                
                # Criar notificação de sistema
                for job in stuck_jobs:
                    try:
                        await db.system_notifications.insert_one({
                            "type": "job_stuck",
                            "severity": "warning",
                            "title": "Job bloqueado detectado",
                            "message": f"Job '{job.get('name', job.get('id'))}' foi automaticamente marcado como falhado após {STUCK_THRESHOLD_HOURS}h sem actividade.",
                            "job_id": job.get("id"),
                            "job_type": job.get("job_type"),
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "read": False
                        })
                    except (IOError, OSError, ValueError) as notif_err:
                        logger.error(f"Erro ao criar notificação para job stuck: {notif_err}")
                
                # Enviar email para admins
                await send_stuck_job_email(stuck_jobs)
                
                logger.info(f"✅ {len(stuck_jobs)} jobs stuck foram marcados como 'failed'")
            
        except (IOError, OSError, ValueError, KeyError) as monitor_err:
            logger.error(f"Erro no background job monitor: {monitor_err}")

# ====================================================================
# CORS MIDDLEWARE — MUST be last middleware added so it is OUTERMOST.
#
# In Starlette, middleware executes in REVERSE order of addition.
# @app.middleware decorators above are added in source order.
# This add_middleware() call is LAST → it runs FIRST on every request,
# ensuring OPTIONS preflight requests are handled before any custom
# middleware can interfere.
# ====================================================================
app.add_middleware(
    CORSMiddleware,
    allow_credentials=CORS_ALLOW_CREDENTIALS,
    allow_origins=CORS_ORIGINS,
    allow_origin_regex=CORS_ORIGIN_REGEX[0] if CORS_ORIGIN_REGEX else None,
    allow_methods=CORS_ALLOW_METHODS,
    allow_headers=CORS_ALLOW_HEADERS,
    max_age=CORS_MAX_AGE,
)

@app.on_event("startup")
async def startup():
    logger.info("🚀 Iniciando aplicação...")
    
    # Criar índices de BD para optimização de performance
    try:
        from services.db_indexes import create_indexes
        logger.info("📊 Criando índices de base de dados...")
        index_results = await create_indexes(db)
        logger.info(f"✅ Índices: {len(index_results.get('created', []))} criados, "
                   f"{len(index_results.get('skipped', []))} já existiam")
    except (IOError, OSError, ValueError, KeyError) as index_err:
        logger.warning(f"⚠️ Erro ao criar índices (não fatal): {index_err}")
    
    # Tenta conectar Redis sem falhar a app se não existir
    try:
        from services.task_queue import task_queue
        await task_queue.connect()
    except (IOError, OSError, ConnectionError, ImportError, TimeoutError):
        pass 
    
    # Inicializar Trello com configurações da base de dados
    try:
        from services.trello import init_trello_from_config
        await init_trello_from_config()
        logger.info("✅ Serviço Trello verificado")
    except (ImportError, ValueError, KeyError) as trello_err:
        logger.debug(f"Trello não configurado: {trello_err}")
    
    # ==========================================
    # TAREFAS DE BACKGROUND (leves — correm sempre)
    # ==========================================
    import asyncio

    # Iniciar scheduler para monitorização de jobs stuck
    monitor_task = asyncio.create_task(background_job_monitor())
    _background_tasks.add(monitor_task)
    monitor_task.add_done_callback(_background_tasks.discard)

    # --- Backup Scheduler: backup diário às 03:00 UTC ---
    try:
        from services.backup import start_backup_scheduler
        backup_task = asyncio.create_task(start_backup_scheduler())
        _background_tasks.add(backup_task)
        backup_task.add_done_callback(_background_tasks.discard)
        logger.info("💾 Backup scheduler iniciado - backup diário às 03:00 UTC")
    except (IOError, OSError, ValueError, ImportError) as backup_err:
        logger.warning(f"⚠️ Erro ao iniciar backup scheduler: {backup_err}")

    # --- CDC Audit Listener: Change Data Capture para compliance ---
    try:
        from services.audit_cdc import cdc_listener
        cdc_task = asyncio.create_task(cdc_listener.start())
        _background_tasks.add(cdc_task)
        cdc_task.add_done_callback(_background_tasks.discard)
        logger.info("🔍 CDC Audit Listener iniciado - monitorizando alterações para compliance")
    except (IOError, OSError, ValueError, ImportError) as cdc_err:
        logger.warning(f"⚠️ Erro ao iniciar CDC Audit Listener: {cdc_err}")

    # ==========================================
    # TAREFAS PESADAS — SÓ PRODUÇÃO (ENVIRONMENT=production)
    # ==========================================
    # O loop IMAP (Email Sync) e o Playwright (Gov Scraper) consomem
    # muita RAM. Em DEV (Render 512MB), estes serviços causam OOM.
    # Apenas arrancam quando ENVIRONMENT=production.
    if os.environ.get('ENVIRONMENT') == 'production':
        # --- Email Auto-Sync: IMAP polling a cada 15 minutos ---
        try:
            from services.scheduled_tasks import run_email_auto_sync
            email_sync_task = asyncio.create_task(run_email_auto_sync(interval_seconds=900))
            _background_tasks.add(email_sync_task)
            email_sync_task.add_done_callback(_background_tasks.discard)
            logger.info("📧 Auto-Sync Email iniciado - sincronização a cada 15 minutos")
        except (IOError, OSError, ValueError, ImportError) as email_sync_err:
            logger.warning(f"⚠️ Erro ao iniciar Auto-Sync Email: {email_sync_err}")
    else:
        logger.warning("🛑 MODO DEV: Playwright e Email Sync totalmente desativados para evitar OOM.")

@app.on_event("shutdown")
async def shutdown_db_client():
    # CORREÇÃO CRÍTICA: Não fechar a ligação DB se estivermos a correr testes!
    # O pytest reutiliza a ligação global, se a fecharmos aqui, o próximo teste falha.
    if os.getenv("TESTING") == "true":
        return
        
    try:
        client.close()
    except (IOError, OSError):
        pass