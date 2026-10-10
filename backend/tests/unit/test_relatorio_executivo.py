"""O motor do relatório executivo (Bloco 4, pontos 13 e 16).

Este ficheiro prova a LÓGICA — o período, o âmbito, a atribuição, a
orquestração, os tectos — com a costura de acesso à base de dados
substituída. O que NÃO se pode provar aqui, e vive em
`tests/integration/test_relatorio_executivo_mongo.py` contra um Mongo REAL,
é a semântica das pipelines (`$unwind` sobre arrays, `$substrBytes`, a
ordem dos `$group`) e o uso de índices: um duplo que reimplementasse o
`$group` provava o duplo, não a base de dados.
"""
from __future__ import annotations

import ast
import json
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

import services.executive_report as er

BACKEND = Path(__file__).resolve().parents[2]
HOJE = date(2026, 10, 9)  # sexta-feira
AGORA = datetime(2026, 10, 9, 15, 30, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _cache_limpa():
    er.limpar_cache()
    yield
    er.limpar_cache()


def _filtros(inicio="2026-10-05", fim="2026-10-11", **kw):
    return er.Filtros(er.construir_periodo(inicio, fim, hoje=HOJE), **kw)


# ════════════════════════════════════════════════════════════════════
# O PERÍODO
# ════════════════════════════════════════════════════════════════════

class TestOPeriodo:
    def test_a_omissao_sao_sete_dias_a_terminar_hoje(self):
        p = er.construir_periodo(None, None, hoje=HOJE)
        assert (p.inicio, p.fim) == (date(2026, 10, 3), date(2026, 10, 9))
        assert p.dias == 7

    def test_o_fim_e_inclusivo_e_o_limite_superior_e_exclusivo(self):
        """`fim=domingo` tem de incluir o domingo inteiro e nada da segunda."""
        p = er.construir_periodo("2026-10-05", "2026-10-11", hoje=HOJE)
        assert p.inicio_utc.isoformat() == "2026-10-05T00:00:00+00:00"
        assert p.fim_exclusivo_utc.isoformat() == "2026-10-12T00:00:00+00:00"

    def test_um_so_dia_e_valido(self):
        assert er.construir_periodo("2026-10-09", "2026-10-09", hoje=HOJE).dias == 1

    @pytest.mark.parametrize("inicio,fim", [("2026-10-10", "2026-10-09")])
    def test_inicio_depois_do_fim_e_recusado(self, inicio, fim):
        with pytest.raises(er.PeriodoInvalido):
            er.construir_periodo(inicio, fim, hoje=HOJE)

    @pytest.mark.parametrize("valor", ["09/10/2026", "2026-13-01", "ontem", "2026-10-9x"])
    def test_formato_invalido(self, valor):
        with pytest.raises(er.PeriodoInvalido):
            er.construir_periodo(valor, None, hoje=HOJE)
        with pytest.raises(er.PeriodoInvalido):
            er.construir_periodo(None, valor, hoje=HOJE)

    def test_o_tecto_do_periodo(self):
        er.construir_periodo("2025-10-09", "2026-10-09", hoje=HOJE)  # 366 dias
        with pytest.raises(er.PeriodoInvalido):
            er.construir_periodo("2025-10-08", "2026-10-09", hoje=HOJE)  # 367

    def test_a_semana_vai_de_segunda_a_domingo(self):
        assert er.semana_de(date(2026, 10, 9)) == (date(2026, 10, 5), date(2026, 10, 11))
        assert er.semana_de(date(2026, 10, 5)) == (date(2026, 10, 5), date(2026, 10, 11))
        assert er.semana_de(date(2026, 10, 11)) == (date(2026, 10, 5), date(2026, 10, 11))


class TestNormalizarLista:
    def test_aceita_texto_e_lista(self):
        assert er.normalizar_lista("b, a ,,a") == ("a", "b")
        assert er.normalizar_lista(["b", " a", "a"]) == ("a", "b")

    @pytest.mark.parametrize("vazio", [None, "", " , ", []])
    def test_vazio(self, vazio):
        assert er.normalizar_lista(vazio) == ()


# ════════════════════════════════════════════════════════════════════
# AS PIPELINES — forma (a semântica é provada contra um Mongo real)
# ════════════════════════════════════════════════════════════════════

A, B = "2026-10-05T00:00:00+00:00", "2026-10-12T00:00:00+00:00"
IDS = ["u1", "u2"]

PIPELINES = {
    "mudancas_por_pessoa": (er.pipeline_mudancas_por_pessoa(IDS, A, B), {"user_id", "created_at"}),
    "mudancas_por_fase": (er.pipeline_mudancas_por_fase(IDS, A, B), {"user_id", "created_at"}),
    "mudancas_por_dia": (er.pipeline_mudancas_por_dia(IDS, A, B), {"user_id", "created_at"}),
    "concluidas_por_pessoa": (er.pipeline_concluidas_por_pessoa(IDS, A, B, {}), {"completed_by", "completed_at"}),
    "concluidas_por_dia": (er.pipeline_concluidas_por_dia(IDS, A, B, {}), {"completed_by", "completed_at"}),
    "carga_em_aberto": (er.pipeline_carga_em_aberto(IDS, B, "2026-10-12", {}), {"assigned_to", "created_at"}),
}


class TestAsPipelines:
    @pytest.mark.parametrize("nome", PIPELINES)
    def test_abre_com_um_match(self, nome):
        pipeline, _ = PIPELINES[nome]
        assert "$match" in pipeline[0]

    @pytest.mark.parametrize("nome", PIPELINES)
    def test_o_match_assenta_nos_campos_indexados(self, nome):
        """Um `$match` sem estes campos varre a colecção inteira."""
        pipeline, campos = PIPELINES[nome]
        assert campos <= set(pipeline[0]["$match"]), (nome, pipeline[0]["$match"])

    @pytest.mark.parametrize("nome", PIPELINES)
    def test_nunca_ha_regex(self, nome):
        """O `$regex` com `i` do relatório antigo não usa índice."""
        pipeline, _ = PIPELINES[nome]
        assert "$regex" not in json.dumps(pipeline)

    @pytest.mark.parametrize("nome", PIPELINES)
    def test_o_periodo_e_semiaberto(self, nome):
        """`[início, fim[`: o fim ignorado era o defeito do relatório antigo."""
        pipeline, _ = PIPELINES[nome]
        texto = json.dumps(pipeline)
        assert B in texto, "o limite superior tem de estar na pipeline"

    def test_o_historico_identifica_a_fase_por_campo_estruturado(self):
        match = er.match_de_mudancas_de_fase(IDS, A, B)
        assert {"field": {"$in": ["estado", "fase", "status"]}} in match["$or"]
        assert {"action": "Moveu processo"} in match["$or"]

    def test_a_condicao_de_rede_envolve_as_tarefas(self):
        rede = {"network_id": {"$in": ["rede_a"]}}
        for pipeline in (
            er.pipeline_concluidas_por_pessoa(IDS, A, B, rede),
            er.pipeline_concluidas_por_dia(IDS, A, B, rede),
            er.pipeline_carga_em_aberto(IDS, B, "2026-10-12", rede),
        ):
            assert pipeline[0]["$match"]["$and"][0] == rede

    def test_sem_condicao_de_rede_o_match_fica_simples(self):
        assert "$and" not in er.pipeline_concluidas_por_pessoa(IDS, A, B, {})[0]["$match"]

    def test_as_tarefas_apagadas_ficam_de_fora(self):
        for pipeline in (
            er.pipeline_concluidas_por_pessoa(IDS, A, B, {}),
            er.pipeline_carga_em_aberto(IDS, B, "2026-10-12", {}),
        ):
            assert pipeline[0]["$match"]["is_deleted"] == {"$ne": True}

    def test_a_carga_e_o_estado_no_fim_do_periodo(self):
        match = er.pipeline_carga_em_aberto(IDS, B, "2026-10-12", {})[0]["$match"]
        assert match["created_at"] == {"$lt": B}
        assert {"completed": {"$ne": True}} in match["$or"]
        assert {"completed_at": {"$gte": B}} in match["$or"]

    def test_so_se_conta_a_quem_esta_na_lista_depois_do_unwind(self):
        """Uma tarefa de três pessoas não pode inflacionar quem está fora do filtro."""
        etapas = [list(e)[0] for e in er.pipeline_carga_em_aberto(IDS, B, "2026-10-12", {})]
        assert etapas == ["$match", "$unwind", "$match", "$group"]

    def test_o_prazo_so_com_data_vale_ate_ao_fim_do_dia(self):
        grupo = er.pipeline_carga_em_aberto(IDS, B, "2026-10-12", {})[3]["$group"]
        texto = json.dumps(grupo["atrasadas"])
        assert "$substrBytes" in texto and "2026-10-12" in texto
        assert '"$type"' in texto, "um prazo que não é texto não pode rebentar a agregação"


# ════════════════════════════════════════════════════════════════════
# A MONTAGEM — pura
# ════════════════════════════════════════════════════════════════════

FASES = [
    {"name": "fase_documental", "label": "Fase Documental", "order": 1},
    {"name": "aprovado", "label": "Aprovado", "order": 2},
]
UTILIZADORES = [
    {"id": "u-ana", "name": "Ana", "email": "ana@x.pt", "role": "consultor"},
    {"id": "u-rui", "name": "Rui", "email": "rui@x.pt", "role": "intermediario"},
    {"id": "u-zé", "name": "Zé", "email": "ze@x.pt", "role": "diretor", "track_history": False},
]


def _montar(**kw):
    base = dict(
        utilizadores=UTILIZADORES,
        por_pessoa={"u-ana": {"processos": 3, "mudancas": 5}, "u-rui": {"processos": 1, "mudancas": 1}},
        por_fase_e_pessoa=[
            {"_id": {"user_id": "u-ana", "fase": "aprovado"}, "n": 4},
            {"_id": {"user_id": "u-ana", "fase": "fase_documental"}, "n": 1},
            {"_id": {"user_id": "u-rui", "fase": "aprovado"}, "n": 1},
        ],
        concluidas={"u-ana": 2, "u-rui": 7, "u-zé": 1},
        carga={"u-ana": {"pendentes": 4, "atrasadas": 1}},
        mudancas_por_dia={"2026-10-06": 3},
        concluidas_por_dia={"2026-10-06": 2, "2026-10-08": 5},
        fases=FASES,
        filtros=_filtros(),
        truncado=False,
        agora=AGORA,
    )
    base.update(kw)
    return er.montar_relatorio(**base)


class TestAMontagem:
    def test_cada_pessoa_leva_os_seus_numeros(self):
        r = _montar()
        ana = next(u for u in r["users"] if u["user_id"] == "u-ana")
        assert (ana["phase_changes"], ana["processes_moved"]) == (5, 3)
        assert (ana["tasks_completed"], ana["tasks_pending"], ana["tasks_overdue"]) == (2, 4, 1)

    def test_quem_nao_fez_nada_tem_zeros(self):
        r = _montar(por_pessoa={}, concluidas={}, carga={})
        rui = next(u for u in r["users"] if u["user_id"] == "u-rui")
        assert (rui["phase_changes"], rui["tasks_completed"], rui["tasks_pending"]) == (0, 0, 0)

    def test_historico_desligado_mostra_traco_e_nao_zero(self):
        """Um 0 diz «não fez nada»; a verdade é «não se regista»."""
        r = _montar()
        ze = next(u for u in r["users"] if u["user_id"] == "u-zé")
        assert ze["phase_changes"] is None and ze["processes_moved"] is None
        assert ze["historico_silenciado"] is True
        assert ze["tasks_completed"] == 1, "as tarefas continuam a contar"

    def test_o_silenciado_nao_entra_nas_somas_de_fases(self):
        r = _montar(por_pessoa={"u-zé": {"processos": 9, "mudancas": 9}})
        assert r["summary"]["total_phase_changes"] == 0

    def test_o_resumo_soma_as_pessoas(self):
        s = _montar()["summary"]
        assert s == {
            "total_users": 3,
            "total_phase_changes": 6,
            "total_processes_moved": 4,
            "total_tasks_completed": 10,
            "total_tasks_pending": 4,
            "total_tasks_overdue": 1,
        }

    def test_ordena_por_processos_movidos_depois_tarefas_depois_nome(self):
        nomes = [u["name"] for u in _montar()["users"]]
        assert nomes == ["Ana", "Rui", "Zé"]

    def test_as_fases_vem_com_o_rotulo_do_motor(self):
        r = _montar()
        assert r["por_fase"][0] == {"fase": "aprovado", "rotulo": "Aprovado", "n": 5}
        ana = next(u for u in r["users"] if u["user_id"] == "u-ana")
        assert [f["rotulo"] for f in ana["por_fase"]] == ["Aprovado", "Fase Documental"]

    def test_uma_fase_desconhecida_aparece_legivel_em_vez_de_desaparecer(self):
        r = _montar(por_fase_e_pessoa=[{"_id": {"user_id": "u-ana", "fase": "fase_nova_x"}, "n": 2}])
        assert r["por_fase"][0]["rotulo"] == "Fase nova x"

    def test_o_periodo_vem_inclusivo_nos_dois_extremos(self):
        r = _montar()
        assert r["start_date"] == "2026-10-05" and r["end_date"] == "2026-10-11"
        assert r["period_end"].startswith("2026-10-11T23:59:59")

    def test_a_serie_diaria_tem_um_ponto_por_dia_com_zeros(self):
        serie = _montar()["serie_diaria"]
        assert [d["dia"] for d in serie][0] == "2026-10-05"
        assert len(serie) == 7
        assert serie[1] == {"dia": "2026-10-06", "mudancas_de_fase": 3, "tarefas_concluidas": 2}
        assert serie[0] == {"dia": "2026-10-05", "mudancas_de_fase": 0, "tarefas_concluidas": 0}

    def test_a_serie_e_omitida_em_periodos_longos(self):
        r = _montar(filtros=_filtros("2026-01-01", "2026-10-09"))
        assert r["serie_diaria"] == [] and r["serie_omitida"] is True

    def test_diz_se_a_lista_foi_cortada(self):
        assert _montar(truncado=True)["truncado"] is True

    def test_as_notas_de_criterio_acompanham_o_relatorio(self):
        notas = " ".join(_montar()["notas"])
        assert "concluiu" in notas and "Indexação" in notas


# ════════════════════════════════════════════════════════════════════
# A ORQUESTRAÇÃO — com a costura substituída
# ════════════════════════════════════════════════════════════════════

class _Mundo:
    """Substitui as costuras de IO e regista o que foi pedido."""

    def __init__(self, utilizadores=None, linhas=None):
        self.utilizadores = UTILIZADORES if utilizadores is None else utilizadores
        self.linhas = linhas or {}
        self.pipelines: list[tuple[str, list]] = []
        self.tempos: list[int] = []
        self.pedidos_de_utilizadores: list[er.Filtros] = []

    async def ler_utilizadores(self, base, ambito, filtros):
        self.pedidos_de_utilizadores.append(filtros)
        return list(self.utilizadores)

    async def correr(self, coluna, pipeline, max_time_ms):
        nome = getattr(coluna, "_nome", "?")
        self.pipelines.append((nome, pipeline))
        self.tempos.append(max_time_ms)
        return list(self.linhas.get(len(self.pipelines), []))


class _Coluna:
    def __init__(self, nome):
        self._nome = nome


@pytest.fixture
def mundo():
    m = _Mundo()
    base = type("DB", (), {"history": _Coluna("history"), "tasks": _Coluna("tasks")})()
    with patch.object(er, "_ler_utilizadores", m.ler_utilizadores), \
            patch.object(er, "_correr", m.correr), \
            patch.object(er, "db", base), \
            patch("services.workflow_phases.carregar_fases", AsyncMock(return_value=FASES)):
        yield m


AMBITO = er.Ambito(chave="rede-a", condicao_de_tarefas={"network_id": {"$in": ["rede_a"]}})


class TestAOrquestracao:
    @pytest.mark.asyncio
    async def test_corre_seis_agregacoes_em_serie_e_todas_com_tecto_de_tempo(self, mundo):
        await er.gerar_relatorio(AMBITO, _filtros(), agora=AGORA)
        assert [n for n, _ in mundo.pipelines] == ["history", "history", "tasks", "tasks", "history", "tasks"]
        assert len(mundo.tempos) == 6 and all(t > 0 for t in mundo.tempos)

    @pytest.mark.asyncio
    async def test_o_tecto_de_tempo_vem_do_ambiente(self, mundo, monkeypatch):
        monkeypatch.setenv("EXEC_REPORT_MAX_TIME_MS", "2500")
        await er.gerar_relatorio(AMBITO, _filtros(), agora=AGORA)
        assert set(mundo.tempos) == {2500}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("lixo", ["abc", "-5", "0", ""])
    async def test_um_tecto_invalido_cai_no_valor_por_omissao(self, mundo, monkeypatch, lixo):
        """Nunca «sem tecto»: um valor inválido não pode desligar a protecção."""
        monkeypatch.setenv("EXEC_REPORT_MAX_TIME_MS", lixo)
        await er.gerar_relatorio(AMBITO, _filtros(), agora=AGORA)
        assert set(mundo.tempos) == {10_000}

    @pytest.mark.asyncio
    async def test_as_pipelines_so_perguntam_pelas_pessoas_do_ambito(self, mundo):
        await er.gerar_relatorio(AMBITO, _filtros(), agora=AGORA)
        for _, pipeline in mundo.pipelines:
            assert json.dumps(pipeline).count('"u-ana"') >= 1
            assert '"u-intruso"' not in json.dumps(pipeline)

    @pytest.mark.asyncio
    async def test_a_condicao_de_rede_chega_as_tarefas_e_nao_ao_historico(self, mundo):
        await er.gerar_relatorio(AMBITO, _filtros(), agora=AGORA)
        for nome, pipeline in mundo.pipelines:
            tem_rede = "rede_a" in json.dumps(pipeline)
            assert tem_rede == (nome == "tasks"), nome

    @pytest.mark.asyncio
    async def test_sem_pessoas_nao_se_corre_nenhuma_agregacao(self, mundo):
        mundo.utilizadores = []
        r = await er.gerar_relatorio(AMBITO, _filtros(), agora=AGORA)
        assert mundo.pipelines == []
        assert r["users"] == [] and r["summary"]["total_users"] == 0

    @pytest.mark.asyncio
    async def test_periodo_longo_dispensa_a_serie_diaria(self, mundo):
        await er.gerar_relatorio(AMBITO, _filtros("2026-01-01", "2026-10-09"), agora=AGORA)
        assert len(mundo.pipelines) == 4

    @pytest.mark.asyncio
    async def test_o_limite_dos_atrasos_e_hoje_se_o_periodo_ainda_nao_acabou(self, mundo):
        await er.gerar_relatorio(AMBITO, _filtros("2026-10-05", "2026-10-11"), agora=AGORA)
        carga = next(p for n, p in mundo.pipelines if n == "tasks" and "$unwind" in json.dumps(p))
        assert "2026-10-09" in json.dumps(carga[3])

    @pytest.mark.asyncio
    async def test_o_limite_dos_atrasos_e_o_fim_se_o_periodo_ja_acabou(self, mundo):
        await er.gerar_relatorio(AMBITO, _filtros("2026-09-28", "2026-10-04"), agora=AGORA)
        carga = next(p for n, p in mundo.pipelines if n == "tasks" and "$unwind" in json.dumps(p))
        assert "2026-10-05" in json.dumps(carga[3])  # o dia a seguir ao fim

    @pytest.mark.asyncio
    async def test_mais_pessoas_do_que_o_tecto_diz_que_cortou(self, mundo, monkeypatch):
        monkeypatch.setattr(er, "LIMITE_DE_UTILIZADORES", 2)
        r = await er.gerar_relatorio(AMBITO, _filtros(), agora=AGORA)
        assert r["truncado"] is True and r["summary"]["total_users"] == 2


class TestOTimeout:
    @pytest.mark.asyncio
    async def test_um_corte_por_tempo_vira_erro_visivel_e_nunca_um_relatorio_vazio(self):
        from pymongo.errors import ExecutionTimeout

        class _Cursor:
            async def to_list(self, _):
                raise ExecutionTimeout("operation exceeded time limit")

        class _Coluna:
            def aggregate(self, pipeline, **kwargs):
                assert kwargs == {"allowDiskUse": True, "maxTimeMS": 123}
                return _Cursor()

        with pytest.raises(er.RelatorioIndisponivel) as exc:
            await er._correr(_Coluna(), [{"$match": {}}], 123)
        assert "demorou demasiado" in str(exc.value)

    @pytest.mark.asyncio
    async def test_outra_falha_da_bd_tambem_e_erro_e_nao_vazio(self):
        from pymongo.errors import OperationFailure

        class _Coluna:
            def aggregate(self, pipeline, **kwargs):
                raise OperationFailure("boom")

        with pytest.raises(er.RelatorioIndisponivel):
            await er._correr(_Coluna(), [], 1)

    @pytest.mark.asyncio
    async def test_um_corte_a_meio_nao_deixa_o_resultado_em_cache(self, mundo):
        original = mundo.correr
        chamadas = {"n": 0}

        async def a_falhar(coluna, pipeline, tempo):
            chamadas["n"] += 1
            if chamadas["n"] == 3:
                raise er.RelatorioIndisponivel("x")
            return await original(coluna, pipeline, tempo)

        with patch.object(er, "_correr", a_falhar):
            with pytest.raises(er.RelatorioIndisponivel):
                await er.gerar_relatorio(AMBITO, _filtros(), agora=AGORA)
        chamadas["n"] = 100
        with patch.object(er, "_correr", a_falhar):
            r = await er.gerar_relatorio(AMBITO, _filtros(), agora=AGORA)
        assert r["summary"]["total_users"] == 3


class TestACache:
    @pytest.mark.asyncio
    async def test_o_segundo_pedido_igual_nao_volta_a_agregar(self, mundo):
        await er.gerar_relatorio(AMBITO, _filtros(), agora=AGORA)
        n = len(mundo.pipelines)
        await er.gerar_relatorio(AMBITO, _filtros(), agora=AGORA)
        assert len(mundo.pipelines) == n

    @pytest.mark.asyncio
    async def test_a_chave_inclui_o_ambito(self, mundo):
        """Um filtro de rede sobre uma cache partilhada é teatro."""
        await er.gerar_relatorio(AMBITO, _filtros(), agora=AGORA)
        n = len(mundo.pipelines)
        outro = er.Ambito(chave="rede-b", condicao_de_tarefas={"network_id": {"$in": ["rede_b"]}})
        await er.gerar_relatorio(outro, _filtros(), agora=AGORA)
        assert len(mundo.pipelines) == 2 * n

    @pytest.mark.asyncio
    @pytest.mark.parametrize("variacao", [
        dict(user_ids=("u-ana",)),
        dict(papeis=("consultor",)),
        dict(com_movimentos=True),
    ])
    async def test_a_chave_inclui_cada_filtro(self, mundo, variacao):
        await er.gerar_relatorio(AMBITO, _filtros(), agora=AGORA)
        n = len(mundo.pipelines)
        with patch.object(er, "_ler_movimentos", AsyncMock(return_value=[])):
            await er.gerar_relatorio(AMBITO, _filtros(**variacao), agora=AGORA)
        assert len(mundo.pipelines) > n

    @pytest.mark.asyncio
    async def test_o_periodo_faz_parte_da_chave(self, mundo):
        await er.gerar_relatorio(AMBITO, _filtros(), agora=AGORA)
        n = len(mundo.pipelines)
        await er.gerar_relatorio(AMBITO, _filtros("2026-09-28", "2026-10-04"), agora=AGORA)
        assert len(mundo.pipelines) > n

    @pytest.mark.asyncio
    async def test_usar_cache_false_ignora_a_cache(self, mundo):
        await er.gerar_relatorio(AMBITO, _filtros(), agora=AGORA)
        n = len(mundo.pipelines)
        await er.gerar_relatorio(AMBITO, _filtros(), usar_cache=False, agora=AGORA)
        assert len(mundo.pipelines) == 2 * n

    @pytest.mark.asyncio
    async def test_o_chamador_nao_estraga_a_cache_ao_alterar_o_resultado(self, mundo):
        r1 = await er.gerar_relatorio(AMBITO, _filtros(), agora=AGORA)
        r1["users"].clear()
        r2 = await er.gerar_relatorio(AMBITO, _filtros(), agora=AGORA)
        assert len(r2["users"]) == 3

    @pytest.mark.asyncio
    async def test_a_cache_expira(self, mundo, monkeypatch):
        await er.gerar_relatorio(AMBITO, _filtros(), agora=AGORA)
        n = len(mundo.pipelines)
        monkeypatch.setattr(er.time, "monotonic", lambda: 10**9)
        await er.gerar_relatorio(AMBITO, _filtros(), agora=AGORA)
        assert len(mundo.pipelines) == 2 * n


class TestOsUtilizadoresDoRelatorio:
    @pytest.mark.asyncio
    async def test_a_indexacao_nunca_entra(self):
        """Restrição de segurança: as acções da Indexação não geram registo, e
        uma linha de zeros num relatório executivo diria «não fez nada»."""
        capturado = {}

        class _Cursor:
            def sort(self, *a, **k):
                return self

            async def to_list(self, _):
                return []

        class _Users:
            def find(self, query, projecao):
                capturado["query"] = query
                return _Cursor()

        base = type("DB", (), {"users": _Users()})()
        await er._ler_utilizadores(base, er.Ambito(chave="x"), _filtros())
        texto = json.dumps(capturado["query"])
        assert '{"role": {"$ne": "indexacao"}}' in texto
        assert "indexacao" not in json.dumps(er.PAPEIS_DO_RELATORIO)

    @pytest.mark.asyncio
    async def test_pedir_so_a_indexacao_nao_devolve_nada(self):
        assert await er._ler_utilizadores(object(), er.Ambito(chave="x"), _filtros(papeis=("indexacao",))) == []

    @pytest.mark.asyncio
    async def test_os_filtros_so_estreitam(self):
        capturado = {}

        class _Cursor:
            def sort(self, *a, **k):
                return self

            async def to_list(self, _):
                return []

        class _Users:
            def find(self, query, projecao):
                capturado["query"] = query
                return _Cursor()

        ambito = er.Ambito(chave="x", consulta_de_utilizadores={"id": {"$in": ["u-ana", "u-rui"]}})
        base = type("DB", (), {"users": _Users()})()
        await er._ler_utilizadores(base, ambito, _filtros(user_ids=("u-ana", "u-intruso"), papeis=("consultor",)))
        condicoes = capturado["query"]["$and"]
        # O âmbito da rede continua lá: um id fora dele não alarga nada.
        assert ambito.consulta_de_utilizadores in condicoes
        assert {"id": {"$in": ["u-ana", "u-intruso"]}} in condicoes


class TestOAmbito:
    @pytest.mark.asyncio
    async def test_sem_utilizador_e_o_consolidado_e_avisa(self, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            ambito = await er.resolver_ambito(None)
        assert ambito.chave == "global" and ambito.condicao_de_tarefas == {}
        assert any("âmbito global" in r.message for r in caplog.records)

    def test_a_cache_e_o_registo_nao_misturam_ambitos_de_empresas_diferentes_sem_rede(self):
        """Em dev (sem rede de omissão) duas empresas sem rede não partilham chave."""
        from services.tenant_network import TenantScope

        def chave(scope):
            import hashlib
            assinatura = "|".join([
                ",".join(sorted(scope.network_ids)),
                ",".join(sorted(scope.company_ids)),
                ",".join(sorted(scope.company_names)),
                "1" if scope.inclui_rede_de_omissao else "0",
            ])
            return hashlib.sha1(assinatura.encode()).hexdigest()[:16]

        a = TenantScope(company_ids=("c1",), company_names=("A",))
        b = TenantScope(company_ids=("c2",), company_names=("B",))
        assert chave(a) != chave(b)
        # E a fórmula do código é esta (não uma cópia que divirja):
        fonte = (BACKEND / "services" / "executive_report.py").read_text(encoding="utf-8")
        assert '",".join(sorted(scope.company_ids))' in fonte


class TestOsMovimentos:
    @pytest.mark.asyncio
    async def test_so_os_processos_do_ambito_e_sem_nomes_de_clientes(self):
        from services.tenant_network import TenantScope

        scope = TenantScope(network_ids=("rede_a",))
        ambito = er.Ambito(chave="a", scope=scope)
        linhas = [
            {"user_id": "u-ana", "process_id": "p-a", "old_value": "fase_documental",
             "new_value": "aprovado", "created_at": "2026-10-06T10:00:00+00:00"},
            {"user_id": "u-ana", "process_id": "p-b", "old_value": "aprovado",
             "new_value": "fase_documental", "created_at": "2026-10-06T11:00:00+00:00"},
            {"user_id": "u-ana", "process_id": "p-fantasma", "old_value": "x",
             "new_value": "y", "created_at": "2026-10-06T12:00:00+00:00"},
        ]
        processos = {
            "p-a": {"id": "p-a", "process_number": 12, "client_name": "Silva", "network_id": "rede_a"},
            "p-b": {"id": "p-b", "process_number": 13, "client_name": "Souza", "network_id": "rede_b"},
        }
        with patch.object(er, "_ler_processos", AsyncMock(return_value=processos)):
            saida = await er.montar_movimentos(None, linhas, {"u-ana": "Ana"}, FASES, ambito)
        assert [m["process_id"] for m in saida] == ["p-a"]
        assert saida[0]["para_rotulo"] == "Aprovado" and saida[0]["user_name"] == "Ana"
        # O nome do cliente NUNCA entra no que é devolvido nem guardado em registo.
        assert "Silva" not in json.dumps(saida) and "client_name" not in saida[0]

    @pytest.mark.asyncio
    async def test_o_consolidado_nao_filtra_por_processo(self):
        linhas = [{"user_id": "u", "process_id": "p-b", "old_value": "a", "new_value": "b", "created_at": "x"}]
        with patch.object(er, "_ler_processos", AsyncMock(return_value={"p-b": {"id": "p-b", "network_id": "rede_b"}})):
            saida = await er.montar_movimentos(None, linhas, {}, FASES, er.Ambito(chave="global"))
        assert len(saida) == 1

    @pytest.mark.asyncio
    async def test_o_limite_de_movimentos(self, monkeypatch):
        monkeypatch.setattr(er, "LIMITE_DE_MOVIMENTOS", 2)
        linhas = [{"user_id": "u", "process_id": "p", "old_value": "a", "new_value": "b", "created_at": str(i)} for i in range(5)]
        with patch.object(er, "_ler_processos", AsyncMock(return_value={"p": {"id": "p"}})):
            saida = await er.montar_movimentos(None, linhas, {}, FASES, er.Ambito(chave="global"))
        assert len(saida) == 2

    @pytest.mark.asyncio
    async def test_quem_tem_o_historico_desligado_nao_e_perguntado(self, mundo):
        pedido = {}

        async def ler(base, ids, a, b, t):
            pedido["ids"] = ids
            return []

        with patch.object(er, "_ler_movimentos", ler):
            await er.gerar_relatorio(AMBITO, _filtros(com_movimentos=True), agora=AGORA)
        assert "u-zé" not in pedido["ids"] and "u-ana" in pedido["ids"]


class TestAFachada:
    def test_o_analytics_service_ja_nao_tem_pipelines_proprias(self):
        fonte = (BACKEND / "services" / "analytics_service.py").read_text(encoding="utf-8")
        arvore = ast.parse(fonte)
        assert "task_logs" not in fonte, "as «tarefas» do relatório são db.tasks, não os trabalhos de fundo"
        corpo = ast.unparse(next(
            n for n in arvore.body
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "generate_weekly_team_report"
        ))
        assert "executive_report" in corpo
        assert "aggregate" not in corpo
        assert "gerar_relatorio" in corpo
