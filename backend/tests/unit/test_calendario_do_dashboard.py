"""Calendário visual do Dashboard (Bloco 4, pontos 29 e 32).

Mostra marcações, escrituras, CPCVs e ausências do mês. As datas de escritura
e de CPCV vivem no PROCESSO (não são eventos), por isso um calendário que só
lesse `deadlines` não as mostrava nunca — e a visibilidade delas tem de ser a
das listagens de processos (rede incluída).
"""
from __future__ import annotations

import ast
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

import services.dashboard_calendar as dc
from tests.unit.helpers_tenant import (  # noqa: F401  (fixtures)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

BACKEND = Path(__file__).resolve().parents[2]
OUT = date(2026, 10, 1)
NOV = date(2026, 11, 1)


class TestOMes:
    def test_janela(self):
        assert dc.janela_do_mes("2026-10") == (date(2026, 10, 1), date(2026, 11, 1))
        assert dc.janela_do_mes("2026-12") == (date(2026, 12, 1), date(2027, 1, 1))

    def test_omissao_e_o_mes_actual(self):
        assert dc.janela_do_mes(None, hoje=date(2026, 3, 17)) == (date(2026, 3, 1), date(2026, 4, 1))

    @pytest.mark.parametrize("mes", ["2026-13", "2026-00", "10/2026", "2026-1", "x"])
    def test_invalido(self, mes):
        with pytest.raises(ValueError):
            dc.janela_do_mes(mes)


class TestAClassificacao:
    @pytest.mark.parametrize("evento,categoria", [
        ({"type": "absence", "title": "Escritura"}, "ausencia"),  # a ausência vence o título
        ({"type": "deadline", "title": "Escritura Ana Martins"}, "escritura"),
        ({"type": "event", "title": "ESCRITURA"}, "escritura"),
        ({"type": "deadline", "title": "Assinar CPCV"}, "cpcv"),
        ({"type": "deadline", "description": "marcar escritura no notário"}, "escritura"),
        ({"type": "event", "title": "Reunião com o banco"}, "marcacao"),
        ({"type": "deadline", "title": "Visita ao imóvel"}, "marcacao"),
        ({"type": "deadline", "title": "Visita"}, "marcacao"),
        ({"type": "deadline", "title": "Entregar IRS"}, "prazo"),
        ({}, "prazo"),
    ])
    def test_categorias(self, evento, categoria):
        assert dc.categoria_do_evento(evento) == categoria


class TestOsDias:
    def test_um_dia(self):
        assert dc.dias_do_evento({"due_date": "2026-10-07T10:00:00"}, OUT, NOV) == ["2026-10-07"]

    def test_varios_dias_cortados_ao_mes(self):
        e = {"due_date": "2026-09-29", "end_date": "2026-10-02"}
        assert dc.dias_do_evento(e, OUT, NOV) == ["2026-10-01", "2026-10-02"]
        e = {"due_date": "2026-10-30", "end_date": "2026-11-03"}
        assert dc.dias_do_evento(e, OUT, NOV) == ["2026-10-30", "2026-10-31"]

    def test_fim_antes_do_inicio_vale_um_dia(self):
        assert dc.dias_do_evento({"due_date": "2026-10-07", "end_date": "2026-10-01"}, OUT, NOV) == ["2026-10-07"]

    def test_fora_do_mes_ou_ilegivel(self):
        assert dc.dias_do_evento({"due_date": "2026-09-30"}, OUT, NOV) == []
        assert dc.dias_do_evento({"due_date": "2026-11-01"}, OUT, NOV) == []
        assert dc.dias_do_evento({"due_date": "lixo"}, OUT, NOV) == []
        assert dc.dias_do_evento({}, OUT, NOV) == []

    def test_a_hora_so_sai_se_houver(self):
        assert dc.item_de_evento({"id": "e", "due_date": "2026-10-07T14:30:00", "title": "x"}, "2026-10-07")["hora"] == "14:30"
        assert dc.item_de_evento({"id": "e", "due_date": "2026-10-07", "title": "x"}, "2026-10-07")["hora"] is None
        assert dc.item_de_evento({"id": "e", "due_date": "2026-10-07T14:30:00", "all_day": True, "title": "x"}, "2026-10-07")["hora"] is None

    def test_a_ausencia_nao_leva_nome_de_cliente(self):
        item = dc.item_de_evento({"id": "e", "type": "absence", "client_name": "Ausência", "responsible_name": "Ana"}, "2026-10-07")
        assert item["client_name"] == "" and item["responsavel"] == "Ana"


class TestOsProcessos:
    PROC = {"id": "p1", "process_number": 12, "client_id": "c1", "client_name": "Silva",
            "real_estate_data": {"data_escritura_prevista": "2026-10-20", "data_cpcv": "2026-10-05"}}

    def test_escritura_e_cpcv_do_mes(self):
        itens = dc.itens_do_processo(self.PROC, OUT, NOV)
        assert {(i["categoria"], i["dia"]) for i in itens} == {("escritura", "2026-10-20"), ("cpcv", "2026-10-05")}
        assert all(i["origem"] == "processo" and i["process_id"] == "p1" for i in itens)
        assert "processo #12" in itens[0]["titulo"]

    def test_datas_de_outro_mes_ou_noutro_formato_ficam_de_fora(self):
        p = {**self.PROC, "real_estate_data": {"data_escritura_prevista": "20/10/2026", "data_cpcv": "2026-11-05"}}
        assert dc.itens_do_processo(p, OUT, NOV) == []

    def test_processo_sem_dados(self):
        assert dc.itens_do_processo({"id": "p"}, OUT, NOV) == []
        assert dc.itens_do_processo({"id": "p", "real_estate_data": None}, OUT, NOV) == []

    def test_nao_duplica_um_evento_criado_a_mao(self):
        eventos = [dc.item_de_evento(
            {"id": "e", "title": "Escritura Silva", "due_date": "2026-10-20", "process_id": "p1"}, "2026-10-20")]
        do_proc = dc.itens_do_processo(self.PROC, OUT, NOV)
        sobra = dc.sem_duplicados(eventos, do_proc)
        assert [i["categoria"] for i in sobra] == ["cpcv"]

    def test_o_mesmo_dia_noutro_processo_nao_e_duplicado(self):
        eventos = [dc.item_de_evento(
            {"id": "e", "title": "Escritura", "due_date": "2026-10-20", "process_id": "p-outro"}, "2026-10-20")]
        assert len(dc.sem_duplicados(eventos, dc.itens_do_processo(self.PROC, OUT, NOV))) == 2

    def test_contagens(self):
        itens = dc.itens_do_processo(self.PROC, OUT, NOV)
        assert dc.contagens(itens) == {"escritura": 1, "cpcv": 1, "marcacao": 0, "ausencia": 0, "prazo": 0}


class TestAJanelaDosEventos:
    def test_sem_janela_nao_filtra(self):
        from services.deadlines_api_calendar import janela_de_datas

        assert janela_de_datas(None, None) == {}
        assert janela_de_datas("2026-10-01", None) == {}

    def test_apanha_o_evento_que_atravessa_o_mes(self):
        from services.deadlines_api_calendar import janela_de_datas
        from tests.unit.helpers_tenant import casa

        j = janela_de_datas("2026-10-01", "2026-11-01")
        assert casa({"due_date": "2026-10-15T09:00:00"}, j)
        assert casa({"due_date": "2026-09-28", "end_date": "2026-10-02"}, j)  # começou antes
        assert not casa({"due_date": "2026-09-28", "end_date": "2026-09-30"}, j)
        assert not casa({"due_date": "2026-11-01"}, j)
        assert not casa({"due_date": "2026-09-30"}, j)


@pytest.fixture
def mundo(fake_async_db, rede_de_omissao_incumbente):
    import services.process_list_filters  # noqa: F401
    import services.tenant_network as tn  # noqa: F401

    semear(fake_async_db)
    fake_async_db.processes.docs.clear()
    fake_async_db.processes.docs.extend([
        {"id": "p-power", "process_number": 1, "client_id": "c1", "client_name": "Silva", "status": "em_analise",
         "company_id": "cmp-power", "network_id": REDE_INCUMBENTE,
         "assigned_consultor_ids": ["u-ana"], "assigned_consultor_id": "u-ana",
         "real_estate_data": {"data_escritura_prevista": "2026-10-20"}},
        {"id": "p-domus", "process_number": 2, "client_id": "c2", "client_name": "Dias", "status": "em_analise",
         "company_id": "cmp-domus", "network_id": REDE_DOMUS,
         "real_estate_data": {"data_cpcv": "2026-10-08"}},
        {"id": "p-fora", "process_number": 3, "client_id": "c3", "client_name": "Fora de Data", "status": "em_analise",
         "company_id": "cmp-power", "network_id": REDE_INCUMBENTE,
         "real_estate_data": {"data_escritura_prevista": "2026-12-01"}},
    ])
    with tenant_db(fake_async_db, dc):
        yield fake_async_db


ANA = {"id": "u-ana", "name": "Ana", "email": "a@x.pt", "role": "diretor"}
BRUNO = {"id": "u-bruno", "name": "Bruno", "email": "b@x.pt", "role": "diretor"}


async def _correr(user, mes="2026-10", eventos=None):
    with patch("services.deadlines_api_calendar.run_get_calendar_deadlines", AsyncMock(return_value=eventos or [])):
        return await dc.run_dashboard_calendar(user, None, mes)


class TestOServico:
    @pytest.mark.asyncio
    async def test_mostra_a_escritura_do_processo_da_sua_rede(self, mundo):
        r = await _correr(ANA)
        assert [(i["categoria"], i["dia"], i["process_id"]) for i in r["itens"]] == [("escritura", "2026-10-20", "p-power")]
        assert r["contagens"]["escritura"] == 1 and r["month"] == "2026-10"

    @pytest.mark.asyncio
    async def test_a_domus_e_uma_ilha_nas_datas_dos_processos(self, mundo):
        """O CPCV do processo da Domus não aparece à Ana, e vice-versa."""
        ana = await _correr(ANA)
        bruno = await _correr(BRUNO)
        assert "p-domus" not in {i["process_id"] for i in ana["itens"]}
        assert {i["process_id"] for i in bruno["itens"]} == {"p-domus"}

    @pytest.mark.asyncio
    async def test_um_processo_com_a_data_noutro_mes_nao_aparece(self, mundo):
        r = await _correr(ANA, mes="2026-12")
        assert [i["process_id"] for i in r["itens"]] == ["p-fora"]

    @pytest.mark.asyncio
    async def test_junta_os_eventos_do_calendario_ordenados(self, mundo):
        eventos = [
            {"id": "e2", "title": "Visita ao imóvel", "due_date": "2026-10-02T15:00:00", "type": "event", "client_name": "Silva"},
            {"id": "e1", "title": "Férias", "due_date": "2026-10-01", "end_date": "2026-10-03", "type": "absence",
             "responsible_name": "Rui"},
        ]
        r = await _correr(ANA, eventos=eventos)
        assert [(i["dia"], i["categoria"]) for i in r["itens"]] == [
            ("2026-10-01", "ausencia"), ("2026-10-02", "ausencia"), ("2026-10-02", "marcacao"),
            ("2026-10-03", "ausencia"), ("2026-10-20", "escritura"),
        ]

    @pytest.mark.asyncio
    async def test_pede_so_a_janela_do_mes_ao_calendario(self, mundo):
        chamada = AsyncMock(return_value=[])
        with patch("services.deadlines_api_calendar.run_get_calendar_deadlines", chamada):
            await dc.run_dashboard_calendar(ANA, None, "2026-10")
        assert chamada.await_args.kwargs == {"desde": "2026-10-01", "ate": "2026-11-01"}

    @pytest.mark.asyncio
    async def test_mes_invalido_e_422(self, mundo):
        with pytest.raises(HTTPException) as exc:
            await _correr(ANA, mes="2026-13")
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_um_processo_eliminado_ou_terminal_nao_aparece(self, mundo):
        mundo.processes.docs[0]["is_deleted"] = True
        r = await _correr(ANA)
        assert r["itens"] == []

    @pytest.mark.asyncio
    async def test_um_processo_em_fase_terminal_nao_aparece(self, mundo):
        """Uma escritura de um processo concluído/desistido não é trabalho a fazer."""
        mundo.processes.docs[0]["status"] = "concluido"
        assert (await _correr(ANA))["itens"] == []

    @pytest.mark.asyncio
    async def test_a_fase_terminal_vem_do_motor_e_nao_de_uma_lista(self, mundo):
        """Uma fase que o administrador marcou como terminal (`is_active: false`)
        e que não está na lista legada também esconde a escritura."""
        from services import workflow_phases as wp

        mundo.workflow_statuses.docs.append({"name": "finalizado_x", "is_active": False, "order": 1})
        wp.invalidar_cache_de_fases()
        mundo.processes.docs[0]["status"] = "finalizado_x"
        assert (await _correr(ANA))["itens"] == []

    @pytest.mark.asyncio
    async def test_a_consulta_aos_processos_leva_a_janela_dos_dois_lados(self, mundo):
        """A base de dados filtra pelo mês (índice), não só o Python depois."""
        capturado = {}
        original = mundo.processes.find

        def espia(query, projecao=None):
            capturado["query"] = query
            return original(query, projecao)

        with patch.object(mundo.processes, "find", espia):
            await _correr(ANA)
        janela = capturado["query"]["$and"][-1]["$or"]
        assert {"real_estate_data.data_escritura_prevista": {"$gte": "2026-10-01", "$lt": "2026-11-01"}} in janela
        assert {"real_estate_data.data_cpcv": {"$gte": "2026-10-01", "$lt": "2026-11-01"}} in janela

    @pytest.mark.asyncio
    async def test_diz_quando_cortou_os_processos(self, mundo, monkeypatch):
        monkeypatch.setattr(dc, "LIMITE_DE_PROCESSOS", 1)
        assert (await _correr(ANA))["truncado"] is True


class TestALigacao:
    def test_a_rota_existe_antes_de_deadline_id(self):
        arvore = ast.parse((BACKEND / "routes" / "deadlines.py").read_text(encoding="utf-8"))
        ordem = [
            d.args[0].value
            for n in arvore.body if isinstance(n, ast.AsyncFunctionDef)
            for d in n.decorator_list
            if isinstance(d, ast.Call) and d.args and isinstance(d.args[0], ast.Constant)
        ]
        assert ordem.index("/dashboard-calendar") < ordem.index("/{deadline_id}")

    def test_o_handler_passa_o_request(self):
        arvore = ast.parse((BACKEND / "routes" / "deadlines.py").read_text(encoding="utf-8"))
        h = next(n for n in arvore.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "get_dashboard_calendar")
        assert "request" in {a.arg for a in h.args.args}
        assert "run_dashboard_calendar(user, request, month)" in ast.unparse(h)

    def test_os_indices_das_datas_estao_declarados(self):
        fonte = (BACKEND / "services" / "db_indexes.py").read_text(encoding="utf-8")
        assert "idx_proc_data_escritura" in fonte and "idx_proc_data_cpcv" in fonte
