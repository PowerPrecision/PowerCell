"""Política de tentativas dos scrapers governamentais (Finanças / Seg. Social).

Os dois scrapers tinham cada um o seu ciclo de tentativas, escrito à mão, e os
dois com os mesmos defeitos (Bloco 5, pontos 8 e 9):

* **Repetiam o que não deve ser repetido.** `mfa_timeout` e
  `mfa_codigo_incorreto` não estavam na lista de erros sem repetição, pelo que
  um cliente que demorasse mais de 2 minutos a escrever o SMS levava um
  segundo login — e um segundo SMS —, e um código errado era seguido de novo
  login e de novo código. Cada tentativa é uma autenticação num serviço do
  Estado com a conta DO CLIENTE: repetir um login que passou por MFA é fazer
  o cidadão receber SMS que não pediu e arriscar o bloqueio da conta dele.
* **Dormiam duas vezes.** Um resultado falhado dormia o atraso dentro do `try`
  e voltava a dormir no fim do ciclo (5 s viravam 10, 15 viravam 30).
* **Não tinham orçamento total.** Três tentativas de 5 minutos mais a espera
  pelo semáforo davam mais de 16 minutos com o cliente a olhar para um ecrã
  «a processar». A espera pelo semáforo era ilimitada.
* **O MFA comia o orçamento da extracção.** Os 120 s à espera do SMS contavam
  para os 300 s da tentativa, e um cliente lento deixava os documentos sem
  tempo.

Este módulo é o ponto único dessa política. Não sabe nada de Playwright: recebe
a corrotina da tentativa e devolve um resultado — `ScraperResult` ou qualquer
objecto com `.success` e `.error`.
"""
from __future__ import annotations

import asyncio
import contextvars
import logging
import time
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

# Tempo que o cliente tem para escrever o SMS (segundos). Fora do orçamento da
# extracção: ver `orcamento_da_tentativa`.
MFA_ESPERA_SEGUNDOS = 120

# Orçamento de UMA tentativa sem a espera do MFA (login + navegação + 2 PDFs).
ORCAMENTO_BASE_SEGUNDOS = 300

# Orçamento total do pedido, do primeiro login ao último resultado. Passado
# isto não se começa outra tentativa: o cliente tem um ecrã à espera.
ORCAMENTO_TOTAL_SEGUNDOS = 12 * 60

# Quanto se espera pelo semáforo antes de dizer «ocupado». Sem isto, uma fila
# de pedidos deixava o último a olhar para «a processar» sem fim.
ESPERA_PELO_SEMAFORO_SEGUNDOS = 5 * 60

# Só se repete o que é falha de REDE ou de TEMPO do lado do portal. Tudo o resto
# é um veredicto: repeti-lo dá o mesmo resultado ou, pior, outro SMS.
ERROS_QUE_JUSTIFICAM_REPETIR = frozenset({"timeout", "timeout_login", "unexpected_error"})

# Nunca se repete depois de o portal ter pedido MFA: um segundo login pede um
# SMS novo e invalida o que o cliente acabou de escrever.
ATRASOS_ENTRE_TENTATIVAS = (5, 15)
MAX_TENTATIVAS = 3

# Mutável de propósito: a tentativa corre numa Task filha (`wait_for`), cujas
# alterações a um `ContextVar` não voltam ao pai — mas um objecto partilhado sim.
_estado_da_tentativa: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar(
    "gov_fetch_estado_da_tentativa", default=None
)


def marcar_mfa_pedido() -> None:
    """Regista que o portal pediu MFA nesta execução (chamado por quem espera o SMS)."""
    estado = _estado_da_tentativa.get()
    if estado is not None:
        estado["mfa"] = True


def orcamento_da_tentativa() -> int:
    """Segundos para UMA tentativa: a extracção mais a espera pelo SMS."""
    return ORCAMENTO_BASE_SEGUNDOS + MFA_ESPERA_SEGUNDOS


def deve_repetir(erro: Optional[str], *, mfa_pedido: bool) -> bool:
    """Decide se um resultado falhado justifica outro login."""
    if mfa_pedido:
        return False
    erro = erro or ""
    # `TimeoutError` do Playwright chega com o nome da classe como código.
    return erro in ERROS_QUE_JUSTIFICAM_REPETIR or erro.endswith("TimeoutError")


class _Resultado:
    """Resultado mínimo para os caminhos em que o scraper nem chegou a correr."""

    def __init__(self, error: str, step_failed: str):
        self.success = False
        self.documents: list = []
        self.error = error
        self.screenshot_b64 = None
        self.step_failed = step_failed


async def executar_com_tentativas(
    tentativa: Callable[[], Awaitable[Any]],
    *,
    etiqueta: str,
    semaforo: asyncio.Semaphore,
    fabrica_de_resultado: Callable[[str, str], Any] = _Resultado,
    process_id: Optional[str] = None,
    relogio: Callable[[], float] = time.monotonic,
    dormir: Callable[[float], Awaitable[Any]] = asyncio.sleep,
) -> Any:
    """Corre `tentativa` sob o semáforo, com orçamento e repetição prudente.

    Nunca levanta (excepto cancelamento): toda a falha volta como resultado
    com `error` e `step_failed`, que é o que o resto do pipeline sabe ler.
    O código MFA que tenha ficado em cache é sempre limpo à saída.
    """
    estado = {"mfa": False}
    token = _estado_da_tentativa.set(estado)
    inicio = relogio()
    ultimo: Any = None
    try:
        try:
            await asyncio.wait_for(semaforo.acquire(), timeout=ESPERA_PELO_SEMAFORO_SEGUNDOS)
        except asyncio.TimeoutError:
            logger.warning(
                "[GOV_SCRAPER] %s: semáforo ocupado há mais de %ss — pedido recusado.",
                etiqueta, ESPERA_PELO_SEMAFORO_SEGUNDOS,
            )
            return fabrica_de_resultado("scraper_ocupado", "semaphore_wait")

        try:
            for numero in range(MAX_TENTATIVAS):
                restante = ORCAMENTO_TOTAL_SEGUNDOS - (relogio() - inicio)
                if numero > 0 and restante < orcamento_da_tentativa() / 2:
                    logger.warning(
                        "[GOV_SCRAPER] %s: orçamento total esgotado (%.0fs restantes) — "
                        "sem nova tentativa.", etiqueta, restante,
                    )
                    break
                try:
                    resultado = await asyncio.wait_for(
                        tentativa(), timeout=min(orcamento_da_tentativa(), max(restante, 1))
                    )
                    ultimo = resultado
                    if getattr(resultado, "success", False):
                        return resultado
                    erro = getattr(resultado, "error", None)
                except asyncio.TimeoutError:
                    logger.error("[GOV_SCRAPER] %s: tentativa %d excedeu o orçamento.", etiqueta, numero + 1)
                    ultimo = fabrica_de_resultado("timeout", "global_timeout")
                    erro = "timeout"
                except MemoryError as exc:
                    logger.error("[GOV_SCRAPER] %s: memória insuficiente: %s", etiqueta, exc)
                    return fabrica_de_resultado("scraper_unavailable", "memory_error")
                except Exception as exc:  # um scraper de terceiros nunca derruba o pedido
                    logger.error(
                        "[GOV_SCRAPER] %s: erro inesperado (%s).", etiqueta, type(exc).__name__,
                        exc_info=True,
                    )
                    ultimo = fabrica_de_resultado(type(exc).__name__, "unexpected_error")
                    erro = "unexpected_error"

                if numero + 1 >= MAX_TENTATIVAS or not deve_repetir(erro, mfa_pedido=estado["mfa"]):
                    break

                atraso = ATRASOS_ENTRE_TENTATIVAS[min(numero, len(ATRASOS_ENTRE_TENTATIVAS) - 1)]
                logger.info(
                    "[GOV_SCRAPER] %s: nova tentativa %d/%d em %ss (erro: %s).",
                    etiqueta, numero + 2, MAX_TENTATIVAS, atraso, erro,
                )
                await dormir(atraso)
        finally:
            semaforo.release()

        return ultimo or fabrica_de_resultado("unknown", "all_retries_exhausted")
    finally:
        _estado_da_tentativa.reset(token)
        if process_id:
            try:
                from services.mfa_cache import delete_mfa_code

                await delete_mfa_code(process_id)
            except Exception as exc:  # limpeza best-effort, nunca esconde o resultado
                logger.warning("[GOV_SCRAPER] Limpeza do código MFA falhou: %s", type(exc).__name__)
