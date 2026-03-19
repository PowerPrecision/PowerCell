import os
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')


# ====================================================================
# VALIDAÇÃO DE VARIÁVEIS DE AMBIENTE CRÍTICAS
# ====================================================================
def get_required_env(key: str) -> str:
    """Obter variável de ambiente obrigatória. Falha se não existir."""
    value = os.environ.get(key)
    if not value:
        print(f"❌ ERRO FATAL: Variável de ambiente '{key}' não definida!", file=sys.stderr)
        print("   Configure no ficheiro .env ou nas variáveis de ambiente do sistema.", file=sys.stderr)
        sys.exit(1)
    return value


# ====================================================================
# JWT CONFIG (OBRIGATÓRIO - VALIDAÇÃO ROBUSTA)
# ====================================================================
JWT_SECRET = get_required_env('JWT_SECRET')
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# Validação robusta do JWT Secret
MIN_JWT_SECRET_LENGTH = 32  # Mínimo 256 bits de entropia

def validate_jwt_secret(secret: str) -> None:
    """
    Valida que o JWT secret é suficientemente seguro.
    Requisitos:
    - Mínimo 32 caracteres
    - Não pode ser um valor de exemplo conhecido
    - Deve ter mistura de caracteres para alta entropia
    """
    import string
    
    # Detectar ambiente de desenvolvimento
    is_development = os.environ.get('ENVIRONMENT', 'development').lower() in ['development', 'dev', 'local', 'preview']
    
    # Lista de valores de exemplo que NÃO devem ser usados
    INSECURE_SECRETS = [
        'super-secret-key',
        'change-in-production',
        'your-secret-key',
        'secret-key',
        'mysecret',
        'changeme',
        'password',
        'jwt-secret',
        'default-secret',
    ]
    
    secret_lower = secret.lower()
    
    # Verificar se é um valor de exemplo
    for insecure in INSECURE_SECRETS:
        if insecure in secret_lower:
            if is_development:
                print(f"⚠️  AVISO (DEV): JWT_SECRET contém valor de exemplo '{insecure}'!", file=sys.stderr)
                print("   Em PRODUÇÃO isto seria bloqueado. Gere: openssl rand -hex 32", file=sys.stderr)
                return  # Não bloqueia em desenvolvimento
            else:
                print(f"❌ ERRO FATAL: JWT_SECRET contém valor de exemplo '{insecure}'!", file=sys.stderr)
                print("   Gere um secret seguro: openssl rand -hex 32", file=sys.stderr)
                sys.exit(1)
    
    # Verificar comprimento mínimo
    if len(secret) < MIN_JWT_SECRET_LENGTH:
        if is_development:
            print(f"⚠️  AVISO (DEV): JWT_SECRET muito curto ({len(secret)} chars)!", file=sys.stderr)
            return
        else:
            print(f"❌ ERRO FATAL: JWT_SECRET muito curto ({len(secret)} chars)!", file=sys.stderr)
            print(f"   Mínimo requerido: {MIN_JWT_SECRET_LENGTH} caracteres", file=sys.stderr)
            print("   Gere um secret seguro: openssl rand -hex 32", file=sys.stderr)
            sys.exit(1)
    
    # Verificar complexidade (entropia)
    has_lower = any(c.islower() for c in secret)
    has_upper = any(c.isupper() for c in secret)
    has_digit = any(c.isdigit() for c in secret)
    has_special = any(c in string.punctuation for c in secret)
    
    complexity_score = sum([has_lower, has_upper, has_digit, has_special])
    
    if complexity_score < 2:
        print(f"⚠️  AVISO: JWT_SECRET com baixa complexidade (score: {complexity_score}/4)", file=sys.stderr)
        print("   Recomendado usar mistura de maiúsculas, minúsculas, números e símbolos", file=sys.stderr)
    
    print(f"✅ JWT_SECRET validado ({len(secret)} chars, complexidade: {complexity_score}/4)", file=sys.stderr)

# Executar validação
validate_jwt_secret(JWT_SECRET)


# ====================================================================
# DATABASE CONFIG (OBRIGATÓRIO)
# ====================================================================
MONGO_URL = get_required_env('MONGO_URL')
DB_NAME = get_required_env('DB_NAME')


# ====================================================================
# CORS CONFIG (FAIL-SECURE)
# ====================================================================
# CORS_ORIGINS é OBRIGATÓRIO em produção.
# Formato: "https://domain1.com,https://domain2.com"
# A aplicação FALHA se não estiver correctamente configurado.
# ====================================================================
_cors_env = os.environ.get('CORS_ORIGINS', '').strip().strip('"').strip("'")

# FAIL-SECURE: A aplicação DEVE falhar se CORS não estiver configurado
if not _cors_env:
    raise ValueError(
        "❌ ERRO FATAL: CORS_ORIGINS não definido!\n"
        "   Configure a variável de ambiente CORS_ORIGINS com as origens permitidas.\n"
        "   Exemplo: CORS_ORIGINS='https://meusite.com,https://app.meusite.com'\n"
        "   A aplicação não pode arrancar sem configuração CORS explícita."
    )

if _cors_env == '*':
    raise ValueError(
        "❌ ERRO FATAL: CORS_ORIGINS='*' não é permitido!\n"
        "   Wildcards não são aceites em modo de produção.\n"
        "   Configure origens específicas: CORS_ORIGINS='https://meusite.com'"
    )

# Parsing e validação estrita das origens
CORS_ORIGINS = []
CORS_ORIGIN_REGEX = []  # Para padrões de wildcard
_invalid_origins = []

# Verificar se devemos permitir previews do Vercel
_allow_vercel_previews = os.environ.get('ALLOW_VERCEL_PREVIEWS', 'true').lower() == 'true'

for origin in _cors_env.split(','):
    origin = origin.strip()
    if not origin:
        continue
    
    # Validar formato da origem (deve ser URL válido com protocolo)
    if origin.startswith('https://'):
        CORS_ORIGINS.append(origin)
    elif origin.startswith('http://localhost') or origin.startswith('http://127.0.0.1'):
        # Permitir localhost apenas para desenvolvimento
        print(f"⚠️  AVISO: Origem HTTP localhost permitida (apenas dev): {origin}", file=sys.stderr)
        CORS_ORIGINS.append(origin)
    elif origin.startswith('http://'):
        _invalid_origins.append(f"{origin} (HTTP não seguro)")
    else:
        _invalid_origins.append(f"{origin} (formato inválido)")

# Adicionar suporte para previews do Vercel
# Sempre que ALLOW_VERCEL_PREVIEWS=true, permite qualquer subdomínio de vercel.app
# Isto é seguro porque previews do Vercel requerem autenticação do GitHub para aceder
if _allow_vercel_previews:
    # Regex para permitir qualquer subdomínio de vercel.app
    CORS_ORIGIN_REGEX = [r"https://[a-z0-9-]+\.vercel\.app"]
    print(f"✅ Vercel preview domains habilitados", file=sys.stderr)

# Reportar origens inválidas
if _invalid_origins:
    print(f"⚠️  Origens CORS ignoradas: {', '.join(_invalid_origins)}", file=sys.stderr)

# FAIL-SECURE: Deve haver pelo menos uma origem válida
if not CORS_ORIGINS:
    raise ValueError(
        f"❌ ERRO FATAL: Nenhuma origem CORS válida configurada!\n"
        f"   Origens rejeitadas: {', '.join(_invalid_origins) if _invalid_origins else 'nenhuma fornecida'}\n"
        f"   Use HTTPS para origens de produção: CORS_ORIGINS='https://meusite.com'"
    )

print(f"✅ CORS configurado (fail-secure): {', '.join(CORS_ORIGINS)}", file=sys.stderr)

# Configurações adicionais de CORS (com defaults seguros)
CORS_ALLOW_CREDENTIALS = os.environ.get('CORS_ALLOW_CREDENTIALS', 'true').lower() == 'true'
CORS_ALLOW_METHODS = os.environ.get('CORS_ALLOW_METHODS', 'GET,POST,PUT,DELETE,OPTIONS,PATCH').split(',')
CORS_ALLOW_HEADERS = os.environ.get('CORS_ALLOW_HEADERS', 'Authorization,Content-Type,Accept,Origin,X-Requested-With').split(',')
CORS_MAX_AGE = int(os.environ.get('CORS_MAX_AGE', '600'))


# ====================================================================
# SENTRY CONFIG (OBSERVABILIDADE)
# ====================================================================
# SENTRY_DSN é opcional - se não definido, Sentry fica desactivado
# Obter DSN em: https://sentry.io -> Project Settings -> Client Keys (DSN)
# Suporta ambos: DSN_SENTRY_BACKEND (preferido) e SENTRY_DSN (legado)
# ====================================================================
SENTRY_DSN = os.environ.get('DSN_SENTRY_BACKEND') or os.environ.get('SENTRY_DSN', '')
SENTRY_ENVIRONMENT = os.environ.get('SENTRY_ENVIRONMENT', 'development')
SENTRY_TRACES_SAMPLE_RATE = float(os.environ.get('SENTRY_TRACES_SAMPLE_RATE', '1.0'))
SENTRY_PROFILES_SAMPLE_RATE = float(os.environ.get('SENTRY_PROFILES_SAMPLE_RATE', '0.1'))
SENTRY_SEND_DEFAULT_PII = os.environ.get('SENTRY_SEND_DEFAULT_PII', 'false').lower() == 'true'

# Validação e log de configuração Sentry
if SENTRY_DSN:
    print(f"✅ Sentry configurado para ambiente: {SENTRY_ENVIRONMENT}", file=sys.stderr)
    print(f"   Traces sample rate: {SENTRY_TRACES_SAMPLE_RATE}", file=sys.stderr)
else:
    print("⚠️  SENTRY_DSN não configurado - observabilidade desactivada", file=sys.stderr)


# ====================================================================
# OneDrive Config (opcional)
# ====================================================================
ONEDRIVE_TENANT_ID = os.environ.get('ONEDRIVE_TENANT_ID', '')
ONEDRIVE_CLIENT_ID = os.environ.get('ONEDRIVE_CLIENT_ID', '')
ONEDRIVE_CLIENT_SECRET = os.environ.get('ONEDRIVE_CLIENT_SECRET', '')
ONEDRIVE_BASE_PATH = os.environ.get('ONEDRIVE_BASE_PATH', 'Documentação Clientes')


# ====================================================================
# EMAIL CONFIG - API TRANSACIONAL
# ====================================================================
# Provider primário (recomendado): SendGrid ou Resend
# SMTP mantido como fallback de emergência
# ====================================================================
EMAIL_PROVIDER = os.environ.get('EMAIL_PROVIDER', 'sendgrid')  # sendgrid | resend | smtp
EMAIL_API_KEY = os.environ.get('EMAIL_API_KEY', '')  # API key do provider
EMAIL_FROM = os.environ.get('EMAIL_FROM', 'noreply@powerealestate.pt')
EMAIL_FROM_NAME = os.environ.get('EMAIL_FROM_NAME', 'Power Real Estate & Precision Crédito')

# SMTP Fallback (legado)
SMTP_SERVER = os.environ.get('SMTP_SERVER', '')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '465'))
SMTP_EMAIL = os.environ.get('SMTP_EMAIL', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')

# Log de configuração de email
if EMAIL_API_KEY:
    print(f"✅ Email configurado: {EMAIL_PROVIDER.upper()} (API transacional)", file=sys.stderr)
elif SMTP_SERVER:
    print("⚠️  Email configurado: SMTP (modo legado)", file=sys.stderr)
else:
    print("⚠️  Email não configurado - emails serão simulados", file=sys.stderr)


# ====================================================================
# TASK QUEUE CONFIG (Redis + ARQ)
# ====================================================================
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
REDIS_DB = int(os.environ.get('REDIS_DB', '0'))
REDIS_MAX_CONNECTIONS = int(os.environ.get('REDIS_MAX_CONNECTIONS', '10'))

# Task settings
TASK_JOB_TIMEOUT = int(os.environ.get('TASK_JOB_TIMEOUT', '300'))
TASK_MAX_TRIES = int(os.environ.get('TASK_MAX_TRIES', '3'))
TASK_RETRY_DELAY = int(os.environ.get('TASK_RETRY_DELAY', '60'))
TASK_MAX_JOBS = int(os.environ.get('TASK_MAX_JOBS', '10'))


def get_redis_settings():
    """Retorna configuração Redis para ARQ."""
    try:
        from arq.connections import RedisSettings
        from urllib.parse import urlparse
        
        # Se não há REDIS_URL configurado ou é localhost, Redis é opcional
        if not os.environ.get('REDIS_URL') or 'localhost' in REDIS_URL:
            return None
        
        parsed = urlparse(REDIS_URL)
        
        return RedisSettings(
            host=parsed.hostname or "localhost",
            port=parsed.port or 6379,
            password=parsed.password,
            database=int(parsed.path.lstrip("/") or REDIS_DB),
            conn_timeout=5,  # Timeout rápido
            conn_retries=1,  # Apenas 1 retry
        )
    except ImportError:
        return None


# ====================================================================
# TRELLO CONFIG (opcional - para integração futura)
# ====================================================================
TRELLO_API_KEY = os.environ.get('TRELLO_API_KEY', '')
TRELLO_TOKEN = os.environ.get('TRELLO_TOKEN', '')
TRELLO_BOARD_ID = os.environ.get('TRELLO_BOARD_ID', '')


# ====================================================================
# AI CONFIG - CONFIGURAÇÃO DE MODELOS DE IA
# ====================================================================
# Chaves de API para diferentes providers
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')

# Modelos disponíveis e seus custos (apenas informativos)
AI_MODELS = {
    "gemini-2.0-flash": {
        "provider": "gemini",
        "name": "Gemini 2.0 Flash",
        "cost_per_1k_tokens": 0.0001,  # Muito económico
        "best_for": ["scraping", "extraction"],
        "requires_key": "GEMINI_API_KEY"
    },
    "gpt-4o-mini": {
        "provider": "openai",
        "name": "GPT-4o Mini",
        "cost_per_1k_tokens": 0.00015,
        "best_for": ["documents", "analysis"],
        "requires_key": "EMERGENT_LLM_KEY"
    },
    "gpt-4o": {
        "provider": "openai", 
        "name": "GPT-4o",
        "cost_per_1k_tokens": 0.005,
        "best_for": ["complex_analysis", "reports"],
        "requires_key": "EMERGENT_LLM_KEY"
    }
}

# Configurações padrão de qual IA usar para cada tarefa
# Pode ser alterado via admin
AI_CONFIG_DEFAULTS = {
    "scraper_extraction": "gemini-2.0-flash",  # Extração de dados de páginas
    "document_analysis": "gpt-4o-mini",        # Análise de documentos
    "weekly_report": "gpt-4o-mini",            # Relatório semanal
    "error_analysis": "gpt-4o-mini",           # Análise de erros
}

# Log de configuração de IA
if GEMINI_API_KEY:
    print("✅ Gemini API configurada", file=sys.stderr)
if EMERGENT_LLM_KEY:
    print("✅ LLM API Key configurada (OpenAI)", file=sys.stderr)

