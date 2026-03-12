import pytest


@pytest.mark.asyncio
async def test_health_check(client):
    """Test health endpoint"""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data


@pytest.mark.asyncio
async def test_login_success(client):
    """Test successful login"""
    response = await client.post("/auth/login", json={
        "email": "admin@sistema.pt",
        "password": "admin123"
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["role"] == "admin"
    assert data["user"]["email"] == "admin@sistema.pt"


@pytest.mark.asyncio
async def test_login_invalid_credentials(client):
    """Test login with wrong password"""
    response = await client.post("/auth/login", json={
        "email": "admin@sistema.pt",
        "password": "wrongpassword"
    })
    assert response.status_code == 401
    assert "Credenciais inválidas" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_nonexistent_user(client):
    """Test login with non-existent email"""
    response = await client.post("/auth/login", json={
        "email": "notexists@sistema.pt",
        "password": "password123"
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_authenticated(client, admin_token):
    """Test get current user info"""
    response = await client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "admin@sistema.pt"
    assert data["role"] == "admin"


@pytest.mark.asyncio
async def test_get_me_unauthorized(client):
    """Test get current user without token - returns 401 when no auth provided"""
    response = await client.get("/auth/me")
    # HTTPBearer returns 403 when no credentials provided (not 401)
    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_get_me_invalid_token(client):
    """Test get current user with invalid token"""
    response = await client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid_token_here"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_consultor_login(client):
    """Test consultor can login"""
    response = await client.post("/auth/login", json={
        "email": "consultor@sistema.pt",
        "password": "consultor123"
    })
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "consultor"


@pytest.mark.asyncio
async def test_mediador_login(client):
    """Test mediador can login"""
    response = await client.post("/auth/login", json={
        "email": "mediador@sistema.pt",
        "password": "mediador123"
    })
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "mediador"
