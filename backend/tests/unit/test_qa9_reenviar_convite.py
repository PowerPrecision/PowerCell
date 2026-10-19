"""QA-9, ponto 2 — «Reenviar convite» a um utilizador do CRM.

A palavra-passe guardada é um hash: não há «credenciais iniciais» para reenviar. O reenvio gera
uma nova, manda-a por email (o mesmo texto da criação) e só então a grava. `TestAExploracao` é o
ataque: o que um perfil local NÃO pode fazer.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from tests.unit.helpers_tenant import (  # noqa: F401
    db_tenant,  # noqa: F401  (fixture)
    tenant_db as _tenant_db,
)

CEO_PRECISION = {"id": "u-ceo-p", "name": "CEO P", "role": "ceo"}
CEO_DOMUS = {"id": "u-ceo-d", "name": "CEO D", "role": "ceo"}
MASTER = {"id": "u-master", "name": "Master", "role": "master"}


@pytest.fixture
def base(db_tenant):  # noqa: F811
    def _u(uid, role, empresa_id, nome_empresa, **extra):
        db_tenant.users.docs.append({
            "id": uid, "name": uid.upper(), "email": f"{uid}@x.pt", "role": role,
            "is_active": True, "password": "HASH-ANTIGO", "company": nome_empresa, **extra,
        })
        db_tenant.user_company_roles.docs.append({
            "user_id": uid, "company_id": empresa_id, "company_name": nome_empresa,
            "role": role, "is_default": True,
        })

    _u("u-ceo-p", "ceo", "cmp-precision", "Precision Crédito")
    _u("u-cons-p", "consultor", "cmp-precision", "Precision Crédito")
    _u("u-ceo-d", "ceo", "cmp-domus", "Domus")
    _u("u-off", "consultor", "cmp-precision", "Precision Crédito", is_active=False)
    db_tenant.users.docs.append({
        "id": "u-parc", "name": "Parceiro", "email": "parceiro_ab12@placeholder.internal",
        "role": "parceiro", "is_active": True, "password": None,
    })
    db_tenant.users.docs.append({
        "id": "u-master", "name": "Master", "email": "m@x.pt", "role": "master",
        "is_active": True, "password": "HASH-MASTER",
    })
    return db_tenant


@pytest.fixture
def emails(monkeypatch):
    """`send_email` com a assinatura REAL, a registar o que sairia (nunca um duplo de **kwargs)."""
    import services.email_service as es

    enviados: list[dict] = []
    resultado = {"success": True}

    async def _falso(account_name, to_emails, subject, body, body_html=None, **kw):
        enviados.append({"to": to_emails, "subject": subject, "body": body, "html": body_html})
        return dict(resultado)

    monkeypatch.setattr(es, "send_email", _falso)
    monkeypatch.setenv("FRONTEND_URL", "https://crm.exemplo.pt")
    enviados_api = type("E", (), {"lista": enviados, "resultado": resultado})
    return enviados_api


async def _reenviar(base, ator, alvo):
    from services import admin_helpers, admin_users, admin_users_scope, user_management_scope
    from services.admin_users import run_resend_user_access
    from unittest.mock import patch

    with _tenant_db(base, admin_users_scope, user_management_scope, admin_users, admin_helpers), \
            patch("services.refresh_token_service.db", base):
        return await run_resend_user_access(alvo, ator)


def _hash_de(base, uid):
    return next(u for u in base.users.docs if u["id"] == uid)["password"]


class TestOReenvio:

    @pytest.mark.asyncio
    async def test_gera_password_nova_envia_por_email_e_nao_a_devolve(self, base, emails):
        res = await _reenviar(base, CEO_PRECISION, "u-cons-p")

        assert res["success"] is True and res["email"] == "u-cons-p@x.pt"
        assert len(emails.lista) == 1
        mail = emails.lista[0]
        assert mail["to"] == ["u-cons-p@x.pt"]
        assert "Novos dados de acesso" in mail["subject"]
        assert "nova palavra-passe" in mail["body"]
        assert "https://crm.exemplo.pt/login" in mail["body"]
        # A palavra-passe que sai no email é a que ficou gravada (como hash)…
        from services.auth import verify_password

        enviada = next(l for l in mail["body"].splitlines() if "Password:" in l).split("Password:")[1].strip()
        assert verify_password(enviada, _hash_de(base, "u-cons-p"))
        # …e nunca volta na resposta.
        assert enviada not in repr(res)

    @pytest.mark.asyncio
    async def test_se_o_email_nao_sai_a_password_nao_muda(self, base, emails):
        emails.resultado["success"] = False
        with pytest.raises(HTTPException) as exc:
            await _reenviar(base, CEO_PRECISION, "u-cons-p")
        assert exc.value.status_code == 502
        assert _hash_de(base, "u-cons-p") == "HASH-ANTIGO"

    @pytest.mark.asyncio
    async def test_revoga_as_sessoes_anteriores(self, base, emails):
        base.refresh_tokens.docs.append({"user_id": "u-cons-p", "revoked": False})
        base.refresh_tokens.docs.append({"user_id": "u-ceo-p", "revoked": False})
        await _reenviar(base, CEO_PRECISION, "u-cons-p")
        por_user = {t["user_id"]: t["revoked"] for t in base.refresh_tokens.docs}
        assert por_user == {"u-cons-p": True, "u-ceo-p": False}

    @pytest.mark.asyncio
    async def test_deixa_rasto_sem_a_password(self, base, emails):
        await _reenviar(base, CEO_PRECISION, "u-cons-p")
        rasto = [d for d in base.audit_logs.docs if "access_resent" in repr(d)]
        assert rasto, "o reenvio tem de deixar rasto"
        enviada = next(l for l in emails.lista[0]["body"].splitlines() if "Password:" in l).split("Password:")[1].strip()
        assert enviada not in repr(base.audit_logs.docs)

    @pytest.mark.asyncio
    async def test_o_master_reenvia_a_qualquer_empresa(self, base, emails):
        res = await _reenviar(base, MASTER, "u-ceo-d")
        assert res["success"] is True


class TestAExploracao:

    @pytest.mark.asyncio
    async def test_o_ceo_da_domus_nao_reenvia_a_um_utilizador_da_precision(self, base, emails):
        with pytest.raises(HTTPException) as exc:
            await _reenviar(base, CEO_DOMUS, "u-cons-p")
        assert exc.value.status_code == 404
        assert emails.lista == []
        assert _hash_de(base, "u-cons-p") == "HASH-ANTIGO"

    @pytest.mark.asyncio
    async def test_um_perfil_local_nao_alcanca_o_master(self, base, emails):
        with pytest.raises(HTTPException) as exc:
            await _reenviar(base, CEO_PRECISION, "u-master")
        assert exc.value.status_code == 404
        assert _hash_de(base, "u-master") == "HASH-MASTER"

    @pytest.mark.asyncio
    async def test_id_inexistente_e_404(self, base, emails):
        with pytest.raises(HTTPException) as exc:
            await _reenviar(base, CEO_PRECISION, "u-nao-existe")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_a_conta_de_parceiro_sem_acesso_e_recusada(self, base, emails):
        with pytest.raises(HTTPException) as exc:
            await _reenviar(base, MASTER, "u-parc")
        assert exc.value.status_code == 400
        assert "Parceiros" in exc.value.detail
        assert emails.lista == []

    @pytest.mark.asyncio
    async def test_ninguem_reenvia_o_convite_a_si_proprio(self, base, emails):
        with pytest.raises(HTTPException) as exc:
            await _reenviar(base, CEO_PRECISION, "u-ceo-p")
        assert exc.value.status_code == 400
        assert emails.lista == []

    @pytest.mark.asyncio
    async def test_conta_desactivada_e_409(self, base, emails):
        with pytest.raises(HTTPException) as exc:
            await _reenviar(base, CEO_PRECISION, "u-off")
        assert exc.value.status_code == 409
        assert emails.lista == []


class TestALigacao:

    def test_a_rota_existe_esta_limitada_e_so_da_gestao(self):
        from server import app

        rota = next(
            r for r in app.routes
            if getattr(r, "path", "") == "/api/admin/users/{user_id}/resend-invite"
        )
        assert "POST" in rota.methods
        import inspect

        params = inspect.signature(rota.endpoint).parameters
        assert {"request", "response"} <= set(params)  # o limiter exige-os (senão o SUCESSO dá 500)
        from middleware.rate_limit import limiter

        assert any(
            chave.endswith("admin_user_access.resend_user_invite") for chave in limiter._route_limits
        ), "o reenvio faz o servidor enviar email: tem de estar limitado"

    def test_o_email_de_criacao_usa_o_mesmo_helper(self):
        from services import admin_users
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        assert "enviar_email_de_acesso" in codigo_da_funcao_sem_comentarios(admin_users.run_create_user)
        assert "enviar_email_de_acesso" in codigo_da_funcao_sem_comentarios(admin_users.run_resend_user_access)
