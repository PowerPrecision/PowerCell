"""
PORTAL DO PARCEIRO — O CAMINHO HTTP COMPLETO

Os testes de serviço chamam funções; este corre os pedidos pela pilha real
(FastAPI + dependências + o `limiter` de produção). Apanha o que uma função
chamada directamente não vê:

  * `@limiter.limit` sem `response: Response` devolve 500 num SUCESSO — e
    uma bateria só de rejeições (403/404) nunca o prova (foi o que
    aconteceu aos endpoints do Portal do Cliente);
  * uma dependência mal ligada (a rota que não exige sessão);
  * a validação `extra="forbid"` como 422 à porta;
  * as famílias de tokens a rejeitarem-se mutuamente PELA PILHA, com os
    produtores reais.
"""
from __future__ import annotations

import contextlib
import copy
import re
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from tests.unit.helpers_tenant import (  # noqa: F401
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)
from tests.unit.test_parceiro_escrita import _S3Falso
from tests.unit.test_parceiro_leitura import FASES, _lead, _proc

PASSWORD = "Parceiro#2026x"
ADMIN = {"id": "u-ana", "name": "Ana", "email": "ana@power.pt", "role": "admin", "effective_role": "admin"}


@pytest.fixture
def cliente(fake_async_db, rede_de_omissao_incumbente, monkeypatch, limiter_de_producao_ligado):
    """Uma app mínima com os dois routers do parceiro + uma rota de staff e
    uma do Portal do Cliente (para provar o cruzamento de famílias)."""
    import services.audit_trail_service as audit
    import services.document_intake as intake
    import services.document_portal_counts as counts
    import services.history as history
    import services.partner_accounts as acc
    import services.partner_leads as leads
    import services.partner_portal_read as ppr
    import services.partner_security as sec
    import services.partner_upload_ops as ops
    import services.portal_upload_ops as portal_ops
    import services.admin_users_scope as scope_mod
    import services.user_management_scope as ums
    from middleware.rate_limit import limiter
    from routes.partner_portal import router as router_parceiro
    from routes.partners_admin import router as router_admin
    from services.auth import get_current_user
    from services.portal_security import get_current_client

    monkeypatch.delenv("FRONTEND_URL", raising=False)
    monkeypatch.delenv("JWT_PARTNER_SECRET", raising=False)
    semear(fake_async_db)
    fake_async_db.workflow_statuses.docs.extend(dict(f) for f in FASES)
    s3 = _S3Falso()
    veredicto = AsyncMock(return_value=SimpleNamespace(tamanho=2048, tipo_detectado="application/pdf"))

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(router_parceiro, prefix="/api")
    app.include_router(router_admin, prefix="/api")

    @app.get("/api/_staff")
    async def _staff(user: dict = Depends(get_current_user)):
        return {"ok": True}

    @app.get("/api/_portal_cliente")
    async def _portal(c: dict = Depends(get_current_client)):
        return {"ok": True}

    with contextlib.ExitStack() as pilha:
        pilha.enter_context(tenant_db(fake_async_db, acc, sec, ppr, leads, ops, intake, counts, history, portal_ops,
                                      audit, scope_mod, ums))
        pilha.enter_context(patch.object(ops, "s3_service", s3))
        pilha.enter_context(patch.object(portal_ops, "s3_service", s3))
        pilha.enter_context(patch.object(ops, "exigir_conteudo_valido", veredicto))
        pilha.enter_context(patch("services.background_tasks.spawn_background_task",
                                  lambda coro, name=None: (coro.close(), MagicMock())[1]))
        yield SimpleNamespace(http=TestClient(app), bd=fake_async_db, s3=s3, veredicto=veredicto, acc=acc)


def _correr(coro):
    """Corre uma corotina de preparação a partir de um teste/fixture síncrono."""
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _criar_parceiro(acc, bd, email="rui@parceiros.pt"):
    convite = await acc.run_invite_partner(
        acc.PartnerInvite(name="Rui Parceiro", email=email, company_id="cmp-power"), ADMIN
    )
    await acc.run_accept_invite(
        acc.PartnerAcceptInvite(token=convite["invite_token"], password=PASSWORD, accept_terms=True)
    )
    return bd.partners.docs[-1]["id"]


def _entrar(c, email="rui@parceiros.pt", password=PASSWORD):
    return c.http.post("/api/partner/auth/login", json={"email": email, "password": password})


@pytest.fixture
def sessao(cliente):
    pid = _correr(_criar_parceiro(cliente.acc, cliente.bd))
    r = _entrar(cliente)
    assert r.status_code == 200, r.text
    cliente.pid = pid
    cliente.cab = {"Authorization": f"Bearer {r.json()['access_token']}"}
    return cliente


# ════════════════════════════════════════════════════════════════════
#  O SUCESSO PELA PILHA REAL (o limiter não pode dar 500)
# ════════════════════════════════════════════════════════════════════
class TestOSucessoPelaPilha:
    def test_login_certo_e_200_com_os_cabecalhos_do_limiter(self, cliente):
        _correr(_criar_parceiro(cliente.acc, cliente.bd))
        r = _entrar(cliente)
        assert r.status_code == 200, r.text
        assert r.json()["token_type"] == "bearer" and "access_token" in r.json()
        assert "x-ratelimit-limit" in {k.lower() for k in r.headers}, "o limiter correu mesmo"

    def test_me_painel_lista_e_detalhe(self, sessao):
        c = sessao
        c.bd.processes.docs.append(_proc("a-novo", c.pid))
        c.bd.clients.docs.append(_lead("lead-1", c.pid))
        assert c.http.get("/api/partner/me", headers=c.cab).json()["email"] == "rui@parceiros.pt"
        assert c.http.get("/api/partner/dashboard", headers=c.cab).status_code == 200
        lista = c.http.get("/api/partner/cases?size=10", headers=c.cab)
        assert lista.status_code == 200 and lista.json()["total"] == 2
        assert c.http.get("/api/partner/cases/a-novo", headers=c.cab).json()["kind"] == "process"
        assert c.http.get("/api/partner/cases/nao-existe", headers=c.cab).status_code == 404

    def test_submeter_uma_lead_e_200_e_aparece_na_lista(self, sessao):
        c = sessao
        r = c.http.post("/api/partner/leads", headers=c.cab, json={
            "name": "Joana Cliente", "email": "joana@c.pt", "phone": "912345678", "consent_confirmed": True,
        })
        assert r.status_code == 200, r.text
        assert "x-ratelimit-limit" in {k.lower() for k in r.headers}
        ids = [i["id"] for i in c.http.get("/api/partner/cases", headers=c.cab).json()["items"]]
        assert r.json()["id"] in ids

    def test_o_fluxo_de_ficheiros_url_confirmar_e_descarregar(self, sessao):
        c = sessao
        c.bd.processes.docs.append(_proc("a-novo", c.pid, s3_folder="Documentação Clientes/cli-a-novo"))
        c.bd.clients.docs.append({"id": "cli-a-novo", "nome": "C", "s3_folder": "Documentação Clientes/cli-a-novo"})

        url = c.http.post("/api/partner/cases/a-novo/upload-url", headers=c.cab, json={"filename": "cc.pdf"})
        assert url.status_code == 200, url.text
        chave = url.json()["file_key"]

        ok = c.http.post("/api/partner/cases/a-novo/confirm-upload", headers=c.cab,
                         json={"file_key": chave, "original_filename": "cc.pdf"})
        assert ok.status_code == 200, ok.text
        assert chave not in ok.text and "http" not in ok.text

        d = c.http.get(f"/api/partner/cases/a-novo/files/{ok.json()['id']}/download-url", headers=c.cab)
        assert d.status_code == 200 and d.json()["url"] == "https://s3.exemplo/get"

    def test_a_mudanca_de_palavra_passe_pela_pilha(self, sessao):
        c = sessao
        r = c.http.post("/api/partner/auth/change-password", headers=c.cab,
                        json={"current_password": PASSWORD, "new_password": "Outra#Pass2027"})
        assert r.status_code == 200, r.text
        assert c.http.get("/api/partner/me", headers=c.cab).status_code == 401, "a sessão antiga morreu"
        novo = {"Authorization": f"Bearer {r.json()['access_token']}"}
        assert c.http.get("/api/partner/me", headers=novo).status_code == 200


# ════════════════════════════════════════════════════════════════════
#  SEM SESSÃO
# ════════════════════════════════════════════════════════════════════
def _rotas_do_parceiro():
    from routes.partner_portal import ROTAS_SEM_SESSAO, router

    for rota in router.routes:
        for metodo in rota.methods - {"HEAD", "OPTIONS"}:
            yield metodo, "/api" + re.sub(r"\{[^}]+\}", "x", rota.path), rota.endpoint.__name__ in ROTAS_SEM_SESSAO


class TestSemSessao:
    def test_o_leitor_encontra_as_rotas(self):
        assert len(list(_rotas_do_parceiro())) >= 12

    @pytest.mark.parametrize("metodo,caminho", [(m, p) for m, p, livre in _rotas_do_parceiro() if not livre])
    def test_toda_a_rota_protegida_recusa_quem_nao_traz_token(self, cliente, metodo, caminho):
        r = cliente.http.request(metodo, caminho, json={} if metodo != "GET" else None)
        assert r.status_code == 401, (metodo, caminho, r.status_code)

    @pytest.mark.parametrize("metodo,caminho", [(m, p) for m, p, livre in _rotas_do_parceiro() if not livre])
    def test_nem_com_um_token_lixo(self, cliente, metodo, caminho):
        r = cliente.http.request(metodo, caminho, headers={"Authorization": "Bearer lixo.lixo.lixo"},
                                 json={} if metodo != "GET" else None)
        assert r.status_code == 401

    def test_as_rotas_de_gestao_recusam_quem_nao_traz_token(self, cliente):
        for metodo, caminho in (("GET", "/api/admin/partners"), ("POST", "/api/admin/partners/invite"),
                                ("GET", "/api/admin/partners/x"), ("PATCH", "/api/admin/partners/x"),
                                ("POST", "/api/admin/partners/x/resend-invite")):
            assert cliente.http.request(metodo, caminho, json={}).status_code in (401, 403), (metodo, caminho)


# ════════════════════════════════════════════════════════════════════
#  AS FAMÍLIAS DE TOKENS, PELA PILHA
# ════════════════════════════════════════════════════════════════════
class TestFamiliasPelaPilha:
    def test_um_token_de_parceiro_nao_abre_o_staff_nem_o_portal_do_cliente(self, sessao):
        c = sessao
        assert c.http.get("/api/_staff", headers=c.cab).status_code == 401
        assert c.http.get("/api/_portal_cliente", headers=c.cab).status_code == 401
        assert c.http.get("/api/admin/partners", headers=c.cab).status_code in (401, 403)

    def test_os_tokens_do_staff_e_do_portal_nao_abrem_o_parceiro(self, sessao):
        from services.auth import create_token
        from services.portal_security import create_access_code_session_token
        from services.refresh_token_service import create_access_token

        for token in (
            create_access_token("u-ana", "ana@power.pt", "admin"),
            create_token("u-ana", "ana@power.pt", "admin"),
            create_access_code_session_token("proc-1", "cli-1"),
        ):
            r = sessao.http.get("/api/partner/me", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 401


# ════════════════════════════════════════════════════════════════════
#  VALIDAÇÃO À PORTA E TRAVÃO
# ════════════════════════════════════════════════════════════════════
class TestValidacaoETravao:
    def test_campos_a_mais_sao_422(self, sessao):
        c = sessao
        base = {"name": "Joana Cliente", "email": "joana@c.pt", "consent_confirmed": True}
        for extra in ({"lead_status": "converted"}, {"submitted_by_partner_id": "outro"}, {"company_id": "cmp-domus"}):
            assert c.http.post("/api/partner/leads", headers=c.cab, json={**base, **extra}).status_code == 422
        assert c.http.post("/api/partner/auth/login", json={"email": "a@b.pt", "password": "x", "admin": True}).status_code == 422

    def test_o_travao_de_login_pela_pilha(self, sessao):
        from services.portal_brute_force import MAX_TENTATIVAS

        c = sessao
        c.bd.portal_login_attempts.docs.clear()
        for _ in range(MAX_TENTATIVAS):
            assert _entrar(c, password="Errada#Pass1x").status_code == 401
        bloqueado = _entrar(c)  # a password CERTA
        assert bloqueado.status_code == 429 and "retry-after" in {k.lower() for k in bloqueado.headers}

    def test_em_producao_sem_segredo_o_portal_responde_503(self, cliente, monkeypatch):
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.delenv("JWT_PARTNER_SECRET", raising=False)
        assert _entrar(cliente).status_code == 503
        assert cliente.http.get("/api/partner/me", headers={"Authorization": "Bearer x.y.z"}).status_code == 503

    def test_o_convite_pela_pilha(self, cliente):
        convite = _correr(
            cliente.acc.run_invite_partner(
                cliente.acc.PartnerInvite(name="Rui Parceiro", email="rui@parceiros.pt", company_id="cmp-power"), ADMIN
            )
        )
        token = convite["invite_token"]
        assert cliente.http.get(f"/api/partner/auth/invite/{token}").json()["email"] == "rui@parceiros.pt"
        assert cliente.http.get("/api/partner/auth/invite/" + "x" * 40).status_code == 400
        r = cliente.http.post("/api/partner/auth/accept-invite",
                              json={"token": token, "password": PASSWORD, "accept_terms": True})
        assert r.status_code == 200 and r.json()["partner"]["status"] == "active"
        assert cliente.http.post("/api/partner/auth/accept-invite",
                                 json={"token": token, "password": PASSWORD, "accept_terms": True}).status_code == 400
