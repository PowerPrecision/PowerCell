"""
Lote 4, ponto 5 (Out 2026) — «Alterar Empresa» e os processos de OUTRA empresa.

O RISCO
  O cliente é titular do Processo A (empresa de origem) e do Processo B (carimbado noutra
  empresa). A transferência cega carimbava os dois com a empresa de destino: B, que pertence a
  outra empresa, mudava de dono, e o histórico (carimbo, tarefas, prazos, visitas) dela ficava
  corrompido.

A REGRA
  * só se movem os processos que SEGUEM o cliente (carimbo = empresa de origem, ou por carimbar);
  * um processo cruzado ACTIVO impede a transferência (409), e nada se escreve;
  * um cruzado já terminado fica onde está e é anunciado (`processos_mantidos`);
  * o preview diz tudo isto antes de pedir a password.
O contrato do 422 (`size` ≤ 100) também fica fixado aqui.
"""
from __future__ import annotations

import re
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

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
    # O Processo B: do mesmo titular, mas carimbado na PRECISION (outra empresa da mesma rede).
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


def _corpo(mod, empresa="cmp-domus", password=SENHA):
    return mod.TransferirClienteIn(company_id=empresa, password=password)


def _processo(bd, id_):
    return next(p for p in bd.processes.docs if p["id"] == id_)


@pytest.mark.asyncio
class TestUmProcessoActivoNoutraEmpresaImpedeATransferencia:
    async def test_a_exploracao_a_transferencia_cega_corrompia_o_processo_B(self, mundo):
        bd, mod = mundo
        with pytest.raises(HTTPException) as erro:
            await mod.run_transfer_client_company("c-power", _corpo(mod), MASTER)
        assert erro.value.status_code == 409

    async def test_e_nada_foi_escrito(self, mundo):
        bd, mod = mundo
        antes = [dict(p) for p in bd.processes.docs] + [dict(c) for c in bd.clients.docs]
        with pytest.raises(HTTPException):
            await mod.run_transfer_client_company("c-power", _corpo(mod), MASTER)
        depois = [dict(p) for p in bd.processes.docs] + [dict(c) for c in bd.clients.docs]
        assert antes == depois, "a transferência escreveu antes de recusar"
        assert not [a for a in bd.audit_logs.docs if "transferred" in str(a.get("action"))]

    async def test_a_password_continua_a_vir_primeiro(self, mundo):
        """Sem a password certa não se diz que há processos a impedir (403, não 409)."""
        bd, mod = mundo
        with pytest.raises(HTTPException) as erro:
            await mod.run_transfer_client_company("c-power", _corpo(mod, password="errada"), MASTER)
        assert erro.value.status_code == 403


@pytest.mark.asyncio
class TestUmCruzadoTerminadoFicaOndeEsta:
    async def test_move_so_o_que_segue_o_cliente_e_anuncia_o_que_manteve(self, mundo):
        bd, mod = mundo
        _processo(bd, "p-precision")["status"] = "concluido"
        resposta = await mod.run_transfer_client_company("c-power", _corpo(mod), MASTER)

        assert resposta["transferido"] is True
        assert resposta["processos_transferidos"] == 1
        assert [p["id"] for p in resposta["processos_mantidos"]] == ["p-precision"]
        assert _processo(bd, "p-power")["company_id"] == "cmp-domus"
        b = _processo(bd, "p-precision")
        assert b["company_id"] == "cmp-precision" and b["network_id"] == REDE_INCUMBENTE, \
            "o processo da Precision mudou de dono"

    async def test_as_tarefas_prazos_e_visitas_do_cruzado_nao_se_mexem(self, mundo):
        bd, mod = mundo
        _processo(bd, "p-precision")["status"] = "concluido"
        await mod.run_transfer_client_company("c-power", _corpo(mod), MASTER)
        for colecao in ("tasks", "deadlines", "visits"):
            doc = next(d for d in getattr(bd, colecao).docs if d["id"] == f"{colecao}-b")
            assert doc["company_id"] == "cmp-precision", f"{colecao} do processo cruzado foi carimbado"

    async def test_um_cruzado_eliminado_tambem_nao_impede(self, mundo):
        bd, mod = mundo
        _processo(bd, "p-precision")["is_deleted"] = True
        resposta = await mod.run_transfer_client_company("c-power", _corpo(mod), MASTER)
        assert resposta["transferido"] is True


@pytest.mark.asyncio
class TestOCasoNormalNaoMudou:
    async def test_sem_cruzados_move_tudo(self, mundo):
        bd, mod = mundo
        bd.processes.docs[:] = [p for p in bd.processes.docs if p["id"] != "p-precision"]
        resposta = await mod.run_transfer_client_company("c-power", _corpo(mod), MASTER)
        assert resposta["processos_transferidos"] == 1 and resposta["processos_mantidos"] == []

    async def test_cliente_da_pool_sem_carimbo_leva_todos_os_processos(self, mundo):
        """Sem carimbo não há «outra empresa»: o activo da Precision NÃO o bloqueia."""
        bd, mod = mundo
        cliente = next(c for c in bd.clients.docs if c["id"] == "c-power")
        for campo in ("company_id", "company_name", "network_id", "company"):
            cliente.pop(campo, None)
        resposta = await mod.run_transfer_client_company("c-power", _corpo(mod), MASTER)
        assert resposta["processos_transferidos"] == 2
        assert _processo(bd, "p-precision")["company_id"] == "cmp-domus"

    async def test_um_processo_por_carimbar_acompanha_o_cliente(self, mundo):
        bd, mod = mundo
        p = _processo(bd, "p-precision")
        for campo in ("company_id", "company_name", "network_id"):
            p.pop(campo, None)
        resposta = await mod.run_transfer_client_company("c-power", _corpo(mod), MASTER)
        assert resposta["processos_transferidos"] == 2


@pytest.mark.asyncio
class TestOPreview:
    async def test_diz_o_que_impede_sem_escrever_nem_pedir_password(self, mundo):
        bd, mod = mundo
        antes = [dict(p) for p in bd.processes.docs]
        res = await mod.run_preview_transfer_client_company("c-power", "cmp-domus", MASTER)
        assert res["bloqueado"] is True
        assert [p["id"] for p in res["processos_que_impedem"]] == ["p-precision"]
        assert res["processos_a_mover"] == 1
        assert antes == [dict(p) for p in bd.processes.docs]

    async def test_com_o_cruzado_terminado_nao_bloqueia_e_lista_o_mantido(self, mundo):
        bd, mod = mundo
        _processo(bd, "p-precision")["status"] = "desistencia"
        res = await mod.run_preview_transfer_client_company("c-power", "cmp-domus", MASTER)
        assert res["bloqueado"] is False
        assert [p["id"] for p in res["processos_mantidos"]] == ["p-precision"]

    async def test_cliente_ou_empresa_inexistentes_sao_404(self, mundo):
        bd, mod = mundo
        for cliente, empresa in (("nao-existe", "cmp-domus"), ("c-power", "nao-existe")):
            with pytest.raises(HTTPException) as erro:
                await mod.run_preview_transfer_client_company(cliente, empresa, MASTER)
            assert erro.value.status_code == 404


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
