"""D-30 — o health check dos scrapers está ligado ao agendador e ao botão «Forçar execução».

Dois caminhos, duas regras: o AUTOMÁTICO respeita o intervalo mínimo (cada arranque do worker corre
todos os jobs e cada corrida é um login na conta de teste do Estado); o FORÇADO ignora-o (é uma pessoa
a pedir). As duas passam pelo `executar_job` — o registo único de «correr este job».
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

import services.job_executors as je
from services.job_heartbeat import JOBS_POR_CHAVE

BACKEND = Path(__file__).resolve().parents[2]
CHAVE = "gov_scrapers_healthcheck"


class TestRegisto:
    def test_o_job_esta_declarado_no_worker_e_so_em_producao(self):
        job = JOBS_POR_CHAVE[CHAVE]
        assert job["processo"] == "worker" and job["so_em_producao"] is True
        assert job["interval_seconds"] == 86400

    def test_tem_executor_automatico_e_forcado_distintos(self):
        assert CHAVE in je.EXECUTORES and CHAVE in je.EXECUTORES_FORCADOS
        assert je.EXECUTORES[CHAVE] is not je.EXECUTORES_FORCADOS[CHAVE]

    def test_o_que_se_forca_tem_job_declarado(self):
        assert set(je.EXECUTORES_FORCADOS) <= set(je.EXECUTORES)

    def test_pode_ser_forcado(self):
        assert je.pode_ser_forcado(CHAVE) is True


class TestOQueCadaCaminhoChama:
    @pytest.mark.asyncio
    async def test_automatico_respeita_o_intervalo_e_forcado_ignora(self, monkeypatch):
        import services.gov_scrapers_healthcheck as h

        chamadas = []

        async def falso(*, respeitar_intervalo=True, agora=None):
            chamadas.append(respeitar_intervalo)
            return {}

        monkeypatch.setattr(h, "correr_healthcheck", falso)
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setattr("services.job_heartbeat.heartbeat", _heartbeat_nulo)

        await je.executar_job(CHAVE)
        await je.executar_job(CHAVE, forcado=True)
        assert chamadas == [True, False]

    @pytest.mark.asyncio
    async def test_fora_de_producao_nao_se_forca(self, monkeypatch):
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        with pytest.raises(PermissionError):
            await je.executar_job(CHAVE, forcado=True)

    @pytest.mark.asyncio
    async def test_forcado_nos_outros_jobs_corre_o_mesmo_executor(self, monkeypatch):
        corridos = []

        async def falso():
            corridos.append("x")

        monkeypatch.setattr(je, "EXECUTORES", {**je.EXECUTORES, "background_job_monitor": falso})
        monkeypatch.setattr("services.job_heartbeat.heartbeat", _heartbeat_nulo)
        await je.executar_job("background_job_monitor", forcado=True)
        assert corridos == ["x"]


class TestAsLigacoes:
    """O botão chama `forcado=True`; sem isto o botão ficaria preso ao intervalo e «não faria nada»."""

    @staticmethod
    def _chamadas_com_forcado(ficheiro: str) -> list[bool]:
        arvore = ast.parse((BACKEND / ficheiro).read_text(encoding="utf-8"))
        saida = []
        for no in ast.walk(arvore):
            if isinstance(no, ast.Call) and getattr(no.func, "id", "") == "executar_job":
                saida.append(any(k.arg == "forcado" and getattr(k.value, "value", None) is True for k in no.keywords))
        return saida

    def test_o_pedido_forcado_do_worker_pede_forcado(self):
        chamadas = self._chamadas_com_forcado("worker.py")
        assert chamadas.count(True) == 1, "o atendimento de «Forçar execução» tem de usar forcado=True"
        assert chamadas.count(False) == 1, "o laço automático NÃO pode forçar"

    def test_o_endpoint_do_painel_pede_forcado(self):
        assert self._chamadas_com_forcado("services/automation_api_engine.py") == [True]


async def _vazio(*_a, **_k):
    return None


class _heartbeat_nulo:
    def __init__(self, *_a, **_k):
        pass

    async def __aenter__(self):
        return None

    async def __aexit__(self, *_exc):
        return False
