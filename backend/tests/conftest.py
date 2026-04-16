"""
Tests for PowerCell API
Configuração central dos testes.

Os utilizadores de teste são criados automaticamente:
- admin@sistema.pt / admin123
- consultor@sistema.pt / consultor123  
- mediador@sistema.pt / mediador123

CI/CD: Variáveis de ambiente dummy são definidas para evitar crash
durante os testes no GitHub Actions.

OTIMIZAÇÕES:
- bcrypt hashing com cache (evita re-hash a cada teste)
- Setup de users/statuses em scope=session (executa 1x)
- client fixture em scope=function (mas sem re-hash)
"""
import os
import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# ==================================================================
# VARIÁVEIS DE AMBIENTE DUMMY PARA CI/CD
# Estas variáveis são definidas ANTES de qualquer import da app
# para evitar que o FastAPI faça crash por falta de credenciais.
# ==================================================================
DUMMY_ENV_VARS = {
    "TESTING": "true",
    "SECRET_KEY": "test_secret_key_for_ci_pipeline_do_not_use_in_production",
    "JWT_SECRET": "test_jwt_secret_for_ci_pipeline_do_not_use_in_production",
    "MONGO_URI": "mongodb://localhost:27017/test_db_ci",
    "MONGODB_URL": "mongodb://localhost:27017/test_db_ci",
    "MONGO_URL": "mongodb://localhost:27017/test_db_ci",
    "DB_NAME": "test_db_ci",
    "CORS_ORIGINS": "http://localhost:3000,http://localhost:5173",
    "REDIS_URL": "none",
    "OPENAI_API_KEY": "sk-test-dummy-key",
    "SENTRY_DSN": "",
    "REACT_APP_BACKEND_URL": "http://localhost:8001",
    "SMTP_SERVER": "smtp.test.com",
    "SMTP_PORT": "587",
    "SMTP_USERNAME": "test@test.com",
    "SMTP_PASSWORD": "test_password",
    "POWER_EMAIL": "power@test.com",
    "POWER_PASSWORD": "test_password",
    "GENIUS_EMAIL": "genius@test.com",
    "GENIUS_PASSWORD": "test_password",
    "AWS_ACCESS_KEY_ID": "AKIAIOSFODNN1EXAMPLE",
    "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "AWS_REGION": "eu-west-1",
    "S3_BUCKET": "test-bucket",
}

# Definir variáveis de ambiente dummy ANTES de importar a app
for key, value in DUMMY_ENV_VARS.items():
    os.environ.setdefault(key, value)

# CORREÇÃO: Definir modo de teste ANTES de importar a app
os.environ["TESTING"] = "true"

# Adicionar backend ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

# URL fictício para os testes
API_URL = "http://testserver/api"

# Utilizadores de teste
TEST_USERS = [
    {
        "email": "admin@sistema.pt",
        "password": "admin123",
        "name": "Admin Teste",
        "role": "admin"
    },
    {
        "email": "consultor@sistema.pt",
        "password": "consultor123",
        "name": "Consultor Teste",
        "role": "consultor"
    },
    {
        "email": "mediador@sistema.pt",
        "password": "mediador123",
        "name": "Mediador Teste",
        "role": "mediador"
    }
]

# ==================================================================
# CACHE DE BCRYPT — evitar re-hash a cada teste (~25s economizados)
# ==================================================================
_bcrypt_cache = {}  # email -> hashed_password


def _get_cached_hash(email, password):
    """Retorna hash bcrypt em cache, ou gera e cacheia se necessário."""
    if email in _bcrypt_cache:
        return _bcrypt_cache[email]

    import bcrypt
    hashed = bcrypt.hashpw(
        password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")

    _bcrypt_cache[email] = hashed
    return hashed


async def ensure_test_users_exist():
    """
    Garantir que os utilizadores de teste existem na base de dados.
    Usa cache de bcrypt para evitar re-hash a cada invocação.
    """
    try:
        from database import get_db

        db = get_db()

        for user_data in TEST_USERS:
            existing = await db.users.find_one({"email": user_data["email"]})

            if existing:
                # Não re-hash se o utilizador já existe — economiza ~100ms
                pass
            else:
                hashed_password = _get_cached_hash(user_data["email"], user_data["password"])
                await db.users.insert_one({
                    "id": str(uuid.uuid4()),
                    "email": user_data["email"],
                    "password": hashed_password,
                    "name": user_data["name"],
                    "role": user_data["role"],
                    "phone": "+351 900000000",
                    "is_active": True,
                    "created_at": datetime.now(timezone.utc).isoformat()
                })
    except Exception as e:
        print(f"Warning: Could not ensure test users exist: {e}")


async def ensure_workflow_statuses_exist():
    """Garante que os workflow statuses padrão existem na base de dados de teste."""
    try:
        from database import get_db
        db = get_db()

        existing = await db.workflow_statuses.count_documents({})
        if existing > 0:
            return  # Já existem

        default_statuses = [
            {"id": str(uuid.uuid4()), "name": "clientes_espera", "label": "Clientes em Espera", "order": 1, "color": "yellow", "is_default": True},
            {"id": str(uuid.uuid4()), "name": "fase_documental", "label": "Fase Documental", "order": 2, "color": "blue", "is_default": True},
            {"id": str(uuid.uuid4()), "name": "fase_documental_ii", "label": "Fase Documental II", "order": 3, "color": "blue", "is_default": True},
            {"id": str(uuid.uuid4()), "name": "enviado_bruno", "label": "Enviado ao Bruno", "order": 4, "color": "purple", "is_default": True},
            {"id": str(uuid.uuid4()), "name": "enviado_luis", "label": "Enviado ao Luís", "order": 5, "color": "purple", "is_default": True},
            {"id": str(uuid.uuid4()), "name": "enviado_bcp_rui", "label": "Enviado BCP Rui", "order": 6, "color": "purple", "is_default": True},
            {"id": str(uuid.uuid4()), "name": "entradas_precision", "label": "Entradas Precision", "order": 7, "color": "orange", "is_default": True},
            {"id": str(uuid.uuid4()), "name": "fase_bancaria", "label": "Fase Bancária - Pré Aprovação", "order": 8, "color": "orange", "is_default": True},
            {"id": str(uuid.uuid4()), "name": "fase_visitas", "label": "Fase de Visitas", "order": 9, "color": "blue", "is_default": True},
            {"id": str(uuid.uuid4()), "name": "ch_aprovado", "label": "CH Aprovado - Avaliação", "order": 10, "color": "green", "is_default": True},
            {"id": str(uuid.uuid4()), "name": "fase_escritura", "label": "Fase de Escritura", "order": 11, "color": "green", "is_default": True},
            {"id": str(uuid.uuid4()), "name": "escritura_agendada", "label": "Escritura Agendada", "order": 12, "color": "green", "is_default": True},
            {"id": str(uuid.uuid4()), "name": "concluidos", "label": "Concluídos", "order": 13, "color": "green", "is_default": True},
            {"id": str(uuid.uuid4()), "name": "desistencias", "label": "Desistências", "order": 14, "color": "red", "is_default": True},
        ]

        await db.workflow_statuses.insert_many(default_statuses)
        print(f"Created {len(default_statuses)} default workflow statuses for tests")
    except Exception as e:
        print(f"Warning: Could not ensure workflow statuses exist: {e}")


@pytest.fixture(scope="session", autouse=True)
def _setup_test_data():
    """
    Setup de dados de teste — executa UMA VEZ por sessão.
    Garante que os users e workflow statuses existem antes dos testes.
    
    Usa asyncio.run() com event loop próprio para evitar conflitos
    com pytest-asyncio loop_scope (Mode.AUTO default_loop_scope=function).
    """
    import asyncio

    async def _do_setup():
        from database import reset_db_connection
        reset_db_connection()
        await ensure_test_users_exist()
        await ensure_workflow_statuses_exist()

    asyncio.run(_do_setup())


@pytest_asyncio.fixture
async def client():
    """
    Cria um cliente HTTP assíncrono que fala DIRETAMENTE com a app.
    Reset da conexão DB antes de cada teste para evitar problemas de event loop.
    
    NOTA: Users e workflow statuses são criados pelo _setup_test_data (session scope).
    """
    from database import reset_db_connection
    from server import app
    from middleware.rate_limit import limiter

    # Reset conexão DB para forçar nova conexão com o event loop actual
    reset_db_connection()

    # Garantia extra de que o rate limit está off
    limiter.enabled = False

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url=API_URL,
        timeout=30.0
    ) as ac:
        yield ac


# --- Fixtures de Autenticação ---

@pytest_asyncio.fixture
async def admin_token(client):
    """Obter token de admin."""
    response = await client.post("/auth/login-v2", json={
        "email": "admin@sistema.pt",
        "password": "admin123"
    })

    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["access_token"]


@pytest_asyncio.fixture
async def consultor_token(client):
    """Obter token de consultor."""
    response = await client.post("/auth/login-v2", json={
        "email": "consultor@sistema.pt",
        "password": "consultor123"
    })
    assert response.status_code == 200, f"Consultor login failed: {response.text}"
    return response.json()["access_token"]


@pytest_asyncio.fixture
async def mediador_token(client):
    """Obter token de mediador."""
    response = await client.post("/auth/login-v2", json={
        "email": "mediador@sistema.pt",
        "password": "mediador123"
    })
    assert response.status_code == 200, f"Mediador login failed: {response.text}"
    return response.json()["access_token"]


# --- Fixtures para Testes de Integração ---

@pytest_asyncio.fixture
async def test_client(client):
    """Alias para client fixture (compatibilidade com novos testes)."""
    yield client


@pytest_asyncio.fixture
def test_credentials():
    """Credenciais de teste para diferentes roles."""
    return {
        "admin": {"email": "admin@sistema.pt", "password": "admin123"},
        "consultor": {"email": "consultor@sistema.pt", "password": "consultor123"},
        "mediador": {"email": "mediador@sistema.pt", "password": "mediador123"}
    }


@pytest_asyncio.fixture
async def auth_headers(client, test_credentials):
    """Headers de autenticação com token de admin."""
    response = await client.post("/auth/login-v2", json=test_credentials["admin"])

    if response.status_code == 200:
        token = response.json().get("access_token") or response.json().get("token")
        return {"Authorization": f"Bearer {token}"}

    # Fallback para testes que não precisam de auth real
    return {"Authorization": "Bearer test_token"}


@pytest_asyncio.fixture
async def gestor_headers(client):
    """Headers de autenticação para gestor de documentos."""
    response = await client.post("/auth/login-v2", json={
        "email": "powerprecision@sistema.pt",
        "password": "PowerCell"
    })

    if response.status_code == 200:
        token = response.json().get("access_token") or response.json().get("token")
        return {"Authorization": f"Bearer {token}"}

    return {"Authorization": "Bearer test_token"}
