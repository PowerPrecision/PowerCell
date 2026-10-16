"""O link de acesso do email de boas-vindas do staff vem de `FRONTEND_URL` (Lote 7.2).

O defeito: `run_create_user` escrevia `https://powercell.vercel.app` à letra — texto e botão. Um deploy
que mude de domínio (ou um ambiente de QA) mandava a equipa nova para um sítio que já não é o nosso, sem
erro nenhum. Os testes correm o `run_create_user` REAL e inspeccionam o que chega ao `send_email`.
"""
from unittest.mock import patch

import pytest

import services.admin_users as admin_users
import services.email_service as email_service
import services.user_company_bootstrap as bootstrap

ADMIN = {"id": "u-admin", "name": "Admin", "role": "master", "effective_role": "master"}


async def _sem_efeito(*a, **k):
    return None


async def _criar(fake_async_db, monkeypatch, *, frontend_env, frontend_url=None):
    from models.auth import UserCreate

    if frontend_env is None:
        monkeypatch.delenv("FRONTEND_URL", raising=False)
    else:
        monkeypatch.setenv("FRONTEND_URL", frontend_env)
    fake_async_db.companies.docs.append({"id": "cmp-power", "name": "Power Real Estate"})
    dados = UserCreate(
        email="nova@power.pt", password="Segura123!", name="Nova Pessoa",
        role="consultor", companies=[{"company_id": "cmp-power"}],
    )
    enviados = []

    async def envio(**kw):
        enviados.append(kw)
        return {"success": True}

    with patch.object(admin_users, "db", fake_async_db), patch.object(bootstrap, "db", fake_async_db), \
         patch.object(email_service, "send_email", envio), patch.object(admin_users, "_audit_log", _sem_efeito):
        await admin_users.run_create_user(dados, ADMIN, frontend_url=frontend_url)
    return enviados[0]


@pytest.mark.asyncio
class TestOLinkDeAcesso:
    async def test_o_ataque_o_link_sai_de_FRONTEND_URL_e_nao_de_um_literal(self, fake_async_db, monkeypatch):
        mail = await _criar(fake_async_db, monkeypatch, frontend_env="https://crm.exemplo.pt/")
        assert 'href="https://crm.exemplo.pt/login"' in mail["body_html"]
        assert "https://crm.exemplo.pt/login" in mail["body"]
        assert "vercel.app" not in mail["body_html"] + mail["body"]

    async def test_sem_FRONTEND_URL_vale_o_dominio_de_onde_o_admin_trabalha(self, fake_async_db, monkeypatch):
        mail = await _criar(fake_async_db, monkeypatch, frontend_env=None, frontend_url="https://staging.exemplo.pt")
        assert 'href="https://staging.exemplo.pt/login"' in mail["body_html"]

    async def test_FRONTEND_URL_vence_o_pedido(self, fake_async_db, monkeypatch):
        mail = await _criar(fake_async_db, monkeypatch, frontend_env="https://crm.exemplo.pt", frontend_url="https://outro.pt")
        assert "outro.pt" not in mail["body_html"]

    async def test_sem_nenhum_dominio_o_email_sai_sem_botao_e_sem_link_morto(self, fake_async_db, monkeypatch):
        mail = await _criar(fake_async_db, monkeypatch, frontend_env=None)
        assert "href=" not in mail["body_html"]
        assert "Aceder à Plataforma" not in mail["body_html"]
        assert "http" not in mail["body"]
        # os dados de acesso continuam lá: é o email que a pessoa precisa de receber
        assert "nova@power.pt" in mail["body"]


def test_url_de_acesso_normaliza_barras(monkeypatch):
    monkeypatch.setenv("FRONTEND_URL", "https://crm.exemplo.pt///")
    assert admin_users.url_de_acesso_ao_crm() == "https://crm.exemplo.pt/login"
