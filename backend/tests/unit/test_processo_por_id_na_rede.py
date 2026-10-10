"""
Um processo pedido por ID tem de ser da rede de quem pede (adenda de RBAC).

O ACHADO
  As listagens isolavam por rede desde o Lote 4; o pedido por id não.
  `can_view_process` responde «sim» a qualquer staff, e nenhum dos ~40
  handlers de `routes/processes.py` perguntava a que rede o processo
  pertence — um consultor da Domus abria um processo da Power sabendo o id.

O QUE ESTE TESTE FAZ DE DIFERENTE
  A dependência lê `request.path_params`, que só existe quando o FastAPI
  resolve a rota. Testá-la chamando a função com um `Request` forjado provava
  a lógica e não a premissa. Aqui monta-se uma aplicação mínima com o MESMO
  `exigir_processo_no_ambito` num router real e pede-se por HTTP.
"""
from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

from services import process_scope_guard as guard
from services.auth import get_current_user
from tests.unit.helpers_tenant import (  # noqa: F401  (rede_de_omissao_incumbente é fixture)
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

BACKEND = Path(__file__).resolve().parents[2]

UTILIZADORES = {
    "ana": {"id": "u-ana", "role": "diretor", "effective_role": "diretor"},          # Power
    "bruno": {"id": "u-bruno", "role": "diretor", "effective_role": "diretor"},      # Domus
    "carla": {"id": "u-carla", "role": "consultor", "effective_role": "consultor"},  # Precision + Domus
    "master": {"id": "u-master", "role": "master", "effective_role": "master"},
    "admin_domus": {"id": "u-adm-domus", "role": "admin", "effective_role": "admin"},
}


@pytest.fixture
def cliente(fake_async_db, rede_de_omissao_incumbente):
    semear(fake_async_db)
    fake_async_db.user_company_roles.docs.append(
        {"user_id": "u-adm-domus", "company_id": "cmp-domus", "company_name": "Domus", "role": "admin"}
    )
    fake_async_db.processes.docs.append(
        {"id": "p-partilhado", "client_name": "Partilhado", "company_id": "cmp-power",
         "network_id": "grupo_power_precision", "partner_network_ids": ["grupo_domus"]}
    )

    atual = {"user": UTILIZADORES["ana"]}
    router = APIRouter(prefix="/processes", dependencies=[Depends(guard.exigir_processo_no_ambito)])

    @router.get("/{process_id}")
    async def detalhe(process_id: str):
        return {"id": process_id}

    @router.get("/{process_id}/timeline")
    async def timeline(process_id: str):
        return {"id": process_id, "timeline": []}

    @router.get("")
    async def listagem():
        return {"items": []}

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: atual["user"]

    with tenant_db(fake_async_db, guard):
        yield TestClient(app), atual


def _como(atual, nome):
    atual["user"] = UTILIZADORES[nome]


class TestOAtaque:
    def test_um_diretor_da_Domus_nao_abre_um_processo_da_Power(self, cliente):
        http, atual = cliente
        _como(atual, "bruno")
        r = http.get("/processes/p-power")
        assert r.status_code == 404
        assert r.json()["detail"] == "Processo não encontrado"

    def test_nem_as_sub_rotas(self, cliente):
        http, atual = cliente
        _como(atual, "bruno")
        assert http.get("/processes/p-power/timeline").status_code == 404

    def test_um_admin_da_Domus_e_local_e_tambem_nao_abre_a_Power(self, cliente):
        """Antes da adenda o Admin era global; agora é a sua empresa."""
        http, atual = cliente
        _como(atual, "admin_domus")
        assert http.get("/processes/p-power").status_code == 404

    def test_o_404_de_um_alheio_e_igual_ao_de_um_inexistente(self, cliente):
        http, atual = cliente
        _como(atual, "bruno")
        alheio = http.get("/processes/p-power")
        nada = http.get("/processes/nao-existe")
        # O inexistente passa a guarda e é o handler que responde — aqui o
        # handler de teste devolve 200, o que prova que a guarda não confirma
        # nem nega a existência de um id que não está na base de dados.
        assert nada.status_code == 200
        assert alheio.status_code == 404


class TestAContraprova:
    def test_o_diretor_da_Power_abre_o_da_Power(self, cliente):
        http, atual = cliente
        _como(atual, "ana")
        assert http.get("/processes/p-power").status_code == 200

    def test_o_admin_da_Domus_abre_os_da_Domus(self, cliente):
        http, atual = cliente
        _como(atual, "admin_domus")
        assert http.get("/processes/p-domus").status_code == 200

    def test_quem_trabalha_nas_duas_redes_abre_ambas(self, cliente):
        http, atual = cliente
        _como(atual, "carla")
        assert http.get("/processes/p-power").status_code == 200
        assert http.get("/processes/p-domus").status_code == 200

    def test_o_master_abre_qualquer_um(self, cliente):
        http, atual = cliente
        _como(atual, "master")
        for pid in ("p-power", "p-domus", "p-legado"):
            assert http.get(f"/processes/{pid}").status_code == 200

    def test_a_rede_convidada_de_um_processo_partilhado_abre_ao_parceiro(self, cliente):
        """Via Rápida: partilhar acrescenta quem VÊ."""
        http, atual = cliente
        _como(atual, "bruno")
        assert http.get("/processes/p-partilhado").status_code == 200

    def test_a_listagem_e_as_rotas_sem_id_nao_sao_tocadas(self, cliente):
        http, atual = cliente
        _como(atual, "bruno")
        assert http.get("/processes").status_code == 200

    def test_o_processo_legado_por_carimbar_so_abre_a_rede_de_omissao(self, cliente):
        http, atual = cliente
        _como(atual, "ana")
        assert http.get("/processes/p-legado").status_code == 200
        _como(atual, "bruno")
        assert http.get("/processes/p-legado").status_code == 404


class TestALigacaoAoRouterReal:
    def test_o_router_de_processos_tem_a_dependencia(self):
        """Sem isto o teste acima provava uma aplicação de brincar."""
        from routes.processes import router

        destinos = [d.dependency for d in router.dependencies]
        assert guard.exigir_processo_no_ambito in destinos

    def test_a_dependencia_nao_confirma_a_existencia_de_ids_inexistentes(self):
        fonte = (BACKEND / "services" / "process_scope_guard.py").read_text(encoding="utf-8")
        arvore = ast.parse(fonte)
        funcao = next(n for n in ast.walk(arvore) if isinstance(n, ast.AsyncFunctionDef))
        corpo = ast.unparse(funcao)
        assert "if not processo:" in corpo
        assert corpo.index("if not processo:") < corpo.index("resolve_tenant_scope")

    def test_o_master_passa_sem_ler_a_base_de_dados(self):
        fonte = (BACKEND / "services" / "process_scope_guard.py").read_text(encoding="utf-8")
        assert fonte.index("utilizador_e_global(user)") < fonte.index("db.processes.find_one")
