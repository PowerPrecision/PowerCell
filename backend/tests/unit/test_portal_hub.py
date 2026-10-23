"""O Hub do Portal do Cliente (D-42): a identidade é o CLIENTE, o contexto é o PROCESSO.

O que estes testes protegem:
  * o token do Hub é ancorado ao cliente (`sub = client_id`) e não abre mais nada — nem rotas de
    processo, nem o WebSocket, nem staff; e um token de processo não abre o Hub;
  * escolher um processo devolve o token de sempre DESSE processo, só se for do cliente e se o token
    do Hub o cobrir (`nets`); tudo o resto é 404, igual ao de «não existe»;
  * um link/verificação (redes restritas) não dá a porta para o processo de outra empresa;
  * só se oferecem processos activos; todos inactivos é o 403 do Portal inactivo;
  * o login e o link curto acrescentam o Hub SEM mudar o que já devolviam.

Os tokens são emitidos pelos produtores REAIS e as guardas testadas são as reais. O único duplo é a
base de dados em memória.
"""
from __future__ import annotations

from unittest.mock import patch

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from services import portal_estado, portal_hub, portal_security, workflow_phases
from services.portal_security import (
    create_access_code_session_token,
    create_client_magic_token,
    create_verified_session_token,
    get_current_client,
)

REDE_POWER = "grupo_power_precision"
REDE_DOMUS = "grupo_domus"

FASES = [
    {"name": "clientes_espera", "label": "Clientes em Espera", "order": 1, "is_active": True},
    {"name": "fase_bancaria", "label": "Fase Bancária", "order": 2, "is_active": True},
    {"name": "concluidos", "label": "Concluídos", "order": 3, "is_active": False},
]


def _cred(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.fixture
async def mundo(fake_async_db, monkeypatch):
    monkeypatch.setenv("TENANT_DEFAULT_NETWORK_ID", REDE_POWER)
    for fase in FASES:
        await fake_async_db.workflow_statuses.insert_one(dict(fase))
    await fake_async_db.clients.insert_many([
        {"id": "c-1", "nome": "Joana"},
        {"id": "c-2", "nome": "Outra Pessoa"},
    ])
    await fake_async_db.processes.insert_many([
        {"id": "p-power", "client_id": "c-1", "process_number": 11, "process_type": "credito_habitacao",
         "status": "fase_bancaria", "network_id": REDE_POWER, "company_id": "cmp-power",
         "company_name": "Power Real Estate", "created_at": "2026-01-01"},
        {"id": "p-domus", "client_id": "c-1", "process_number": 22, "process_type": "credito_pessoal",
         "status": "clientes_espera", "network_id": REDE_DOMUS, "company_id": "cmp-domus",
         "created_at": "2026-02-01"},
        # 2.º titular de um processo de outra pessoa
        {"id": "p-segundo", "client_id": "c-2", "second_client_id": "c-1", "process_number": 33,
         "process_type": "credito_habitacao", "status": "clientes_espera", "network_id": REDE_POWER,
         "company_name": "Power Real Estate", "created_at": "2026-03-01"},
        {"id": "p-fechado", "client_id": "c-1", "process_number": 44, "status": "concluidos",
         "network_id": REDE_POWER, "created_at": "2025-01-01"},
        {"id": "p-eliminado", "client_id": "c-1", "status": "clientes_espera", "is_deleted": True,
         "network_id": REDE_POWER},
        {"id": "p-alheio", "client_id": "c-2", "process_number": 55, "status": "clientes_espera",
         "network_id": REDE_POWER},
    ])
    await fake_async_db.companies.insert_one({"id": "cmp-domus", "name": "Domus"})
    with patch.object(portal_hub, "db", fake_async_db), \
            patch.object(portal_security, "db", fake_async_db), \
            patch.object(workflow_phases, "db", fake_async_db):
        workflow_phases.invalidar_cache_de_fases()
        yield fake_async_db
        workflow_phases.invalidar_cache_de_fases()


async def _hub(token):
    return await portal_hub.get_current_hub(_cred(token))


# ─────────────────────────────────────────────────────────────────────
# O token
# ─────────────────────────────────────────────────────────────────────
class TestOToken:
    def test_e_ancorado_ao_cliente(self):
        from services.portal_jwt_secret import descodificar_token_do_portal

        payload = descodificar_token_do_portal(portal_hub.criar_token_do_hub("c-1"))
        assert (payload["sub"], payload["client_id"], payload["type"], payload["role"]) == (
            "c-1", "c-1", "client_hub", "client_portal",
        )
        assert "nets" not in payload, "sem restrição = todas as redes do cliente"

    def test_dura_o_mesmo_que_uma_sessao_interactiva(self):
        from services.portal_jwt_secret import descodificar_token_do_portal

        p = descodificar_token_do_portal(portal_hub.criar_token_do_hub("c-1"))
        assert p["exp"] - p["iat"] == portal_security.PORTAL_SESSION_VALIDITY_HOURS * 3600

    def test_as_redes_sao_normalizadas_e_sem_repetidos(self):
        from services.portal_jwt_secret import descodificar_token_do_portal

        p = descodificar_token_do_portal(
            portal_hub.criar_token_do_hub("c-1", redes_permitidas=[" B ", "A", "A", "", None]),
        )
        assert p["nets"] == ["A", "B"]

    @pytest.mark.parametrize("valor,esperado", [
        (None, "ausente"), (["A"], {"A"}), ([], set()), ("A", set()), ({"A": 1}, set()), (0, set()),
    ])
    def test_uma_claim_estragada_fecha_nunca_abre(self, valor, esperado):
        payload = {} if valor is None else {"nets": valor}
        resultado = portal_hub.redes_do_token(payload)
        assert (resultado is None) if esperado == "ausente" else (resultado == esperado)


# ─────────────────────────────────────────────────────────────────────
# Os tipos de token não se misturam
# ─────────────────────────────────────────────────────────────────────
class TestOsTiposNaoSeMisturam:
    @pytest.mark.parametrize("criar", [
        lambda: create_verified_session_token("p-power", "c-1"),
        lambda: create_access_code_session_token("p-power", "c-1"),
        lambda: create_client_magic_token("p-power"),
    ])
    async def test_um_token_de_processo_nao_abre_o_hub(self, mundo, criar):
        with pytest.raises(HTTPException) as exc:
            await _hub(criar())
        assert exc.value.status_code == 403

    async def test_o_token_do_hub_nao_abre_nenhuma_rota_de_processo(self, mundo):
        with pytest.raises(HTTPException) as exc:
            await get_current_client(_cred(portal_hub.criar_token_do_hub("c-1")))
        assert exc.value.status_code == 403
        assert "tipo incorreto" in exc.value.detail

    async def test_o_hub_nao_aceita_um_token_de_staff(self, mundo):
        from config import JWT_ALGORITHM, JWT_SECRET

        staff = jwt.encode({"sub": "u-1", "role": "admin", "type": "access"}, JWT_SECRET, algorithm=JWT_ALGORITHM)
        with pytest.raises(HTTPException) as exc:
            await _hub(staff)
        assert exc.value.status_code in (401, 403)

    async def test_sem_token_401(self, mundo):
        with pytest.raises(HTTPException) as exc:
            await portal_hub.get_current_hub(None)
        assert exc.value.status_code == 401

    async def test_token_adulterado_401(self, mundo):
        with pytest.raises(HTTPException) as exc:
            await _hub(portal_hub.criar_token_do_hub("c-1") + "x")
        assert exc.value.status_code == 401

    async def test_token_expirado_401(self, mundo):
        from datetime import datetime, timedelta, timezone

        from config import JWT_ALGORITHM
        from services.portal_jwt_secret import segredo_de_assinatura

        velho = jwt.encode(
            {"sub": "c-1", "client_id": "c-1", "role": "client_portal", "type": "client_hub",
             "exp": datetime.now(timezone.utc) - timedelta(seconds=5)},
            segredo_de_assinatura(), algorithm=JWT_ALGORITHM,
        )
        with pytest.raises(HTTPException) as exc:
            await _hub(velho)
        assert exc.value.status_code == 401

    async def test_o_sub_tem_de_coincidir_com_o_client_id(self, mundo):
        from datetime import datetime, timedelta, timezone

        from config import JWT_ALGORITHM
        from services.portal_jwt_secret import segredo_de_assinatura

        torto = jwt.encode(
            {"sub": "c-1", "client_id": "c-2", "role": "client_portal", "type": "client_hub",
             "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            segredo_de_assinatura(), algorithm=JWT_ALGORITHM,
        )
        with pytest.raises(HTTPException) as exc:
            await _hub(torto)
        assert exc.value.status_code == 401

    async def test_um_cliente_eliminado_ou_inexistente_perde_o_hub(self, mundo):
        with pytest.raises(HTTPException) as exc:
            await _hub(portal_hub.criar_token_do_hub("nao-existe"))
        assert exc.value.status_code == 401
        await mundo.clients.update_one({"id": "c-1"}, {"$set": {"is_deleted": True}})
        with pytest.raises(HTTPException) as exc:
            await _hub(portal_hub.criar_token_do_hub("c-1"))
        assert exc.value.status_code == 401

    def test_o_hub_nao_e_um_tipo_do_portal_para_o_websocket_nem_serve_ao_staff(self):
        from services.ws_client_identity import (
            TIPOS_DO_PORTAL,
            TIPOS_ESTRANHOS_AO_STAFF,
            tipo_de_token_e_de_staff,
            tipo_de_token_e_do_portal,
        )

        assert portal_hub.TIPO_DO_HUB not in TIPOS_DO_PORTAL
        assert tipo_de_token_e_do_portal(portal_hub.TIPO_DO_HUB) is False
        assert tipo_de_token_e_de_staff(portal_hub.TIPO_DO_HUB) is False
        assert portal_hub.TIPO_DO_HUB in TIPOS_ESTRANHOS_AO_STAFF


# ─────────────────────────────────────────────────────────────────────
# Listar
# ─────────────────────────────────────────────────────────────────────
class TestListar:
    async def test_lista_os_processos_activos_das_duas_empresas(self, mundo):
        hub = await _hub(portal_hub.criar_token_do_hub("c-1"))
        r = await portal_hub.listar_para_o_hub(hub)
        assert [p["id"] for p in r["processos"]] == ["p-segundo", "p-domus", "p-power"], (
            "do mais recente para o mais antigo; o fechado, o eliminado e o alheio ficam de fora"
        )
        assert r["cliente_nome"] == "Joana"

    async def test_o_dto_e_o_que_o_cliente_precisa_e_nada_mais(self, mundo):
        hub = await _hub(portal_hub.criar_token_do_hub("c-1"))
        r = await portal_hub.listar_para_o_hub(hub)
        domus = next(p for p in r["processos"] if p["id"] == "p-domus")
        power = next(p for p in r["processos"] if p["id"] == "p-power")
        assert power == {
            "id": "p-power", "numero": 11, "tipo": "credito_habitacao", "tipo_rotulo": "Crédito Habitação",
            "empresa": "Power Real Estate", "estado_rotulo": "Fase Bancária",
        }
        assert domus["empresa"] == "Domus", "sem nome no carimbo vai buscar-se à empresa"
        assert domus["tipo_rotulo"] == "Crédito Pessoal"

    async def test_o_segundo_titular_ve_o_processo_em_que_e_segundo(self, mundo):
        hub = await _hub(portal_hub.criar_token_do_hub("c-1"))
        r = await portal_hub.listar_para_o_hub(hub)
        assert "p-segundo" in {p["id"] for p in r["processos"]}

    async def test_nunca_lista_processos_de_outra_pessoa(self, mundo):
        hub = await _hub(portal_hub.criar_token_do_hub("c-1"))
        ids = {p["id"] for p in (await portal_hub.listar_para_o_hub(hub))["processos"]}
        assert "p-alheio" not in ids

    async def test_um_token_restrito_so_ve_a_sua_rede(self, mundo):
        hub = await _hub(portal_hub.criar_token_do_hub("c-1", redes_permitidas=[REDE_POWER]))
        ids = {p["id"] for p in (await portal_hub.listar_para_o_hub(hub))["processos"]}
        assert ids == {"p-power", "p-segundo"}

    async def test_um_token_com_redes_vazias_nao_ve_nada(self, mundo):
        hub = await _hub(portal_hub.criar_token_do_hub("c-1", redes_permitidas=[]))
        assert (await portal_hub.listar_para_o_hub(hub))["processos"] == []

    async def test_todos_os_processos_inactivos_e_o_403_do_portal_inactivo(self, mundo):
        await mundo.processes.update_many({"client_id": "c-1"}, {"$set": {"status": "concluidos"}})
        await mundo.processes.update_one({"id": "p-segundo"}, {"$set": {"status": "concluidos"}})
        hub = await _hub(portal_hub.criar_token_do_hub("c-1"))
        with pytest.raises(HTTPException) as exc:
            await portal_hub.listar_para_o_hub(hub)
        assert exc.value.status_code == 403
        assert exc.value.detail["codigo"] == portal_estado.CODIGO_PORTAL_INATIVO

    async def test_sem_nenhum_processo_a_lista_e_vazia_e_nao_e_um_erro(self, mundo):
        await mundo.clients.insert_one({"id": "c-novo", "nome": "Novo"})
        hub = await _hub(portal_hub.criar_token_do_hub("c-novo"))
        assert (await portal_hub.listar_para_o_hub(hub))["processos"] == []

    async def test_a_pista_de_entrada_vai_na_resposta(self, mundo):
        hub = await _hub(portal_hub.criar_token_do_hub("c-1", processo_de_entrada="p-power"))
        assert (await portal_hub.listar_para_o_hub(hub))["entrada"] == "p-power"


# ─────────────────────────────────────────────────────────────────────
# Escolher
# ─────────────────────────────────────────────────────────────────────
class TestEscolher:
    async def test_devolve_o_token_de_processo_desse_processo(self, mundo):
        from services.portal_jwt_secret import descodificar_token_do_portal

        hub = await _hub(portal_hub.criar_token_do_hub("c-1"))
        r = await portal_hub.seleccionar_processo(hub, "p-domus")
        payload = descodificar_token_do_portal(r["token"])
        assert (payload["sub"], payload["client_id"], payload["type"]) == ("p-domus", "c-1", "access_code_session")
        assert r["process_id"] == "p-domus" and r["processo"]["empresa"] == "Domus"

    async def test_o_token_escolhido_abre_so_esse_processo(self, mundo):
        """O contexto adapta-se: a rota de processo vê o processo escolhido e nenhum outro."""
        hub = await _hub(portal_hub.criar_token_do_hub("c-1"))
        r = await portal_hub.seleccionar_processo(hub, "p-domus")
        contexto = await get_current_client(_cred(r["token"]))
        assert contexto["process_id"] == "p-domus"
        assert contexto["process"]["id"] == "p-domus"

    async def test_e_possivel_trocar_de_processo_com_o_mesmo_hub(self, mundo):
        hub = await _hub(portal_hub.criar_token_do_hub("c-1"))
        a = await portal_hub.seleccionar_processo(hub, "p-power")
        b = await portal_hub.seleccionar_processo(hub, "p-domus")
        assert (await get_current_client(_cred(a["token"])))["process_id"] == "p-power"
        assert (await get_current_client(_cred(b["token"])))["process_id"] == "p-domus"

    @pytest.mark.parametrize("alvo", ["p-alheio", "nao-existe", "", "p-eliminado"])
    async def test_um_processo_que_nao_e_do_cliente_e_404(self, mundo, alvo):
        hub = await _hub(portal_hub.criar_token_do_hub("c-1"))
        with pytest.raises(HTTPException) as exc:
            await portal_hub.seleccionar_processo(hub, alvo)
        assert exc.value.status_code == 404
        assert exc.value.detail == "Processo não encontrado."

    async def test_o_404_de_um_alheio_e_igual_ao_de_um_inexistente(self, mundo):
        hub = await _hub(portal_hub.criar_token_do_hub("c-1"))
        erros = []
        for alvo in ("p-alheio", "nao-existe"):
            with pytest.raises(HTTPException) as exc:
                await portal_hub.seleccionar_processo(hub, alvo)
            erros.append((exc.value.status_code, exc.value.detail))
        assert erros[0] == erros[1]

    async def test_um_token_restrito_nao_escolhe_o_processo_de_outra_rede(self, mundo):
        """A equipa da Power tem um link do cliente: não ganha a porta para o processo da Domus."""
        hub = await _hub(portal_hub.criar_token_do_hub("c-1", redes_permitidas=[REDE_POWER]))
        with pytest.raises(HTTPException) as exc:
            await portal_hub.seleccionar_processo(hub, "p-domus")
        assert exc.value.status_code == 404
        # e o que é da sua rede continua a abrir
        assert (await portal_hub.seleccionar_processo(hub, "p-power"))["process_id"] == "p-power"

    async def test_um_processo_inactivo_do_cliente_da_o_aviso_do_portal_inactivo(self, mundo):
        hub = await _hub(portal_hub.criar_token_do_hub("c-1"))
        with pytest.raises(HTTPException) as exc:
            await portal_hub.seleccionar_processo(hub, "p-fechado")
        assert exc.value.status_code == 403
        assert exc.value.detail["codigo"] == portal_estado.CODIGO_PORTAL_INATIVO

    async def test_o_processo_que_passa_a_inactivo_depois_de_escolhido_continua_bloqueado(self, mundo):
        hub = await _hub(portal_hub.criar_token_do_hub("c-1"))
        r = await portal_hub.seleccionar_processo(hub, "p-power")
        await mundo.processes.update_one({"id": "p-power"}, {"$set": {"status": "concluidos"}})
        with pytest.raises(HTTPException) as exc:
            await get_current_client(_cred(r["token"]))
        assert exc.value.status_code == 403

    async def test_a_posse_vem_da_mesma_funcao_que_a_listagem(self, mundo):
        import inspect

        fonte = inspect.getsource(portal_hub.seleccionar_processo)
        assert "processos_do_cliente" in fonte
        assert "db.processes" not in fonte, "uma segunda regra de posse divergiria da listagem"


# ─────────────────────────────────────────────────────────────────────
# Acrescentar o Hub a uma resposta de login
# ─────────────────────────────────────────────────────────────────────
class TestAnexarHub:
    async def test_acrescenta_o_token_e_os_processos_sem_mexer_no_resto(self, mundo):
        base = {"token": "t", "client_id": "c-1", "process_id": "p-power"}
        r = await portal_hub.anexar_hub(dict(base), "c-1", redes_permitidas=None)
        assert {k: r[k] for k in base} == base
        assert {p["id"] for p in r["processos"]} == {"p-power", "p-domus", "p-segundo"}
        assert r["hub_token"]

    async def test_sem_processos_activos_nao_ha_hub(self, mundo):
        await mundo.clients.insert_one({"id": "c-novo", "nome": "Novo"})
        r = await portal_hub.anexar_hub({"token": "t"}, "c-novo", redes_permitidas=None)
        assert r["processos"] == [] and "hub_token" not in r

    async def test_o_hub_do_link_fica_restrito_a_rede_do_processo(self, mundo):
        from services.portal_jwt_secret import descodificar_token_do_portal

        r = await portal_hub.anexar_hub({"token": "t"}, "c-1", redes_permitidas=[REDE_POWER], processo_de_entrada="p-power")
        assert {p["id"] for p in r["processos"]} == {"p-power", "p-segundo"}
        payload = descodificar_token_do_portal(r["hub_token"])
        assert payload["nets"] == [REDE_POWER] and payload["entrada"] == "p-power"

    async def test_nunca_levanta_um_soluco_do_hub_nao_deixa_o_cliente_a_porta(self, mundo):
        async def rebenta(*_a, **_k):
            raise RuntimeError("base de dados em baixo")

        with patch.object(portal_hub, "processos_do_cliente", rebenta):
            r = await portal_hub.anexar_hub({"token": "t", "x": 1}, "c-1", redes_permitidas=None)
        assert r == {"token": "t", "x": 1, "processos": []}

    async def test_sem_client_id_devolve_a_resposta_com_a_lista_vazia(self, mundo):
        assert await portal_hub.anexar_hub({"token": "t"}, None, redes_permitidas=None) == {"token": "t", "processos": []}


# ─────────────────────────────────────────────────────────────────────
# As rotas
# ─────────────────────────────────────────────────────────────────────
class TestAsRotas:
    def _handlers(self):
        import ast
        from pathlib import Path

        fonte = (Path(__file__).resolve().parents[2] / "routes" / "portal.py").read_text(encoding="utf-8")
        arvore = ast.parse(fonte)
        return {
            n.name: (n, ast.get_source_segment(fonte, n) or "")
            for n in ast.walk(arvore)
            if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
        }

    def test_as_duas_rotas_do_hub_usam_a_dependencia_do_hub_e_nao_a_de_processo(self):
        handlers = self._handlers()
        for nome in ("portal_hub_list", "portal_hub_select"):
            _, fonte = handlers[nome]
            assert "get_current_hub" in fonte, nome
            assert "get_current_client" not in fonte, nome

    def test_nenhuma_rota_de_processo_aceita_o_token_do_hub(self):
        """O inventário por rota: tirando as duas do Hub e as que emitem tokens / são de staff, todas
        passam por `get_current_client`, que recusa o tipo do Hub."""
        handlers = self._handlers()
        usam_hub = {n for n, (_, f) in handlers.items() if "get_current_hub" in f}
        assert usam_hub == {"portal_hub_list", "portal_hub_select"}

    def test_o_post_do_hub_tem_limite_e_response_e_o_get_tambem(self):
        import ast

        handlers = self._handlers()
        for nome in ("portal_hub_list", "portal_hub_select"):
            no, _ = handlers[nome]
            decoradores = [ast.unparse(d) for d in no.decorator_list]
            assert any("limiter.limit" in d for d in decoradores), nome
            argumentos = {a.arg for a in no.args.args}
            assert {"request", "response"} <= argumentos, f"{nome}: sem `response: Response` o SUCESSO devolve 500"

    def test_o_corpo_do_select_recusa_campos_extra_e_ids_vazios(self):
        from pydantic import ValidationError

        from routes.portal import HubSelectRequest

        assert HubSelectRequest(process_id="p-1").process_id == "p-1"
        for mau in ({}, {"process_id": ""}, {"process_id": "p-1", "client_id": "c-2"}, {"process_id": "x" * 65}):
            with pytest.raises(ValidationError):
                HubSelectRequest(**mau)

    async def test_o_limite_responde_no_sucesso_com_os_cabecalhos(self, mundo, limiter_de_producao_ligado):
        """Um `Limiter` REAL: o sucesso do GET não pode rebentar por falta de `response: Response`."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import routes.portal as rp

        app = FastAPI()
        app.include_router(rp.router)
        with TestClient(app) as http:
            token = portal_hub.criar_token_do_hub("c-1")
            r = http.get("/portal/hub", headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200, r.text
            assert "x-ratelimit-limit" in {k.lower() for k in r.headers}, "o limiter REAL esteve ligado"
            assert {p["id"] for p in r.json()["processos"]} == {"p-power", "p-domus", "p-segundo"}
            r = http.post("/portal/hub/select", json={"process_id": "p-domus"}, headers={"Authorization": f"Bearer {token}"})
            assert r.status_code == 200, r.text
            assert r.json()["process_id"] == "p-domus"

    async def test_um_token_de_processo_nao_abre_o_hub_por_http(self, mundo):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import routes.portal as rp

        app = FastAPI()
        app.include_router(rp.router)
        with TestClient(app) as http:
            token = create_access_code_session_token("p-power", "c-1")
            assert http.get("/portal/hub", headers={"Authorization": f"Bearer {token}"}).status_code == 403
            assert http.post("/portal/hub/select", json={"process_id": "p-power"},
                             headers={"Authorization": f"Bearer {token}"}).status_code == 403
            assert http.get("/portal/hub").status_code == 401

    async def test_o_token_do_hub_nao_abre_as_rotas_de_processo_por_http(self, mundo):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import routes.portal as rp

        app = FastAPI()
        app.include_router(rp.router)
        with TestClient(app) as http:
            token = portal_hub.criar_token_do_hub("c-1")
            for caminho in ("/portal/status", "/portal/me", "/portal/messages", "/portal/events", "/portal/visits"):
                assert http.get(caminho, headers={"Authorization": f"Bearer {token}"}).status_code == 403, caminho


# ─────────────────────────────────────────────────────────────────────
# O login, o link curto e a verificação acrescentam o Hub sem mudar o resto
# ─────────────────────────────────────────────────────────────────────
class TestOsLoginsAcrescentamOHub:
    async def _correr_login(self, mundo, email="joana@exemplo.pt", codigo="ABC123"):
        import json

        import services.portal_auth as pa

        await mundo.clients.update_one(
            {"id": "c-1"},
            {"$set": {"contacto": {"email": email}, "portal_access_code": "ABC-123",
                      "process_ids": ["p-power", "p-domus", "p-segundo", "p-fechado"]}},
        )
        with patch.object(pa, "db", mundo), patch.object(portal_security, "db", mundo):
            r = await pa.run_portal_login(pa.PortalLoginRequest(email=email, access_code=codigo))
        return json.loads(r.body)

    async def test_o_login_devolve_o_hub_e_continua_a_devolver_o_token_de_processo(self, mundo):
        from services.portal_jwt_secret import descodificar_token_do_portal

        r = await self._correr_login(mundo)
        # o que já devolvia
        assert r["token_type"] == "access_code_session" and r["client_id"] == "c-1" and r["process_id"]
        assert descodificar_token_do_portal(r["token"])["sub"] == r["process_id"]
        # o que ganhou
        assert {p["id"] for p in r["processos"]} == {"p-power", "p-domus", "p-segundo"}
        hub = descodificar_token_do_portal(r["hub_token"])
        assert (hub["type"], hub["sub"]) == ("client_hub", "c-1") and "nets" not in hub

    async def test_o_login_por_codigo_cobre_todas_as_redes(self, mundo):
        r = await self._correr_login(mundo)
        assert {"p-power", "p-domus"} <= {p["id"] for p in r["processos"]}

    async def test_com_um_unico_processo_activo_o_hub_tem_uma_lista_de_um(self, mundo):
        await mundo.processes.update_many({"id": {"$in": ["p-domus", "p-segundo"]}}, {"$set": {"status": "concluidos"}})
        r = await self._correr_login(mundo)
        assert [p["id"] for p in r["processos"]] == ["p-power"]

    async def test_o_link_curto_restringe_o_hub_a_rede_do_processo_do_link(self, mundo):
        import services.portal_auth as pa
        from services.portal_jwt_secret import descodificar_token_do_portal

        link = create_client_magic_token("p-power")
        await mundo.portal_tokens.insert_one({"short_id": "abc123", "jwt_token": link, "process_id": "p-power", "client_id": "c-1"})
        with patch.object(pa, "db", mundo):
            r = await pa.run_resolve_portal_token("abc123")
        assert r["token"] == link and r["process_id"] == "p-power" and r["client_id"] == "c-1"
        assert {p["id"] for p in r["processos"]} == {"p-power", "p-segundo"}, "a Domus fica de fora"
        assert descodificar_token_do_portal(r["hub_token"])["nets"] == [REDE_POWER]

    async def test_a_verificacao_por_nif_restringe_o_hub_a_rede_do_processo(self, mundo):
        import json

        import services.portal_auth as pa
        from services.portal_jwt_secret import descodificar_token_do_portal

        async def verifica(**_k):
            return {"client_id": "c-1", "process_id": "p-power", "client_name": "Joana", "process_number": 11}

        with patch.object(pa, "db", mundo), patch.object(pa, "verify_client_credentials", verifica):
            r = json.loads((await pa.run_verify_portal_login("c-1", {"nif": "285739461", "process_number": 11})).body)
        assert {p["id"] for p in r["processos"]} == {"p-power", "p-segundo"}
        assert descodificar_token_do_portal(r["hub_token"])["nets"] == [REDE_POWER]

    async def test_a_personificacao_do_staff_nao_traz_hub(self, mundo):
        """«Ver como cliente» vê DESSE processo, nunca os das outras empresas."""
        import inspect

        import services.portal_auth as pa

        fonte = inspect.getsource(pa.run_impersonate_client_portal)
        assert "anexar_hub" not in fonte and "hub_token" not in fonte

    async def test_o_hub_e_um_acrescento_um_soluco_nao_derruba_o_login(self, mundo):
        async def rebenta(*_a, **_k):
            raise RuntimeError("hub em baixo")

        with patch.object(portal_hub, "processos_do_cliente", rebenta):
            r = await self._correr_login(mundo)
        assert r["token"] and r["processos"] == [] and "hub_token" not in r
