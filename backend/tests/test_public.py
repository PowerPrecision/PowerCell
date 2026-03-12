import pytest


@pytest.mark.asyncio
async def test_public_client_registration(client):
    """Test public client registration creates user and process"""
    import uuid
    unique_email = f"test_{uuid.uuid4().hex[:8]}@email.pt"
    
    response = await client.post("/public/client-registration", json={
        "name": "Test Cliente Pytest",
        "email": unique_email,
        "phone": "+351 999 000 111",
        "process_type": "credito"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "process_id" in data
    # A mensagem pode variar se email foi enviado ou não
    assert "Registo criado com sucesso" in data["message"]


@pytest.mark.asyncio
async def test_public_registration_missing_fields(client):
    """Test public registration with missing required fields"""
    response = await client.post("/public/client-registration", json={
        "name": "Test User"
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_public_registration_invalid_email(client):
    """Test public registration with invalid email format"""
    response = await client.post("/public/client-registration", json={
        "name": "Test User",
        "email": "not-an-email",
        "phone": "+351 999 000 111",
        "process_type": "credito"
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_public_registration_with_personal_data(client):
    """Test public registration with optional personal data"""
    import uuid
    import random
    unique_email = f"test_full_{uuid.uuid4().hex[:8]}@email.pt"
    
    # Gerar NIF válido e único para cada teste
    # Usar timestamp para garantir unicidade
    import time
    ts = str(int(time.time() * 1000))[-7:]  # últimos 7 dígitos do timestamp
    base = "1" + ts  # Começar com 1 (válido para particulares)
    
    # Calcular dígito de controlo
    weights = [9, 8, 7, 6, 5, 4, 3, 2]
    total = sum(int(d) * w for d, w in zip(base, weights))
    check_digit = 11 - (total % 11)
    if check_digit >= 10:
        check_digit = 0
    unique_nif = base + str(check_digit)
    
    response = await client.post("/public/client-registration", json={
        "name": "Test Cliente Full",
        "email": unique_email,
        "phone": "+351 888 777 666",
        "process_type": "ambos",
        "personal_data": {
            "nif": unique_nif,
            "morada_fiscal": "Rua de Teste, 123",
            "nacionalidade": "Portuguesa"
        },
        "financial_data": {
            "renda_habitacao_atual": 500.00,
            "capital_proprio": 25000.00,
            "efetivo": "Sim"
        }
    })
    assert response.status_code == 200
    data = response.json()
    # success deve ser True para registo bem sucedido
    assert data.get("success") is True or "process_id" in data


@pytest.mark.asyncio
async def test_public_registration_all_process_types(client):
    """Test all process types are accepted"""
    import uuid
    
    for process_type in ["credito", "imobiliaria", "ambos"]:
        unique_email = f"test_tipo_{process_type}_{uuid.uuid4().hex[:8]}@email.pt"
        response = await client.post("/public/client-registration", json={
            "name": f"Test Tipo {process_type}",
            "email": unique_email,
            "phone": "+351 111 222 333",
            "process_type": process_type
        })
        assert response.status_code == 200, f"Failed for type: {process_type}"
