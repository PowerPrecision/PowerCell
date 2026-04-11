"""
Testes para endpoints públicos de registo.
CI/CD: Testes que requerem MongoDB fazem pytest.skip quando a BD não está disponível.
"""
import pytest
from pymongo.errors import ServerSelectionTimeoutError, ConnectionFailure


def _require_mongodb():
    """Verifica se MongoDB está acessível. Lança Skip se não."""
    try:
        import asyncio
        from database import get_db
        db = get_db()
        # Teste rápido de conectividade
        loop = asyncio.get_event_loop()
        loop.run_until_complete(db.command("ping"))
    except (ServerSelectionTimeoutError, ConnectionFailure, OSError) as e:
        pytest.skip(f"MongoDB não disponível no CI: {type(e).__name__}")


@pytest.mark.asyncio
async def test_public_client_registration(client):
    """Test public client registration creates user and process"""
    try:
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
        assert "Registo criado com sucesso" in data["message"]
    except (ServerSelectionTimeoutError, ConnectionFailure) as e:
        pytest.skip(f"MongoDB não disponível: {type(e).__name__}")


@pytest.mark.asyncio
async def test_public_registration_missing_fields(client):
    """Test public registration with missing required fields"""
    # Validação de campos não requer MongoDB (Pydantic valida antes)
    response = await client.post("/public/client-registration", json={
        "name": "Test User"
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_public_registration_invalid_email(client):
    """Test public registration with invalid email format"""
    # Validação de campos não requer MongoDB (Pydantic valida antes)
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
    try:
        import uuid
        import random
        unique_email = f"test_full_{uuid.uuid4().hex[:8]}@email.pt"

        # Gerar NIF válido e único para cada teste
        import time
        ts = str(int(time.time() * 1000))[-7:]
        base = "1" + ts

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
        assert data.get("success") is True or "process_id" in data
    except (ServerSelectionTimeoutError, ConnectionFailure) as e:
        pytest.skip(f"MongoDB não disponível: {type(e).__name__}")


@pytest.mark.asyncio
async def test_public_registration_all_process_types(client):
    """Test all process types are accepted"""
    try:
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
    except (ServerSelectionTimeoutError, ConnectionFailure) as e:
        pytest.skip(f"MongoDB não disponível: {type(e).__name__}")
