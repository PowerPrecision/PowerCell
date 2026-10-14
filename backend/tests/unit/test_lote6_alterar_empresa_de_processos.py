"""«Alterar Empresa» move PROCESSOS escolhidos, nunca o cliente (Lote 6, Out 2026).

Substitui o `test_lote4_transferir_cliente_cruzados.py`, que afirmava a regra antiga (mover o cliente
e arrastar tudo o que é dele, com um 409 para os processos «cruzados»). Com a escolha explícita dos
processos, o cruzado deixa de ser um problema a bloquear: move-se o que se escolhe, e só isso.
O contrato do 422 (`size` ≤ 100) também fica fixado aqui.
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from services.auth import hash_password
from tests.unit.helpers_tenant import (  # noqa: F401  (fixture)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

SENHA = "Segredo-Certo-9!"
MASTER = {"id": "u-master", "role": "master", "effective_role": "master", "name": "Master", "email": "m@p.pt"}
RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    import services.admin_helpers as helpers
    import services.client_company_transfer as mod
    import services.reauth_password as reauth

    bd = semear(fake_async_db)
    bd.users.docs.append({"id": "u-master", "email": MASTER["email"], "password": hash_password(SENHA), "is_active": True})
    cliente = next(c for c in bd.clients.docs if c["id"] == "c-power")
    cliente.update({"process_ids": ["p-power", "p-precision"], "company_name": "Power Real Estate"})
    processo = next(p for p in bd.processes.docs if p["id"] == "p-power")
    processo.update({"client_id": "c-power", "company_name": "Power Real Estate", "status": "em_analise"})
    # Do mesmo titular, mas carimbado na PRECISION (outra empresa da mesma rede).
    bd.processes.docs.append({
        "id": "p-precision", "client_id": "c-power", "client_name": "Silva da Power", "status": "em_analise",
        "company_id": "cmp-precision", "company_name": "Precision Crédito", "network_id": REDE_INCUMBENTE,
        "process_number": 77,
    })
    for colecao in ("tasks", "deadlines", "visits"):
        getattr(bd, colecao).docs.append({"id": f"{colecao}-b", "process_id": "p-precision",
                                           "network_id": REDE_INCUMBENTE, "company_id": "cmp-precision"})
    with tenant_db(bd, helpers, mod, reauth), patch("services.history.db", bd):
        yield bd, mod


def _corpo(mod, processos, empresa="cmp-domus"):
    return mod.TransferirClienteIn(company_id=empresa, process_ids=list(processos), password=SENHA)


def _processo(bd, id_):
    return next(p for p in bd.processes.docs if p["id"] == id_)


@pytest.mark.asyncio
class TestOQueNaoSeEscolheNaoSeMexe:
    async def test_mover_um_nao_arrasta_o_outro_do_mesmo_cliente(self, mundo):
        bd, mod = mundo
        await mod.run_transfer_client_company("c-power", _corpo(mod, ["p-power"]), MASTER)
        b = _processo(bd, "p-precision")
        assert (b["company_id"], b["network_id"]) == ("cmp-precision", REDE_INCUMBENTE)

    async def test_as_tarefas_prazos_e_visitas_do_nao_escolhido_nao_se_mexem(self, mundo):
        bd, mod = mundo
        await mod.run_transfer_client_company("c-power", _corpo(mod, ["p-power"]), MASTER)
        for colecao in ("tasks", "deadlines", "visits"):
            doc = next(d for d in getattr(bd, colecao).docs if d["id"] == f"{colecao}-b")
            assert doc["company_id"] == "cmp-precision", f"{colecao} do processo não escolhido foi carimbado"


@pytest.mark.asyncio
class TestOQueSeEscolheMove:
    async def test_um_processo_de_outra_empresa_da_ficha_move_se_quando_escolhido(self, mundo):
        """Já não há «cruzado que impede»: é uma escolha explícita do Master, sobre um processo do cliente."""
        bd, mod = mundo
        resposta = await mod.run_transfer_client_company("c-power", _corpo(mod, ["p-precision"]), MASTER)
        assert resposta["processos_transferidos"] == 1
        b = _processo(bd, "p-precision")
        assert (b["company_id"], b["network_id"]) == ("cmp-domus", REDE_DOMUS)
        for colecao in ("tasks", "deadlines", "visits"):
            doc = next(d for d in getattr(bd, colecao).docs if d["id"] == f"{colecao}-b")
            assert doc["company_id"] == "cmp-domus"

    async def test_varios_de_uma_vez(self, mundo):
        bd, mod = mundo
        resposta = await mod.run_transfer_client_company("c-power", _corpo(mod, ["p-power", "p-precision"]), MASTER)
        assert resposta["processos_transferidos"] == 2
        assert {_processo(bd, i)["network_id"] for i in ("p-power", "p-precision")} == {REDE_DOMUS}

    async def test_um_ja_no_destino_e_os_outros_movem_se(self, mundo):
        bd, mod = mundo
        resposta = await mod.run_transfer_client_company(
            "c-power", _corpo(mod, ["p-power", "p-precision"], empresa="cmp-precision"), MASTER,
        )
        assert resposta["processos_transferidos"] == 1
        assert [p["id"] for p in resposta["processos_ja_no_destino"]] == ["p-precision"]

    async def test_a_ficha_do_cliente_nunca_muda_de_empresa(self, mundo):
        bd, mod = mundo
        cliente = next(c for c in bd.clients.docs if c["id"] == "c-power")
        await mod.run_transfer_client_company("c-power", _corpo(mod, ["p-power", "p-precision"]), MASTER)
        assert (cliente["company_id"], cliente["network_id"]) == ("cmp-power", REDE_INCUMBENTE)


class TestORouterEOContratoDoTamanhoDaPagina:
    def test_o_preview_e_so_master(self):
        fonte = (RAIZ / "routes" / "clients_company_transfer.py").read_text(encoding="utf-8")
        trecho = fonte[fonte.index("transfer-company/preview"):]
        assert "require_roles([UserRole.MASTER])" in trecho

    def test_o_frontend_nunca_pede_mais_do_que_o_maximo_da_pagina_de_empresas(self):
        """O 422: o diálogo pedia `size: 200` a uma rota com `le=100`."""
        rota = (RAIZ / "routes" / "companies_crud.py").read_text(encoding="utf-8")
        maximo = int(re.search(r"size: int = Query\(\d+, ge=1, le=(\d+)\)", rota).group(1))
        front = RAIZ.parent / "frontend" / "src"
        for ficheiro in ("components/clients/TransferirClienteDialog.jsx", "services/api.js"):
            texto = (front / ficheiro).read_text(encoding="utf-8")
            for pedido in re.findall(r"getCompanies\([^)]*size:\s*(\d+)", texto):
                assert int(pedido) <= maximo, f"{ficheiro} pede size={pedido} (máximo {maximo})"
