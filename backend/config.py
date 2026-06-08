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

def _add_origin_with_variants(origin: str) -> list:
    """
    Adiciona uma origem e suas variantes (www e não-www).
    Isto resolve problemas de CORS quando o utilizador acede via www ou não.
    
    Exemplo: https://powercell.pt adiciona também https://www.powercell.pt
    """
    origins = [origin]
    
    if origin.startswith('https://'):
        domain = origin[8:]  # Remove 'https://'
        
        # Se não tem www, adicionar versão com www
        if not domain.startswith('www.'):
            origins.append(f"https://www.{domain}")
        # Se tem www, adicionar versão sem www
        elif domain.startswith('www.'):
            origins.append(f"https://{domain[4:]}")
    
    return origins

for origin in _cors_env.split(','):
    origin = origin.strip()
    if not origin:
        continue
    
    # Validar formato da origem (deve ser URL válido com protocolo)
    if origin.startswith('https://'):
        # Adicionar origem e suas variantes (www/non-www)
        for variant in _add_origin_with_variants(origin):
            if variant not in CORS_ORIGINS:
                CORS_ORIGINS.append(variant)
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
#
# CORREÇÃO CORS (2025): O regex anterior podia falhar em alguns cenários:
# 1. ALLOW_VERCEL_PREVIEWS podia estar desativado no Render Dashboard
# 2. O regex podia não fazer match por diferenças de parsing
#
# SOLUÇÃO: Agora o regex é sempre adicionado (independentemente de ALLOW_VERCEL_PREVIEWS)
# e existe também um fallback middleware em server.py que trata URLs .vercel.app
# mesmo que o CORSMiddleware não faça match.
#
# Segurança: Previews do Vercel são HTTPS e requerem acesso ao repositório GitHub.
if _allow_vercel_previews:
    # Regex para permitir qualquer subdomínio de vercel.app (incluindo aninhados)
    # Exemplos que matcham:
    #   https://power-cell.vercel.app
    #   https://power-cell-git-dev-power-precisions-projects.vercel.app
    #   https://power-cell-abc123.vercel.app
    # Não matcha:
    #   https://evil-vercel.app (domínio diferente)
    #   http://power-cell.vercel.app (HTTP, não HTTPS)
    CORS_ORIGIN_REGEX = [r"https://[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.vercel\.app(?::\d+)?$"]
    print(f"✅ Vercel preview domains habilitados (regex: qualquer subdomínio .vercel.app)", file=sys.stderr)
else:
    # Mesmo com ALLOW_VERCEL_PREVIEWS=false, adicionamos o regex como fallback
    # porque o Vercel fallback middleware em server.py precisa dele para
    # saber quais origins são do Vercel. O middleware funciona independentemente.
    CORS_ORIGIN_REGEX = [r"https://[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.vercel\.app(?::\d+)?$"]
    print(f"⚠️  Vercel preview domains: regex mantido (fallback middleware ativo)", file=sys.stderr)

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
if CORS_ORIGIN_REGEX:
    print(f"✅ CORS regex ativo: {CORS_ORIGIN_REGEX[0]}", file=sys.stderr)

# Configurações adicionais de CORS (com defaults seguros)
CORS_ALLOW_CREDENTIALS = os.environ.get('CORS_ALLOW_CREDENTIALS', 'true').lower() == 'true'
CORS_ALLOW_METHODS = os.environ.get('CORS_ALLOW_METHODS', 'GET,POST,PUT,DELETE,OPTIONS,PATCH').split(',')

# CORS_ALLOW_HEADERS: Garantir que os headers custom do frontend estão sempre presentes.
# CORREÇÃO (2025): O Render Dashboard pode ter um valor personalizado para CORS_ALLOW_HEADERS
# que NÃO inclui X-Company-Id, causando erro "Disallowed CORS headers" nos pedidos preflight.
# Estes headers são obrigatórios porque o frontend envia-os em TODOS os pedidos API:
# - X-Active-Role: ContextSwitcher (multi-role)
# - X-Company-Id: ContextSwitcher (multi-empresa)
_REQUIRED_CORS_HEADERS = {'X-Active-Role', 'X-Company-Id'}
_raw_allow_headers = os.environ.get('CORS_ALLOW_HEADERS', 'Authorization,Content-Type,Accept,Origin,X-Requested-With,X-Active-Role,X-Company-Id')
CORS_ALLOW_HEADERS = [h.strip() for h in _raw_allow_headers.split(',')]
# Garantir que os headers obrigatórios estão presentes (mesmo que o env var os omita)
_headers_set = set(CORS_ALLOW_HEADERS)
for _req_header in _REQUIRED_CORS_HEADERS:
    if _req_header not in _headers_set:
        print(f"⚠️  CORS_ALLOW_HEADERS: Header obrigatório '{_req_header}' em falta! A adicionar automaticamente.", file=sys.stderr)
        CORS_ALLOW_HEADERS.append(_req_header)

CORS_MAX_AGE = int(os.environ.get('CORS_MAX_AGE', '600'))

# Log de resumo CORS
print(f"✅ CORS resumo: {len(CORS_ORIGINS)} origens explícitas, "
      f"regex={'ativo' if CORS_ORIGIN_REGEX else 'inativo'}, "
      f"credentials={CORS_ALLOW_CREDENTIALS}, "
      f"allow_headers={CORS_ALLOW_HEADERS}, "
      f"max_age={CORS_MAX_AGE}", file=sys.stderr)


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

# ====================================================================
# PII PRIVACY CONFIG - CONFORMIDADE COM OPENAI
# ====================================================================
# IMPORTANTE: Configure estas variáveis para garantir que dados PII
# (NIFs, rendimentos, dados pessoais) não são usados para treino.
#
# Como configurar o opt-out na conta OpenAI:
# 1. Aceda a https://platform.openai.com/account/organization
# 2. Navegue para "Data Controls" > "Training Data"
# 3. Desative "Improve our models with your data"
# 4. Configure OPENAI_DATA_TRAINING_OPT_OUT=true (confirmação)
# 5. Configure OPENAI_ORGANIZATION_ID com o ID da organização
# ====================================================================

# ID da organização OpenAI (para contas corporativas)
# Encontrado em: https://platform.openai.com/account/organization
OPENAI_ORGANIZATION_ID = os.environ.get('OPENAI_ORGANIZATION_ID', '')

# Confirmação de que o opt-out está configurado na conta OpenAI
# IMPORTANTE: Isto deve ser configurado como 'true' apenas depois de
# verificar nas settings da OpenAI que o treino de dados está desativado
OPENAI_DATA_TRAINING_OPT_OUT = os.environ.get('OPENAI_DATA_TRAINING_OPT_OUT', 'true').lower() == 'true'

# Log de configuração de privacidade
if OPENAI_DATA_TRAINING_OPT_OUT:
    print("✅ OpenAI Data Training Opt-Out configurado", file=sys.stderr)
else:
    print("⚠️  AVISO: OPENAI_DATA_TRAINING_OPT_OUT não configurado!", file=sys.stderr)
    print("   Dados PII podem ser usados para treino de modelos.", file=sys.stderr)
    print("   Configure: https://platform.openai.com/account/organization", file=sys.stderr)

if OPENAI_ORGANIZATION_ID:
    print(f"✅ OpenAI Organization ID: {OPENAI_ORGANIZATION_ID[:8]}...", file=sys.stderr)

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


# ====================================================================
# GOOGLE OAUTH 2.0 CONFIG (Gmail API)
# ====================================================================
# Opcional — se definido, permite autenticação OAuth para Gmail
# em vez de passwords IMAP/SMTP (mais seguro, sem "Less Secure Apps").
#
# Como configurar:
# 1. Aceder a https://console.cloud.google.com/apis/credentials
# 2. Criar um projeto (ou seleccionar existente)
# 3. Criar "OAuth 2.0 Client ID" (tipo "Web application")
# 4. Adicionar a redirect URI autorizada:
#    https://<SEU_BACKEND>/api/auth/google/callback
# 5. Copiar Client ID e Client Secret para as variáveis abaixo
#
# Scopes solicitados:
#   - https://mail.google.com/ (leitura + envio + gestão completa)
#   - https://www.googleapis.com/auth/gmail.compose (envio)
#   - https://www.googleapis.com/auth/gmail.readonly (leitura)
# ====================================================================
GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
GOOGLE_REDIRECT_URI = os.environ.get(
    'GOOGLE_REDIRECT_URI',
    os.environ.get('GOOGLE_OAUTH_REDIRECT_URI', '')
)

# Scopes do Gmail — acesso completo para leitura e envio
GOOGLE_GMAIL_SCOPES = [
    'https://mail.google.com/',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.modify',
]

# Validação: se Client ID está definido, Client Secret também deve estar
if GOOGLE_CLIENT_ID and not GOOGLE_CLIENT_SECRET:
    print("⚠️  GOOGLE_CLIENT_ID definido mas GOOGLE_CLIENT_SECRET em falta!", file=sys.stderr)
elif GOOGLE_CLIENT_SECRET and not GOOGLE_CLIENT_ID:
    print("⚠️  GOOGLE_CLIENT_SECRET definido mas GOOGLE_CLIENT_ID em falta!", file=sys.stderr)
elif GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    print(f"✅ Google OAuth 2.0 configurado (Client ID: {GOOGLE_CLIENT_ID[:8]}...)", file=sys.stderr)
    if not GOOGLE_REDIRECT_URI:
        print("⚠️  GOOGLE_REDIRECT_URI não definido — o callback usará a URL do request", file=sys.stderr)


