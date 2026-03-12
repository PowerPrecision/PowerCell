"""
Iteration 16 - Testing Leads Page and Trello Integration
CORRIGIDO: Usa TestClient em vez de requests para não depender de servidor externo.
"""
import pytest
from fastapi.testclient import TestClient
import sys
import os
from pathlib import Path

# Adicionar backend ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from server import app

# Cliente síncrono para testes que não são async
client = TestClient(app)

class TestAdminLogin:
    """Test admin authentication"""
    
    def test_admin_login_success(self):
        """Test login with admin credentials"""
        # Tenta password do seed.py primeiro
        response = client.post("/api/auth/login", json={
            "email": "admin@sistema.pt",
            "password": "admin123"
        })
        
        # Fallback para outra password se falhar
        if response.status_code != 200:
            response = client.post("/api/auth/login", json={
                "email": "admin@sistema.pt",
                "password": "admin2026"
            })
        
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data
        return data["access_token"]

class TestLeadsEndpoints:
    """Test Leads API endpoints"""
    
    def get_auth_token(self):
        # Helper para login
        res = client.post("/api/auth/login", json={"email": "admin@sistema.pt", "password": "admin123"})
        if res.status_code != 200:
             res = client.post("/api/auth/login", json={"email": "admin@sistema.pt", "password": "admin2026"})
        return res.json().get("access_token")
    
    def test_leads_list_endpoint(self):
        """Test /api/leads returns list of leads"""
        token = self.get_auth_token()
        response = client.get(
            "/api/leads",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_leads_create_requires_url(self):
        """Test creating lead requires URL field"""
        token = self.get_auth_token()
        response = client.post(
            "/api/leads",
            headers={"Authorization": f"Bearer {token}"},
            json={"title": "Test Lead", "price": 250000} # Missing URL
        )
        # 422 é o erro padrão do FastAPI para validação
        assert response.status_code == 422

class TestNavigationEndpoints:
    
    def get_auth_token(self):
        res = client.post("/api/auth/login", json={"email": "admin@sistema.pt", "password": "admin123"})
        if res.status_code != 200:
             res = client.post("/api/auth/login", json={"email": "admin@sistema.pt", "password": "admin2026"})
        return res.json().get("access_token")

    def test_users_list_endpoint(self):
        token = self.get_auth_token()
        response = client.get("/api/users", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_properties_endpoint(self):
        token = self.get_auth_token()
        response = client.get("/api/properties", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200