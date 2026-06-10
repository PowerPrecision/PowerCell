import os
import logging
from datetime import datetime, timezone

# v2025-01-webmail-sync

# NOTA: libmagic1 é instalado no Dockerfile (camada de build).
# NÃO instalar apt-get packages no arranque — causa OOM no Render (512MB).

# ====================================================================
# SINGLETON LOCK para tarefas de background
# ====================================================================
# Com múltiplos Uvicorn workers, cada worker executa o startup event.
# Sem lock, tarefas pesadas (email sync, CDC, backup) correm N vezes,
# causando OOM no Render (2GB RAM com 4 workers = 16 tarefas de bg).
# Este lock garante que SÓ UM worker inicia as tarefas de background.
# ====================================================================
import fcntl

_BG_LOCK_FD = None

def _try_acquire_bg_lock() -> bool:
    """Tenta adquirir o lock singleton para tarefas de background.
    
    Usa fcntl.flock (exclusivo, não-bloqueante) em /tmp/powercell_bg.lock.
    Só o primeiro worker que chamar esta função obtém o lock.
    Os restantes workers não iniciam tarefas de background.
    
    Returns:
        True se o lock foi adquirido (worker primário), False caso contrário.
    """
    global _BG_LOCK_FD
    try:
        _BG_LOCK_FD = open('/tmp/powercell_bg.lock', 'w')
        fcntl.flock(_BG_LOCK_FD, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _BG_LOCK_FD.write(str(os.getpid()))
        _BG_LOCK_FD.flush()
        return True
    except (IOError, OSError):
        if _BG_LOCK_FD:
            try:
                _BG_LOCK_FD.close()
            except (IOError, OSError):
                pass
            _BG_LOCK_FD = None
        return False

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.integrations.pymongo import PyMongoIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from fastapi import FastAPI, APIRouter
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
from routes.ai_bulk import router as ai_bulk_router
from routes.leads import router as leads_router
from routes.match import router as match_router
from routes.system_config import router as system_config_router
from routes.properties import router as properties_router
from routes.clients import router as clients_router
from routes.visits import router as visits_router
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
from routes.user_company_roles import router as user_company_roles_router
from routes.portal_settings import router as portal_settings_router
from routes.ai_analysis import router as ai_analysis_router
from routes.announcements import router as announcements_router
from routes.gov_auth import router as gov_auth_router
from routes.user_branches import router as user_branches_router
try:
    from routes.admin_process_migration import router as admin_process_migration_router
    _admin_process_migration_import_error = None
except Exception as e:
    import logging as _mig_log
    _mig_log.getLogger(__name__).error(f"⚠️ Falha ao importar admin_process_migration: {type(e).__name__}: {e}")
    admin_process_migration_router = None
    _admin_process_migration_import_error = f"{type(e).__name__}: {e}"

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

# ── Configuração de Logging para Render ──
# O utils/logger.py configura o root logger com sys.stdout e formato limpo.
# Deve ser importado ANTES de criar o logger do server.py para que o
# handler de stdout seja registado primeiro.
from utils.logger import get_logger
logger = get_logger(__name__)

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
        except jwt.PyJWTError:
            # Outros erros JWT (InvalidKeyError, etc.) — usar IP como fallback
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
        except Exception as log_error:
            logger.warning(f"Erro ao registar log: {type(log_error).__name__}: {log_error}")
    
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
    # Obter origin do request para CORS (igual ao http_exception_handler)
    origin = request.headers.get("origin", "")

    # Verificar se a origin é permitida
    allowed_origin = None
    if origin in CORS_ORIGINS:
        allowed_origin = origin
    elif CORS_ORIGIN_REGEX:
        import re as _re_422
        for pattern in CORS_ORIGIN_REGEX:
            if _re_422.match(pattern, origin):
                allowed_origin = origin
                break
    # Fallback: permitir previews do Vercel mesmo sem regex
    if not allowed_origin and origin and origin.startswith("https://") and origin.endswith(".vercel.app"):
        allowed_origin = origin

    cors_headers = {}
    if allowed_origin:
        cors_headers = {
            "Access-Control-Allow-Origin": allowed_origin,
            "Access-Control-Allow-Credentials": "true",
        }

    # Retornar erro formatado ao cliente
    return JSONResponse(
        status_code=422,
        content={"detail": safe_errors},
        headers=cors_headers
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """
    Handler para excepções não tratadas.
    Regista o erro, imprime traceback completo na consola e retorna 500.
    Inclui headers CORS para garantir que erros não bloqueiam o frontend.
    """
    exception_type = type(exc).__name__
    import traceback as _tb
    full_tb = _tb.format_exc()

    # === SEMPRE imprimir traceback completo na consola ===
    logger.error(
        f"!!! EXCEPÇÃO NÃO TRATADA: {exception_type}: {exc}\n"
        f"    Path: {request.method} {request.url.path}\n"
        f"    Traceback completo:\n{full_tb}"
    )

    # Registar no sistema de logs do MongoDB
    try:
        from services.system_error_logger import system_error_logger

        await system_error_logger.log_error(
            error_type="unhandled_exception",
            message=str(exc),
            component="api",
            details={
                "path": str(request.url.path),
                "method": request.method,
                "exception_type": exception_type,
                "traceback": full_tb,
            },
            severity="critical",
            request_path=str(request.url.path)
        )
    except Exception as log_error:
        logger.error(f"Erro ao registar excepção no system_error_logger: {type(log_error).__name__}: {log_error}")

    # Obter origin do request para CORS
    origin = request.headers.get("origin", "*")

    # Construir detalhe do erro
    error_detail = "Erro interno do servidor"
    if exception_type not in ("HTTPException", "ValidationError", "RequestValidationError"):
        error_detail = f"Erro interno do servidor [{exception_type}]"

    # Em modo de desenvolvimento, incluir traceback na resposta para debug
    is_dev = os.getenv("ENVIRONMENT", "dev") == "dev"
    if is_dev:
        # Extrair a linha relevante do traceback
        error_line = ""
        for line in full_tb.split('\n'):
            if '.py"' in line or '.py' in line:
                error_line = line.strip()
        error_detail = f"{exception_type}: {str(exc)} | Linha: {error_line} | TB: {full_tb[-800:]}"

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
app.include_router(ai_bulk_router, prefix="/api")
app.include_router(leads_router, prefix="/api")
app.include_router(match_router, prefix="/api")
app.include_router(system_config_router, prefix="/api")
app.include_router(properties_router, prefix="/api")
app.include_router(visits_router, prefix="/api")
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
app.include_router(user_company_roles_router, prefix="/api")
app.include_router(portal_settings_router, prefix="/api")
app.include_router(ai_analysis_router, prefix="/api")
app.include_router(announcements_router, prefix="/api")
app.include_router(gov_auth_router, prefix="/api")
app.include_router(user_branches_router, prefix="/api")
if admin_process_migration_router:
    app.include_router(admin_process_migration_router, prefix="/api")
else:
    # Rota de diagnóstico — se o import falhou, esta rota explica o porquê
    _diag_router = APIRouter(prefix="/admin/process-migration", tags=["Admin Process Migration (Diagnostic)"])

    @_diag_router.get("/status")
    async def migration_diagnostic():
        return {
            "error": "O módulo admin_process_migration falhou ao importar",
            "import_error": _admin_process_migration_import_error,
            "hint": "Verifique os logs do servidor para detalhes do erro de importação"
        }

    app.include_router(_diag_router, prefix="/api")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}


@app.get("/api/cors-debug")
async def cors_debug_endpoint(request: Request):
    """
    Endpoint de diagnóstico CORS.
    
    Retorna a configuração CORS atual e verifica se uma determinada
    origin seria permitida. Use o query parameter ?origin=URL para
    testar uma origin específica.
    
    Exemplo: /api/cors-debug?origin=https://power-cell.vercel.app
    """
    import re as _re_debug
    
    test_origin = request.query_params.get("origin", "")
    
    # Verificar se a origin seria permitida
    origin_status = {
        "in_explicit_list": test_origin in CORS_ORIGINS if test_origin else False,
        "matches_regex": False,
        "is_vercel_preview": False,
        "would_be_allowed": False,
    }
    
    if test_origin and CORS_ORIGIN_REGEX:
        for pattern in CORS_ORIGIN_REGEX:
            if _re_debug.match(pattern, test_origin):
                origin_status["matches_regex"] = True
                break
    
    if test_origin:
        origin_status["is_vercel_preview"] = (
            test_origin.startswith("https://") and
            test_origin.endswith(".vercel.app") and
            len(test_origin) > len("https://.vercel.app")
        )
    
    origin_status["would_be_allowed"] = (
        origin_status["in_explicit_list"] or
        origin_status["matches_regex"] or
        origin_status["is_vercel_preview"]  # Fallback middleware
    )
    
    return {
        "cors_config": {
            "explicit_origins": CORS_ORIGINS,
            "origin_regex": CORS_ORIGIN_REGEX[0] if CORS_ORIGIN_REGEX else None,
            "allow_credentials": CORS_ALLOW_CREDENTIALS,
            "allow_methods": CORS_ALLOW_METHODS,
            "allow_headers": CORS_ALLOW_HEADERS,
            "max_age": CORS_MAX_AGE,
            "vercel_fallback_middleware": True,
        },
        "test_origin": test_origin or "(nenhuma fornecida)",
        "origin_status": origin_status,
    }


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
# LOGGING / RASTREABILIDADE MIDDLEWARE
# Regista todos os pedidos HTTP com método, path, status, duração e user.
# Adicionado ANTES do CORS para que execute DEPOIS na cadeia (reverse order).
# ====================================================================
from middleware.logging_middleware import LoggingMiddleware
app.add_middleware(LoggingMiddleware)

# ====================================================================
# CORS DEBUG MIDDLEWARE — Regista origens rejeitadas para diagnóstico.
# Adicionado ANTES do CORSMiddleware (executa DEPOIS na cadeia).
# Isto permite-nos ver no log qual origin foi rejeitada e porquê.
# ====================================================================
import re as _re

@app.middleware("http")
async def cors_debug_middleware(request, call_next):
    """
    Middleware de debug CORS — regista origins que falham validação.
    
    Ajuda a diagnosticar erros CORS em produção, especialmente com
    Vercel preview URLs que mudam frequentemente.
    
    Só regista quando o pedido é OPTIONS (preflight) e a origin
    não está nas origens permitidas.
    """
    response = await call_next(request)
    
    # Só diagnosticar pedidos OPTIONS (CORS preflight)
    if request.method == "OPTIONS":
        origin = request.headers.get("origin", "")
        if origin:
            # Verificar se a origin foi permitida
            allow_origin = response.headers.get("access-control-allow-origin", "")
            if not allow_origin:
                logger.warning(
                    f"🚫 CORS REJEITADO: Origin '{origin}' não permitida | "
                    f"Origins explícitas: {CORS_ORIGINS} | "
                    f"Regex: {CORS_ORIGIN_REGEX[0] if CORS_ORIGIN_REGEX else 'nenhum'}"
                )
            else:
                logger.debug(f"✅ CORS OK: Origin '{origin}' permitida")
    
    return response

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

# ====================================================================
# VERCEL CORS FALLBACK MIDDLEWARE — Camada de segurança extra.
#
# Adicionado DEPOIS do CORSMiddleware → torna-se o OUTERMOST middleware.
# Isto garante que pedidos preflight OPTIONS de URLs do Vercel são
# sempre tratados, mesmo que o CORSMiddleware não faça match da regex.
#
# PROBLEMA: Alguns deployments no Render podem ter ALLOW_VERCEL_PREVIEWS
# desativado ou a regex pode falhar por motivos de parsing. Este middleware
# garante que previews do Vercel funcionam SEMPRE.
#
# Segurança: Apenas aceita origins HTTPS que terminem em .vercel.app
# ====================================================================
from starlette.responses import Response as StarletteResponse

@app.middleware("http")
async def vercel_cors_fallback_middleware(request, call_next):
    """
    Fallback CORS middleware para URLs de preview do Vercel.
    
    Garante que pedidos preflight OPTIONS de *.vercel.app são sempre
    tratados com HTTP 200 e headers CORS correctos, mesmo que o
    CORSMiddleware principal não faça match da origin.
    
    Isto resolve o erro: "Response to preflight request doesn't pass
    access control check: It does not have HTTP ok status."
    
    Segurança:
    - Apenas origens HTTPS (nunca HTTP)
    - Apenas domínios .vercel.app (verificado por sufixo)
    - Respeita a configuração de credentials
    """
    origin = request.headers.get("origin", "")
    
    # Detectar se é uma URL de preview do Vercel
    is_vercel_preview = (
        origin and
        origin.startswith("https://") and
        origin.endswith(".vercel.app") and
        len(origin) > len("https://.vercel.app")  # Tem subdomínio
    )
    
    # Para pedidos preflight OPTIONS de Vercel: responder directamente
    if request.method == "OPTIONS" and is_vercel_preview:
        # Verificar se o CORSMiddleware já adicionou headers
        # (se passou pelo CORSMiddleware com sucesso, já terá resposta)
        # Como este middleware é OUTERMOST, chamar call_next passa ao CORSMiddleware
        response = await call_next(request)
        
        # Se o CORSMiddleware não adicionou o header, o preflight falhou
        if not response.headers.get("access-control-allow-origin"):
            logger.info(
                f"🔄 Vercel CORS fallback: Origin '{origin}' não foi tratada pelo CORSMiddleware. "
                f"A adicionar headers CORS manualmente."
            )
            return StarletteResponse(
                status_code=200,
                headers={
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": ",".join(CORS_ALLOW_METHODS),
                    "Access-Control-Allow-Headers": ",".join(CORS_ALLOW_HEADERS),
                    "Access-Control-Allow-Credentials": "true" if CORS_ALLOW_CREDENTIALS else "false",
                    "Access-Control-Max-Age": str(CORS_MAX_AGE),
                }
            )
        return response
    
    # Para pedidos normais (GET, POST, etc.) de Vercel
    response = await call_next(request)
    
    # Se o CORSMiddleware não adicionou headers CORS, adicionar manualmente
    if is_vercel_preview and not response.headers.get("access-control-allow-origin"):
        logger.debug(f"🔄 Vercel CORS fallback: Adicionando headers CORS para origin '{origin}'")
        response.headers["Access-Control-Allow-Origin"] = origin
        if CORS_ALLOW_CREDENTIALS:
            response.headers["Access-Control-Allow-Credentials"] = "true"
    
    return response

# Log da configuração CORS no arranque
logger.info(f"📋 CORS: {len(CORS_ORIGINS)} origins explícitas = {CORS_ORIGINS}")
logger.info(f"📋 CORS: regex = {CORS_ORIGIN_REGEX[0] if CORS_ORIGIN_REGEX else 'nenhum'}")
logger.info(f"📋 CORS: credentials = {CORS_ALLOW_CREDENTIALS}")
logger.info(f"📋 CORS: max_age = {CORS_MAX_AGE}")
logger.info("📋 CORS: Vercel fallback middleware ATIVO (qualquer *.vercel.app HTTPS é permitido)")

@app.on_event("startup")
async def startup():
    import os as _os_diag
    logger.info("🚀 Iniciando aplicação...")
    logger.info(f"📋 ENVIRONMENT = '{_os_diag.environ.get('ENVIRONMENT', '(não definido)')}' | "
                f"APP_ENV = '{_os_diag.environ.get('APP_ENV', '(não definido)')}' | "
                f"UVICORN_WORKERS = '{_os_diag.environ.get('UVICORN_WORKERS', '(não definido)')}'")
    
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
    
    # Trello integration removed (deprecated)
    
    # Inicializar S3 a partir da config da base de dados
    try:
        from services.s3_storage import sync_s3_from_db_config
        await sync_s3_from_db_config()
        logger.info("✅ S3 Service sincronizado com config da BD")
    except (ImportError, ValueError, KeyError) as s3_err:
        logger.debug(f"S3 sync não disponível: {s3_err}")
    
    # ==========================================
    # TAREFAS DE BACKGROUND
    # =========================================
    # 🛑 EM DEV (ENVIRONMENT != production): Só corre o job monitor (leve).
    # Backup, CDC e Email Sync são BLOQUEADOS para poupar RAM no Render.
    # 🔑 SINGLETON: Com múltiplos workers, SÓ O PRIMEIRO worker inicia
    # as tarefas de background (via file lock). Isto evita que N workers
    # lancem N×4 tarefas de background em simultâneo (causa OOM).
    import asyncio
    import os as _os
    _is_production = _os.environ.get('ENVIRONMENT') == 'production'
    _is_primary_worker = _try_acquire_bg_lock()

    if _is_production and _is_primary_worker:
        logger.info("🟢 PRODUÇÃO + Worker primário: Todas as tarefas de background ativadas.")
    elif _is_production and not _is_primary_worker:
        logger.info("🟢 PRODUÇÃO + Worker secundário: Apenas job monitor (leve).")
    else:
        logger.warning("🟡 MODO DEV: Tarefas pesadas de background DESATIVADAS para poupar RAM.")

    # Iniciar scheduler para monitorização de jobs stuck (leve — corre sempre)
    monitor_task = asyncio.create_task(background_job_monitor())
    _background_tasks.add(monitor_task)
    monitor_task.add_done_callback(_background_tasks.discard)

    # --- Tarefas pesadas: SÓ no worker primário em PRODUÇÃO ---
    if _is_production and _is_primary_worker:
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

        # Iniciar Auto-Sync de Emails
        try:
            from services.scheduled_tasks import run_email_auto_sync
            email_sync_task = asyncio.create_task(run_email_auto_sync(interval_seconds=180))
            _background_tasks.add(email_sync_task)
            email_sync_task.add_done_callback(_background_tasks.discard)
            logger.info("✅ Auto-sync de email iniciado (Apenas Produção).")
        except Exception as email_sync_err:
            logger.warning(f"⚠️ Erro ao iniciar Auto-Sync Email: {email_sync_err}")
    elif _is_production and not _is_primary_worker:
        logger.info("💾 Backup scheduler: DESATIVADO (worker secundário)")
        logger.info("🔍 CDC Audit Listener: DESATIVADO (worker secundário)")
        logger.info("📧 Auto-sync de email: DESATIVADO (worker secundário)")
    else:
        logger.info("💾 Backup scheduler: DESATIVADO em DEV")
        logger.info("🔍 CDC Audit Listener: DESATIVADO em DEV")
        logger.warning("🛑 MODO DEV: Tarefas de background (Email/Scraper) DESATIVADAS para poupar RAM.")

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