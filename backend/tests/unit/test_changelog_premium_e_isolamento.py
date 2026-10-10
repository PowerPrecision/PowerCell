"""
Atualizações do Sistema num CRM multi-tenant: isolamento, visibilidade global e Premium.

O QUE SE GARANTE
  1. As atualizações são do CRM: o cliente e o parceiro nunca as lêem — nem com
     um token dos seus portais (cada produtor REAL, nunca um token forjado),
     nem com uma conta fantasma de cliente/parceiro do CRM.
  2. São GLOBAIS: nenhuma condição de rede/empresa na consulta; duas redes
     diferentes veem exactamente o mesmo.
  3. `is_premium`: um campo booleano, falso por omissão (inclusive nas entradas
     antigas), que SÓ o Master escreve — na geração ou depois.

Monta o router REAL de `routes.changelog` e pede por HTTP, com o
`get_current_user` real e a base de dados falsa.
"""
from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, patch

import pytest
from bson import ObjectId
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.unit.helpers_tenant import (  # noqa: F401  (rede_de_omissao_incumbente é fixture)
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

ID_ANTIGO = ObjectId()
ID_NOVO = ObjectId()
ID_PREMIUM = ObjectId()
# Fixo: um id gerado no parametrize difere entre workers do xdist e a recolha falha.
ID_INEXISTENTE = "66f000000000000000000001"

UTILIZADORES = [
    {"id": "u-ana", "email": "ana@power.pt", "name": "Ana", "role": "consultor", "is_active": True},
    {"id": "u-bruno", "email": "bruno@domus.pt", "name": "Bruno", "role": "consultor", "is_active": True},
    {"id": "u-adm", "email": "adm@power.pt", "name": "Admin", "role": "admin", "is_active": True},
    {"id": "u-ceo", "email": "ceo@power.pt", "name": "CEO", "role": "ceo", "is_active": True},
    {"id": "u-master", "email": "m@x.pt", "name": "Master", "role": "master", "is_active": True},
    {"id": "u-cliente", "email": "c@x.pt", "name": "Cliente", "role": "cliente", "is_active": True},
    {"id": "u-parceiro", "email": "p@x.pt", "name": "Parceiro", "role": "parceiro", "is_active": True},
]
UCRS = [
    {"user_id": "u-ana", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "consultor", "is_default": True},
    {"user_id": "u-bruno", "company_id": "cmp-domus", "company_name": "Domus", "role": "consultor", "is_default": True},
]


def _entradas():
    return [
        # Anterior ao campo: não tem `is_premium`.
        {"_id": ID_ANTIGO, "version": "2026-06-25", "content_markdown": "antiga", "published_at": "2026-06-25T10:00:00+00:00",
         "generated_by": "ai", "source_summary": "x"},
        {"_id": ID_NOVO, "version": "2026-09-01", "content_markdown": "nova", "published_at": "2026-09-01T10:00:00+00:00",
         "generated_by": "ai", "source_summary": "y", "is_premium": False},
        {"_id": ID_PREMIUM, "version": "2026-10-01", "content_markdown": "módulo novo", "published_at": "2026-10-01T10:00:00+00:00",
         "generated_by": "ai", "source_summary": "z", "is_premium": True},
    ]


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    import routes.changelog as rota
    import services.auth as auth_mod
    import services.changelog_service as servico

    semear(fake_async_db)
    fake_async_db.users.docs.extend(dict(u) for u in UTILIZADORES)
    fake_async_db.user_company_roles.docs.extend(dict(u) for u in UCRS)
    fake_async_db.system_changelogs.docs.extend(_entradas())

    app = FastAPI()
    app.include_router(rota.router)
    with contextlib.ExitStack() as pilha:
        pilha.enter_context(tenant_db(fake_async_db, auth_mod, servico))
        yield TestClient(app, raise_server_exceptions=False), fake_async_db


def _bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _token_do_crm(user_id: str) -> str:
    """Token de sessão feito pelo produtor REAL do login (nunca forjado)."""
    from services.refresh_token_service import create_access_token

    u = next(x for x in UTILIZADORES if x["id"] == user_id)
    return create_access_token(u["id"], u["email"], u["role"])


# ====================================================================
# 1. ISOLAMENTO — só a equipa do CRM
# ====================================================================

class TestSoAEquipaDoCrmLe:
    def test_sem_token_nao_ha_atualizacoes(self, mundo):
        cliente, _ = mundo
        assert cliente.get("/system/changelog").status_code in (401, 403)

    @pytest.mark.parametrize("origem", ["magic_link", "verified_session", "access_code_session"])
    def test_cada_produtor_real_do_portal_do_cliente_e_recusado(self, mundo, origem):
        from services.portal_security import (
            create_access_code_session_token,
            create_client_magic_token,
            create_verified_session_token,
        )

        cliente, _ = mundo
        token = {
            "magic_link": create_client_magic_token("proc-1"),
            "verified_session": create_verified_session_token("proc-1", "cli-1"),
            "access_code_session": create_access_code_session_token("proc-1", "cli-1"),
        }[origem]
        with patch("routes.changelog.run_list_changelogs", AsyncMock(return_value=["NAO"])) as handler:
            resposta = cliente.get("/system/changelog", headers=_bearer(token))
        assert resposta.status_code == 401
        handler.assert_not_awaited()

    def test_o_token_do_parceiro_e_recusado(self, mundo):
        from services.partner_security import create_partner_token

        cliente, _ = mundo
        with patch("routes.changelog.run_list_changelogs", AsyncMock(return_value=["NAO"])) as handler:
            resposta = cliente.get(
                "/system/changelog", headers=_bearer(create_partner_token({"id": "p1", "token_epoch": 0})),
            )
        assert resposta.status_code == 401
        handler.assert_not_awaited()

    @pytest.mark.parametrize("fantasma", ["u-cliente", "u-parceiro"])
    def test_contas_de_cliente_ou_parceiro_do_crm_nao_lem(self, mundo, fantasma):
        cliente, _ = mundo
        with patch("routes.changelog.run_list_changelogs", AsyncMock(return_value=["NAO"])) as handler:
            resposta = cliente.get("/system/changelog", headers=_bearer(_token_do_crm(fantasma)))
        assert resposta.status_code == 403
        handler.assert_not_awaited()

    def test_a_equipa_le(self, mundo):
        cliente, _ = mundo
        resposta = cliente.get("/system/changelog", headers=_bearer(_token_do_crm("u-ana")))
        assert resposta.status_code == 200
        assert len(resposta.json()) == 3

    def test_os_portais_nao_tem_nada_que_consulte_as_atualizacoes(self):
        """O frontend dos portais nunca chama o endpoint (fonte lida, com contraprova)."""
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[3] / "frontend" / "src"
        ficheiros = [raiz / "pages" / "ClientPortal.jsx"]
        ficheiros += sorted((raiz / "pages" / "partner").glob("*.jsx"))
        ficheiros += sorted((raiz / "components" / "portal").glob("*.jsx"))
        ficheiros += sorted((raiz / "components" / "partner").glob("*.jsx"))
        assert len(ficheiros) >= 8
        for f in ficheiros:
            texto = f.read_text(encoding="utf-8")
            assert "system/changelog" not in texto and "getSystemChangelogs" not in texto, f.name
        # Contraprova: o leitor lê mesmo o sítio onde o CRM as consulta.
        assert "getSystemChangelogs" in (raiz / "pages" / "ConsultorDashboard.js").read_text(encoding="utf-8")

    def test_o_servico_de_listagem_nao_serve_um_portal_por_importacao(self):
        """Nenhum módulo dos portais importa o serviço do changelog."""
        from pathlib import Path

        backend = Path(__file__).resolve().parents[2]
        for nome in ("portal_status.py", "portal_auth.py", "partner_read.py", "partner_security.py"):
            f = backend / "services" / nome
            if f.exists():
                assert "changelog" not in f.read_text(encoding="utf-8").lower(), nome


# ====================================================================
# 2. GLOBAIS — sem fronteira de rede
# ====================================================================

class TestGlobais:
    def test_duas_redes_veem_exactamente_o_mesmo(self, mundo):
        cliente, _ = mundo
        power = cliente.get("/system/changelog?limit=20", headers=_bearer(_token_do_crm("u-ana"))).json()
        domus = cliente.get("/system/changelog?limit=20", headers=_bearer(_token_do_crm("u-bruno"))).json()
        assert power == domus
        assert [e["version"] for e in power] == ["2026-10-01", "2026-09-01", "2026-06-25"]

    @pytest.mark.asyncio
    async def test_a_consulta_nao_leva_nenhuma_condicao(self):
        """O filtro vazio é a propriedade: um filtro de rede aqui escondia novidades."""
        import services.changelog_service as servico

        capturado = {}

        class _Cursor:
            def sort(self, *a, **k):
                return self

            def limit(self, *a, **k):
                return self

            def __aiter__(self):
                async def vazio():
                    return
                    yield  # pragma: no cover

                return vazio()

        class _Coleccao:
            def find(self, filtro, projecao):
                capturado["filtro"] = filtro
                capturado["projecao"] = projecao
                return _Cursor()

        class _Bd:
            system_changelogs = _Coleccao()

        with patch.object(servico, "db", _Bd()):
            await servico.get_changelogs(limit=5)
        assert capturado["filtro"] == {}
        assert capturado["projecao"].get("is_premium") == 1


# ====================================================================
# 3. PREMIUM
# ====================================================================

class TestIsPremium:
    def test_a_listagem_traz_o_campo_e_o_antigo_nao_e_premium(self, mundo):
        cliente, _ = mundo
        por_versao = {
            e["version"]: e
            for e in cliente.get("/system/changelog?limit=20", headers=_bearer(_token_do_crm("u-ana"))).json()
        }
        assert por_versao["2026-10-01"]["is_premium"] is True
        assert por_versao["2026-09-01"]["is_premium"] is False
        assert por_versao["2026-06-25"]["is_premium"] is False  # sem o campo na base

    @pytest.mark.asyncio
    async def test_so_o_booleano_true_e_premium(self, fake_async_db):
        import services.changelog_service as servico

        fake_async_db.system_changelogs.docs.extend([
            {"_id": ObjectId(), "version": "a", "content_markdown": "x", "published_at": "2026-01-01", "is_premium": "true"},
            {"_id": ObjectId(), "version": "b", "content_markdown": "x", "published_at": "2026-01-02", "is_premium": 1},
        ])
        with patch.object(servico, "db", fake_async_db):
            lista = await servico.get_changelogs(limit=10)
        assert [e["is_premium"] for e in lista] == [False, False]

    @pytest.mark.parametrize("quem", ["u-ana", "u-adm", "u-ceo"])
    def test_so_o_master_marca(self, mundo, quem):
        cliente, bd = mundo
        resposta = cliente.patch(
            f"/system/changelog/{ID_NOVO}/premium", json={"is_premium": True}, headers=_bearer(_token_do_crm(quem)),
        )
        assert resposta.status_code == 403, quem
        assert next(d for d in bd.system_changelogs.docs if d["_id"] == ID_NOVO)["is_premium"] is False

    def test_o_master_marca_e_desmarca(self, mundo):
        cliente, bd = mundo
        cabecalho = _bearer(_token_do_crm("u-master"))
        r = cliente.patch(f"/system/changelog/{ID_NOVO}/premium", json={"is_premium": True}, headers=cabecalho)
        assert r.status_code == 200 and r.json() == {"id": str(ID_NOVO), "is_premium": True}
        assert next(d for d in bd.system_changelogs.docs if d["_id"] == ID_NOVO)["is_premium"] is True
        # E vê-se na listagem de quem não é Master.
        lista = cliente.get("/system/changelog?limit=20", headers=_bearer(_token_do_crm("u-bruno"))).json()
        assert next(e for e in lista if e["id"] == str(ID_NOVO))["is_premium"] is True

        r = cliente.patch(f"/system/changelog/{ID_NOVO}/premium", json={"is_premium": False}, headers=cabecalho)
        assert r.status_code == 200
        assert next(d for d in bd.system_changelogs.docs if d["_id"] == ID_NOVO)["is_premium"] is False

    def test_o_corpo_tem_de_ser_um_booleano(self, mundo):
        cliente, _ = mundo
        r = cliente.patch(
            f"/system/changelog/{ID_NOVO}/premium", json={"is_premium": "talvez"},
            headers=_bearer(_token_do_crm("u-master")),
        )
        assert r.status_code == 422

    @pytest.mark.parametrize("identificador", ["nao-e-um-objectid", ID_INEXISTENTE])
    def test_um_id_inexistente_ou_invalido_e_404(self, mundo, identificador):
        cliente, _ = mundo
        r = cliente.patch(
            f"/system/changelog/{identificador}/premium", json={"is_premium": True},
            headers=_bearer(_token_do_crm("u-master")),
        )
        assert r.status_code == 404

    def test_um_portal_nao_marca(self, mundo):
        from services.partner_security import create_partner_token

        cliente, _ = mundo
        r = cliente.patch(
            f"/system/changelog/{ID_NOVO}/premium", json={"is_premium": True},
            headers=_bearer(create_partner_token({"id": "p1", "token_epoch": 0})),
        )
        assert r.status_code == 401

    # ── na geração ────────────────────────────────────────────────
    def test_gerar_por_omissao_nao_e_premium(self, mundo):
        cliente, _ = mundo
        gerar = AsyncMock(return_value={"changelog": {"id": "x"}, "tokens_used": 1})
        with patch("services.changelog_api_generate.generate_changelog_ai", gerar):
            r = cliente.post("/system/changelog/generate-ai", json={}, headers=_bearer(_token_do_crm("u-adm")))
        assert r.status_code == 200
        assert gerar.await_args.kwargs["is_premium"] is False

    @pytest.mark.parametrize("quem", ["u-adm", "u-ceo"])
    def test_pedir_premium_na_geracao_so_o_master(self, mundo, quem):
        cliente, _ = mundo
        gerar = AsyncMock()
        with patch("services.changelog_api_generate.generate_changelog_ai", gerar):
            r = cliente.post(
                "/system/changelog/generate-ai", json={"is_premium": True}, headers=_bearer(_token_do_crm(quem)),
            )
        assert r.status_code == 403
        gerar.assert_not_awaited()  # nem sequer se paga a chamada à IA

    def test_o_master_gera_ja_como_premium(self, mundo):
        cliente, _ = mundo
        gerar = AsyncMock(return_value={"changelog": {"id": "x"}, "tokens_used": 1})
        with patch("services.changelog_api_generate.generate_changelog_ai", gerar):
            r = cliente.post(
                "/system/changelog/generate-ai", json={"is_premium": True}, headers=_bearer(_token_do_crm("u-master")),
            )
        assert r.status_code == 200
        assert gerar.await_args.kwargs["is_premium"] is True

    def test_o_modelo_nasce_nao_premium(self):
        from models.changelog import ChangelogEntry, ChangelogGenerateRequest, ChangelogResponse

        assert ChangelogEntry(version="v", content_markdown="x").is_premium is False
        assert ChangelogGenerateRequest().is_premium is False
        resposta = ChangelogResponse(id="1", version="v", content_markdown="x", published_at="2026-01-01T00:00:00Z", generated_by="ai")
        assert resposta.is_premium is False

    def test_a_entrada_gerada_guarda_o_campo(self):
        """A fonte da geração escreve `is_premium` no documento que insere."""
        from pathlib import Path

        fonte = (Path(__file__).resolve().parents[2] / "services" / "changelog_service.py").read_text(encoding="utf-8")
        trecho = fonte.split("doc = {")[-1].split("}")[0]
        assert '"is_premium": bool(is_premium)' in trecho
