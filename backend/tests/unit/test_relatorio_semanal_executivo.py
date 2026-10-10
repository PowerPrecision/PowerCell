"""Relatório semanal executivo: registo, API e PDF (Bloco 4, ponto 13/16).

Semana fechada = REGISTO calculado uma vez; semana a decorrer = vista ao vivo
que não se guarda. O registo é por ÂMBITO (rede), nunca partilhado, e não
guarda nomes de clientes (RGPD). Os números das agregações vêm do motor, já
provado contra um Mongo real; aqui prova-se a política do registo.
"""
from __future__ import annotations

import ast
import copy
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

import services.executive_report as er
import services.executive_weekly as ew

BACKEND = Path(__file__).resolve().parents[2]
HOJE = date(2026, 10, 14)  # quarta-feira
CEO = {"id": "u-ceo", "name": "Cátia CEO", "role": "ceo"}


def _relatorio(inicio="2026-10-05", fim="2026-10-11"):
    return {
        "start_date": inicio, "end_date": fim, "gerado_em": "2026-10-14T09:00:00+00:00",
        "summary": {"total_users": 1}, "users": [{"user_id": "u-ana", "name": "Ana"}],
        "movimentos": [{"user_id": "u-ana", "process_id": "p1", "process_number": 12,
                        "de": "a", "para": "b"}],
    }


@pytest.fixture
def mundo(fake_async_db):
    chamadas = {"n": 0, "ambito": "rede-a"}

    async def ambito(user):
        return er.Ambito(chave=chamadas["ambito"], redes=("rede_a",))

    async def gerar(ambito_, filtros, **kw):
        chamadas["n"] += 1
        chamadas["filtros"] = filtros
        return _relatorio(filtros.periodo.inicio.isoformat(), filtros.periodo.fim.isoformat())

    fake_async_db.processes.docs.append({"id": "p1", "client_name": "Silva", "process_number": 12})
    with patch.object(er, "resolver_ambito", ambito), \
            patch.object(er, "gerar_relatorio", gerar), \
            patch.object(er, "_ler_processos", AsyncMock(side_effect=lambda base, ids: {
                p["id"]: p for p in base.processes.docs if p["id"] in ids})):
        yield fake_async_db, chamadas


async def _obter(base, semana="2026-10-07", **kw):
    return await ew.obter_semana(CEO, semana, base=base, hoje=HOJE, **kw)


class TestASemana:
    def test_sem_referencia_e_a_semana_anterior_fechada(self):
        assert ew.semana_pedida(None, hoje=HOJE) == (date(2026, 10, 5), date(2026, 10, 11))

    def test_qualquer_dia_da_semana_serve(self):
        assert ew.semana_pedida("2026-10-11", hoje=HOJE)[0] == date(2026, 10, 5)

    def test_a_semana_actual_e_valida(self):
        assert ew.semana_pedida("2026-10-14", hoje=HOJE) == (date(2026, 10, 12), date(2026, 10, 18))

    def test_uma_semana_futura_e_recusada(self):
        with pytest.raises(er.PeriodoInvalido):
            ew.semana_pedida("2026-10-19", hoje=HOJE)

    def test_fechada_so_depois_do_domingo(self):
        assert ew.semana_esta_fechada(date(2026, 10, 11), hoje=HOJE) is True
        assert ew.semana_esta_fechada(date(2026, 10, 18), hoje=HOJE) is False
        assert ew.semana_esta_fechada(date(2026, 10, 14), hoje=date(2026, 10, 14)) is False

    def test_as_semanas_recentes_comecam_na_actual(self):
        s = ew.semanas_recentes(3, hoje=HOJE)
        assert s == [date(2026, 10, 12), date(2026, 10, 5), date(2026, 9, 28)]


class TestORegisto:
    @pytest.mark.asyncio
    async def test_a_semana_fechada_e_calculada_uma_vez_e_fica_em_registo(self, mundo):
        base, chamadas = mundo
        r1 = await _obter(base)
        r2 = await _obter(base)
        assert chamadas["n"] == 1, "a segunda abertura lê o registo"
        assert r1["registo"]["guardado"] is True and r2["registo"]["guardado"] is True
        assert r2["registo"]["gerado_por"] == "Cátia CEO"
        assert len(base.executive_weekly_reports.docs) == 1
        doc = base.executive_weekly_reports.docs[0]
        assert (doc["scope_key"], doc["week_start"], doc["week_end"]) == ("rede-a", "2026-10-05", "2026-10-11")

    @pytest.mark.asyncio
    async def test_a_semana_a_decorrer_nao_se_guarda(self, mundo):
        base, chamadas = mundo
        r = await _obter(base, semana="2026-10-14")
        await _obter(base, semana="2026-10-14")
        assert r["registo"]["guardado"] is False
        assert base.executive_weekly_reports.docs == []
        assert chamadas["n"] == 2

    @pytest.mark.asyncio
    async def test_o_registo_e_por_ambito(self, mundo):
        """O registo de uma rede nunca serve outra."""
        base, chamadas = mundo
        await _obter(base)
        chamadas["ambito"] = "rede-b"
        await _obter(base)
        assert chamadas["n"] == 2
        assert {d["scope_key"] for d in base.executive_weekly_reports.docs} == {"rede-a", "rede-b"}

    @pytest.mark.asyncio
    async def test_forcar_regenera_e_substitui_sem_duplicar(self, mundo):
        base, chamadas = mundo
        await _obter(base)
        await _obter(base, forcar=True)
        assert chamadas["n"] == 2
        assert len(base.executive_weekly_reports.docs) == 1

    @pytest.mark.asyncio
    async def test_o_registo_nao_guarda_nomes_de_clientes(self, mundo):
        base, _ = mundo
        await _obter(base)
        assert "Silva" not in str(base.executive_weekly_reports.docs)
        assert "client_name" not in str(base.executive_weekly_reports.docs)

    @pytest.mark.asyncio
    async def test_o_nome_resolve_se_na_leitura_com_os_dados_de_hoje(self, mundo):
        base, _ = mundo
        r1 = await _obter(base)
        assert r1["movimentos"][0]["client_name"] == "Silva"
        base.processes.docs[0]["client_name"] = "Anonimizado"  # RGPD, depois da semana
        r2 = await _obter(base)
        assert r2["movimentos"][0]["client_name"] == "Anonimizado"
        assert "Silva" not in str(base.executive_weekly_reports.docs)

    @pytest.mark.asyncio
    async def test_se_o_registo_falhar_o_relatorio_aparece_na_mesma(self, mundo):
        base, _ = mundo

        async def falha(*a, **k):
            raise RuntimeError("bd")

        with patch.object(base.executive_weekly_reports, "update_one", falha):
            r = await _obter(base)
        assert r["users"] and r["registo"]["guardado"] is False

    @pytest.mark.asyncio
    async def test_o_relatorio_pede_os_movimentos(self, mundo):
        base, chamadas = mundo
        await _obter(base)
        assert chamadas["filtros"].com_movimentos is True

    @pytest.mark.asyncio
    async def test_uma_semana_futura_nao_gera_nada(self, mundo):
        base, chamadas = mundo
        with pytest.raises(er.PeriodoInvalido):
            await _obter(base, semana="2026-12-01")
        assert chamadas["n"] == 0


class TestAListaDeSemanas:
    @pytest.mark.asyncio
    async def test_marca_as_que_tem_registo_so_do_ambito(self, mundo):
        base, chamadas = mundo
        await _obter(base)  # semana 05/10 da rede-a
        chamadas["ambito"] = "rede-b"
        lista = await ew.listar_semanas(CEO, base=base, hoje=HOJE)
        assert len(lista) == 12 and not any(s["tem_registo"] for s in lista)
        chamadas["ambito"] = "rede-a"
        lista = await ew.listar_semanas(CEO, base=base, hoje=HOJE)
        assert [s["week_start"] for s in lista if s["tem_registo"]] == ["2026-10-05"]
        assert lista[0]["fechada"] is False and lista[1]["fechada"] is True


class TestAApi:
    @pytest.mark.asyncio
    async def test_periodo_invalido_e_422(self):
        import services.executive_report_api as api

        with pytest.raises(HTTPException) as exc:
            await api.run_team_performance(CEO, "2026-10-10", "2026-10-01")
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_corte_da_base_de_dados_e_503_e_nunca_vazio(self):
        import services.executive_report_api as api

        with patch.object(er, "resolver_ambito", AsyncMock(return_value=er.Ambito(chave="x"))), \
                patch.object(er, "gerar_relatorio", AsyncMock(side_effect=er.RelatorioIndisponivel("demorou demasiado"))):
            with pytest.raises(HTTPException) as exc:
                await api.run_team_performance(CEO)
        assert exc.value.status_code == 503 and "demorou" in exc.value.detail

    @pytest.mark.asyncio
    async def test_os_filtros_chegam_ao_motor_normalizados(self):
        import services.executive_report_api as api

        gerar = AsyncMock(return_value=_relatorio())
        with patch.object(er, "resolver_ambito", AsyncMock(return_value=er.Ambito(chave="x"))), \
                patch.object(er, "gerar_relatorio", gerar):
            await api.run_team_performance(CEO, "2026-10-05", "2026-10-11", "b, a,a", "consultor,diretor")
        filtros = gerar.await_args.args[1]
        assert filtros.user_ids == ("a", "b") and filtros.papeis == ("consultor", "diretor")

    @pytest.mark.asyncio
    async def test_o_pdf_e_o_mesmo_relatorio_do_ecra(self):
        import services.executive_report_api as api

        rel = {**_relatorio(), "filtros": {}, "por_fase": [], "serie_diaria": [], "notas": [],
               "summary": {}, "users": [{"name": "Ana", "role": "consultor", "phase_changes": 1,
                                         "processes_moved": 1, "tasks_completed": 1,
                                         "tasks_pending": 0, "tasks_overdue": 0}]}
        gerar = AsyncMock(return_value=rel)
        with patch.object(er, "resolver_ambito", AsyncMock(return_value=er.Ambito(chave="x"))), \
                patch.object(er, "gerar_relatorio", gerar), \
                patch.object(api, "_branding", AsyncMock(return_value={"empresa": {"nome": "Power"}, "logo_bytes": None, "accent": "#334155"})):
            resp = await api.run_team_performance_pdf(CEO, "2026-10-05", "2026-10-11")
        assert resp.media_type == "application/pdf" and resp.body[:5] == b"%PDF-"
        assert 'filename="relatorio-executivo_2026-10-05_2026-10-11.pdf"' in resp.headers["content-disposition"]
        assert resp.headers["cache-control"] == "no-store"
        assert gerar.await_args.args[1].com_movimentos is False

    @pytest.mark.asyncio
    async def test_o_pdf_corre_fora_do_event_loop(self):
        import services.executive_report_api as api

        fonte = (BACKEND / "services" / "executive_report_api.py").read_text(encoding="utf-8")
        assert "run_in_executor" in fonte


class TestAsRotas:
    def _handlers(self):
        arvore = ast.parse((BACKEND / "routes" / "admin.py").read_text(encoding="utf-8"))
        nomes = {"get_team_performance", "get_team_performance_pdf", "get_executive_weekly",
                 "regenerate_executive_weekly", "get_executive_weekly_pdf"}
        return {n.name: n for n in arvore.body if isinstance(n, ast.AsyncFunctionDef) and n.name in nomes}

    def test_existem_as_cinco(self):
        assert len(self._handlers()) == 5

    def test_so_admin_e_ceo(self):
        for nome, h in self._handlers().items():
            fonte = ast.unparse(h)
            assert "UserRole.ADMIN" in fonte and "UserRole.CEO" in fonte, nome
            assert "UserRole.DIRETOR" not in fonte and "UserRole.CONSULTOR" not in fonte, nome

    def test_limitadas_com_request_e_response(self):
        for nome, h in self._handlers().items():
            args = {a.arg for a in h.args.args}
            assert {"request", "response"} <= args, nome
            assert any("limiter.limit" in ast.unparse(d) for d in h.decorator_list), nome

    def test_o_pdf_tem_limite_mais_apertado_que_a_vista(self):
        h = self._handlers()
        assert any("6/minute" in ast.unparse(d) for d in h["get_team_performance_pdf"].decorator_list)
        assert any("30/minute" in ast.unparse(d) for d in h["get_team_performance"].decorator_list)
