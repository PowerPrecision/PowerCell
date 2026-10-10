"""Política de tentativas dos scrapers governamentais (Bloco 5, pontos 8 e 9).

O oráculo é o comportamento observável de `executar_com_tentativas`: quantas
vezes a tentativa corre, quanto se dorme e o que sai. Nada é reimplementado
aqui — o relógio e o `sleep` são os únicos duplos.
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from services import gov_fetch_policy as politica


class Res:
    def __init__(self, success=False, error=None, step_failed=None):
        self.success = success
        self.error = error
        self.step_failed = step_failed
        self.documents = []
        self.screenshot_b64 = None


def fabrica(erro, passo):
    return Res(False, erro, passo)


class Sequencia:
    """Devolve um resultado por chamada e conta as chamadas."""

    def __init__(self, *resultados, antes=None):
        self.resultados = list(resultados)
        self.chamadas = 0
        self.antes = antes

    async def __call__(self):
        self.chamadas += 1
        if self.antes:
            self.antes()
        item = self.resultados[min(self.chamadas - 1, len(self.resultados) - 1)]
        if isinstance(item, BaseException):
            raise item
        return item


class Dorminhoco:
    def __init__(self):
        self.pausas = []

    async def __call__(self, segundos):
        self.pausas.append(segundos)


@pytest.fixture(autouse=True)
def _sem_redis():
    with patch("services.mfa_cache.delete_mfa_code", new_callable=AsyncMock) as apagar:
        yield apagar


async def correr(tentativa, **kw):
    dormir = kw.pop("dormir", Dorminhoco())
    resultado = await politica.executar_com_tentativas(
        tentativa,
        etiqueta="teste",
        semaforo=asyncio.Semaphore(1),
        fabrica_de_resultado=fabrica,
        dormir=dormir,
        **kw,
    )
    return resultado, dormir


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "erro",
    [
        "credenciais_invalidas",
        "mfa_requerido",
        "mfa_timeout",
        "mfa_codigo_incorreto",
        "mfa_error",
        "mfa_no_input",
        "sem_documentos",
        "selector_desatualizado",
    ],
)
async def test_um_veredicto_nao_se_repete(erro):
    """Repetir um veredicto dá o mesmo resultado — ou, no MFA, outro SMS ao cliente."""
    seq = Sequencia(Res(False, erro))
    resultado, dormir = await correr(seq)
    assert seq.chamadas == 1
    assert resultado.error == erro
    assert dormir.pausas == []


@pytest.mark.asyncio
async def test_um_timeout_repete_e_dorme_UMA_vez_por_repeticao():
    """A cópia anterior dormia o atraso dentro do `try` e outra vez no fim."""
    seq = Sequencia(Res(False, "timeout"), Res(False, "timeout"), Res(True))
    resultado, dormir = await correr(seq)
    assert seq.chamadas == 3
    assert resultado.success is True
    assert dormir.pausas == [5, 15]


@pytest.mark.asyncio
async def test_depois_de_pedir_MFA_nunca_se_repete_mesmo_num_timeout():
    """Um segundo login pede SMS novo e invalida o código que o cliente escreveu."""
    def pede_mfa():
        politica.marcar_mfa_pedido()

    seq = Sequencia(Res(False, "timeout"), Res(True), antes=pede_mfa)
    resultado, dormir = await correr(seq)
    assert seq.chamadas == 1
    assert resultado.error == "timeout"
    assert dormir.pausas == []


@pytest.mark.asyncio
async def test_a_marca_de_MFA_vem_de_dentro_da_tentativa_mesmo_correndo_numa_task_filha():
    """`wait_for` corre a tentativa numa Task: a marca tem de atravessar essa fronteira."""
    async def tentativa():
        politica.marcar_mfa_pedido()
        return Res(False, "timeout")

    chamadas = {"n": 0}

    async def contada():
        chamadas["n"] += 1
        return await tentativa()

    resultado, dormir = await correr(contada)
    assert chamadas["n"] == 1
    assert dormir.pausas == []


@pytest.mark.asyncio
async def test_a_marca_de_MFA_de_um_pedido_nao_contamina_o_seguinte():
    async def com_mfa():
        politica.marcar_mfa_pedido()
        return Res(False, "mfa_timeout")

    await correr(com_mfa)
    seq = Sequencia(Res(False, "timeout"), Res(True))
    resultado, _ = await correr(seq)
    assert seq.chamadas == 2 and resultado.success


@pytest.mark.asyncio
async def test_o_orcamento_total_impede_nova_tentativa():
    relogio = {"t": 0.0}

    def agora():
        return relogio["t"]

    def gasta():
        relogio["t"] += politica.ORCAMENTO_TOTAL_SEGUNDOS - 10  # sobra quase nada

    seq = Sequencia(Res(False, "timeout"), Res(True), antes=gasta)
    resultado, dormir = await correr(seq, relogio=agora)
    assert seq.chamadas == 1
    assert resultado.error == "timeout"


@pytest.mark.asyncio
async def test_excepcao_inesperada_nunca_sobe_e_e_classificada():
    seq = Sequencia(RuntimeError("boom"), RuntimeError("boom"), RuntimeError("boom"))
    resultado, _ = await correr(seq)
    assert resultado.success is False
    assert resultado.error == "RuntimeError"
    assert resultado.step_failed == "unexpected_error"


@pytest.mark.asyncio
async def test_falta_de_memoria_nao_se_repete():
    seq = Sequencia(MemoryError("sem RAM"), Res(True))
    resultado, _ = await correr(seq)
    assert seq.chamadas == 1
    assert resultado.error == "scraper_unavailable"
    assert resultado.step_failed == "memory_error"


@pytest.mark.asyncio
async def test_semaforo_ocupado_responde_ocupado_em_vez_de_esperar_para_sempre():
    semaforo = asyncio.Semaphore(1)
    await semaforo.acquire()  # outro scraper em curso
    seq = Sequencia(Res(True))
    with patch.object(politica, "ESPERA_PELO_SEMAFORO_SEGUNDOS", 0.05):
        resultado = await politica.executar_com_tentativas(
            seq, etiqueta="t", semaforo=semaforo, fabrica_de_resultado=fabrica
        )
    assert resultado.error == "scraper_ocupado"
    assert seq.chamadas == 0


@pytest.mark.asyncio
async def test_o_semaforo_e_libertado_mesmo_com_falha():
    semaforo = asyncio.Semaphore(1)
    seq = Sequencia(RuntimeError("x"))
    await politica.executar_com_tentativas(
        seq, etiqueta="t", semaforo=semaforo, fabrica_de_resultado=fabrica, dormir=Dorminhoco()
    )
    assert not semaforo.locked()


@pytest.mark.asyncio
async def test_o_codigo_MFA_em_cache_e_sempre_limpo_a_saida(_sem_redis):
    seq = Sequencia(Res(True))
    await correr(seq, process_id="proc-1")
    _sem_redis.assert_awaited_once_with("proc-1")


def test_a_espera_do_MFA_nao_come_o_orcamento_da_extraccao():
    assert politica.orcamento_da_tentativa() == politica.ORCAMENTO_BASE_SEGUNDOS + politica.MFA_ESPERA_SEGUNDOS
    assert politica.orcamento_da_tentativa() > politica.MFA_ESPERA_SEGUNDOS + 240
