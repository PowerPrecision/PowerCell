"""
Lote 4, ponto 2 (Out 2026) — «Clientes Registados» é o ecrã de TRABALHO.

O PEDIDO
  «Clientes cujos processos já se encontram em Concluído ou Desistência continuam a
  poluir o ecrã ativo de Clientes Registados.»

A REGRA
  Por omissão o ecrã não mostra o cliente cujos processos estão TODOS terminados (fase
  terminal DO MOTOR) ou eliminados; o separador «Histórico» mostra só esses. Um cliente
  sem processo (lead) fica no ecrã de trabalho, e basta UM processo em curso para o
  cliente ficar lá (quem tem um processo concluído e outro activo é trabalho).
"""
from __future__ import annotations

import pytest

from tests.unit.helpers_tenant import (  # noqa: F401  (fixture)
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

ANA = {"id": "u-ana", "name": "Ana", "email": "ana@power.pt", "role": "diretor"}


def _cli(id, nome, **kw):
    base = {
        "id": id, "nome": nome, "contacto": {"email": f"{id}@x.pt", "telefone": "910000000"},
        "dados_pessoais": {"nif": "100000000"}, "company_id": "cmp-power",
        "network_id": REDE_INCUMBENTE, "process_ids": [],
    }
    base.update(kw)
    return base


def _proc(id, client_id, nome, status="em_analise", **kw):
    base = {
        "id": id, "client_id": client_id, "client_name": nome, "status": status,
        "process_number": 1, "company_id": "cmp-power", "network_id": REDE_INCUMBENTE,
        "created_at": "2026-10-01T10:00:00Z",
    }
    base.update(kw)
    return base


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    import services.client_list_search as cls
    import services.client_list_titulares as clt

    semear(fake_async_db)
    fake_async_db.processes.docs.clear()
    fake_async_db.clients.docs.clear()
    fake_async_db.clients.docs.extend([
        _cli("c-curso", "Em Curso"),
        _cli("c-concluido", "Concluído Só"),
        _cli("c-desistiu", "Desistiu"),
        _cli("c-misto", "Misto"),
        _cli("c-eliminado", "Só Eliminado"),
        _cli("c-lead", "Lead Sem Processo"),
    ])
    fake_async_db.processes.docs.extend([
        _proc("p1", "c-curso", "Em Curso"),
        _proc("p2", "c-concluido", "Concluído Só", status="concluido"),
        _proc("p3", "c-desistiu", "Desistiu", status="desistencia"),
        _proc("p4", "c-misto", "Misto", status="concluido"),
        _proc("p5", "c-misto", "Misto", status="em_analise"),
        _proc("p6", "c-eliminado", "Só Eliminado", is_deleted=True),
    ])
    with tenant_db(fake_async_db, cls, clt):
        yield fake_async_db


async def _listar(**kw):
    import services.client_list_search as cls

    kw.setdefault("limit", 100)
    kw.setdefault("exclude_deleted", True)
    return await cls.run_list_clients(ANA, **kw)


def _ids(res):
    return {c["id"] for c in res["clients"]}


@pytest.mark.asyncio
class TestOEcraDeTrabalhoNaoMostraOHistorico:
    async def test_a_exploracao_concluidos_e_desistencias_ja_nao_poluem_o_ecra(self, mundo):
        """O ataque (era o defeito): estes dois apareciam no ecrã ativo."""
        ids = _ids(await _listar())
        assert "c-concluido" not in ids
        assert "c-desistiu" not in ids

    async def test_o_trabalho_em_curso_continua_la(self, mundo):
        ids = _ids(await _listar())
        assert {"c-curso", "c-misto"} <= ids

    async def test_basta_um_processo_em_curso_para_ficar_no_ecra_de_trabalho(self, mundo):
        assert "c-misto" in _ids(await _listar())
        assert "c-misto" not in _ids(await _listar(historico=True))

    def test_a_lead_sem_processo_nao_e_historico(self):
        # Contraprova: «todos terminados» não pode ser verdade para uma lista VAZIA.
        from services.client_list_search import _so_processos_terminados

        assert _so_processos_terminados({"processes": []}, {"concluido"}) is False
        assert _so_processos_terminados({}, {"concluido"}) is False
        assert _so_processos_terminados({"processes": [{"status": "concluido"}]}, {"concluido"}) is True
        assert _so_processos_terminados(
            {"processes": [{"status": "concluido"}, {"status": "em_analise"}]}, {"concluido"},
        ) is False


@pytest.mark.asyncio
class TestOSeparadorHistorico:
    async def test_mostra_so_os_clientes_de_processos_terminados(self, mundo):
        ids = _ids(await _listar(historico=True))
        assert ids == {"c-concluido", "c-desistiu"}

    async def test_a_resposta_anuncia_quantos_escondeu(self, mundo):
        res = await _listar()
        assert res["total_historico"] == 2
        # E o separador mostra o mesmo total que anuncia.
        assert (await _listar(historico=True))["total"] == 2

    async def test_a_vista_de_eliminados_nao_e_tocada(self, mundo):
        res = await _listar(exclude_deleted=False, deleted_only=True)
        assert "c-eliminado" in _ids(res)
        assert res["total_historico"] == 0

    async def test_o_cliente_so_com_processo_eliminado_nao_polui_o_ecra(self, mundo):
        assert "c-eliminado" not in _ids(await _listar())

    async def test_as_fases_terminais_vem_do_motor_e_nao_de_uma_lista_de_nomes(self, mundo):
        """Uma fase terminal que só existe no workflow (não na lista legada) também conta."""
        mundo.workflow_statuses.docs.extend([
            {"name": "em_analise", "label": "Em análise", "order": 1, "is_active": True},
            {"name": "fechado_pelo_banco", "label": "Fechado", "order": 9, "is_active": False},
        ])
        mundo.clients.docs.append(_cli("c-fechado", "Fechado Pelo Banco"))
        mundo.processes.docs.append(_proc("p9", "c-fechado", "Fechado Pelo Banco", status="fechado_pelo_banco"))
        from services import workflow_phases as wp

        wp.invalidar_cache_de_fases()
        assert "c-fechado" in _ids(await _listar(historico=True))
        assert "c-fechado" not in _ids(await _listar())


class TestOEcraLigaOSeparador:
    def test_a_rota_expoe_o_parametro_e_a_pagina_pede_o_historico(self):
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[2]
        rota = (raiz / "routes" / "clients.py").read_text(encoding="utf-8")
        assert "historico: Optional[bool]" in rota and "historico=historico" in rota
        pagina = (raiz.parent / "frontend" / "src" / "pages" / "ClientsPage.js").read_text(encoding="utf-8")
        assert 'params.append("historico", "true")' in pagina
        assert 'data-testid="clients-tab-historico"' in pagina
