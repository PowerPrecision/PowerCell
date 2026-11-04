"""A IA está disponível? (Nov 2026 — OpenAI sem créditos).

O PEDIDO: «quando a IA não está disponível, bloquear os botões de analisar e extrair até que a IA volte a
estar disponível». Com a conta sem saldo, cada clique lançava dezenas de pedidos pagos-que-não-passam e
terminava em alertas «A IA não conseguiu analisar».

COMO
====
* `call_openai_api` (o funil de todas as chamadas ao modelo) avisa aqui: `registar_sem_creditos()` quando a
  OpenAI responde `insufficient_quota`, `registar_resposta_ok()` quando volta a responder. O estado vive na
  base de dados (`system_flags`, id `ia_openai`) e não em memória, porque a análise e o ecrã podem correr em
  processos diferentes (web e worker).
* `estado_da_ia()` é o que a bancada do Index lê. Enquanto estiver bloqueada, no máximo a cada
  `INTERVALO_DA_SONDA` faz UMA sonda (um pedido de 1 token, em segundo plano): sem ela, com os botões
  desligados, ninguém voltaria a chamar o modelo e o bloqueio nunca saía sozinho depois de carregarem créditos.
* Nunca levanta: um problema aqui não pode impedir uma análise nem a abertura da bancada.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from database import db

logger = logging.getLogger(__name__)

ID_DO_ESTADO = "ia_openai"
INTERVALO_DA_SONDA = timedelta(minutes=3)
MENSAGEM_SEM_CREDITOS = (
    "A IA está sem créditos: «Analisar» e «Extrair dados» ficam bloqueados até o administrador carregar "
    "créditos na conta OpenAI. O resto da bancada (incluindo «Marcar como Indexado») funciona normalmente."
)

#: Evita uma escrita na base de dados a cada resposta boa: só se limpa o que este processo sabe estar marcado
#: (ou não sabe — `None` — e então confirma-se uma vez).
_marcado_localmente: Optional[bool] = None
_sonda_em_curso: Optional[asyncio.Task] = None


def _agora() -> datetime:
    return datetime.now(timezone.utc)


#: Tecto de cada escrita do estado: isto vem do caminho de uma chamada ao modelo e nunca a pode prender.
TECTO_DA_ESCRITA = 3.0


async def registar_sem_creditos() -> None:
    global _marcado_localmente
    try:
        agora = _agora().isoformat()
        await asyncio.wait_for(db.system_flags.update_one(
            {"id": ID_DO_ESTADO},
            {"$set": {"id": ID_DO_ESTADO, "sem_creditos": True, "desde": agora, "verificado_em": agora}},
            upsert=True,
        ), timeout=TECTO_DA_ESCRITA)
        _marcado_localmente = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("[IA] Estado «sem créditos» não gravado: %s", exc)


async def _limpar() -> None:
    try:
        r = await asyncio.wait_for(db.system_flags.update_one(
            {"id": ID_DO_ESTADO, "sem_creditos": True},
            {"$set": {"sem_creditos": False, "voltou_em": _agora().isoformat()}},
        ), timeout=TECTO_DA_ESCRITA)
        if getattr(r, "modified_count", 0):
            logger.info("[IA] A OpenAI voltou a responder: análise desbloqueada.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("[IA] Estado da IA não actualizado: %s", exc)


async def registar_resposta_ok() -> None:
    """Uma resposta boa desbloqueia. Em segundo plano: a resposta do modelo não espera pela escrita."""
    global _marcado_localmente
    if _marcado_localmente is False:
        return
    _marcado_localmente = False
    try:
        asyncio.get_running_loop().create_task(_limpar(), name="ia-estado-ok")
    except RuntimeError:  # sem loop (não acontece no servidor)
        pass


async def _sondar() -> None:
    """UM pedido mínimo ao modelo. A resposta (boa ou «sem créditos») actualiza o estado pelo funil."""
    try:
        from services.ai_document import call_openai_api

        await db.system_flags.update_one({"id": ID_DO_ESTADO}, {"$set": {"verificado_em": _agora().isoformat()}})
        await call_openai_api([{"role": "user", "content": "Responde em JSON: {}"}], None, timeout=20.0, max_tokens=5,
                              ignorar_pausa=True)
        await _limpar()  # directo: o «já limpei» em memória pode ser de antes de outro processo marcar
    except Exception as exc:  # noqa: BLE001 — a sonda falhada só quer dizer «ainda não»
        logger.info("[IA] Sonda: a IA continua indisponível (%s)", type(exc).__name__)


def _sonda_devida(estado: dict) -> bool:
    try:
        ultima = datetime.fromisoformat(str(estado.get("verificado_em")))
    except (TypeError, ValueError):
        return True
    if ultima.tzinfo is None:
        ultima = ultima.replace(tzinfo=timezone.utc)
    return _agora() - ultima >= INTERVALO_DA_SONDA


async def estado_da_ia(bd=None) -> dict[str, Any]:
    """`{"disponivel": bool, "motivo": código|None, "mensagem": texto|None}`. Nunca levanta.

    `bd`: a base de dados de quem pergunta (o módulo que a importou ao nível do módulo — e é essa que os
    testes trocam por uma falsa)."""
    global _sonda_em_curso, _marcado_localmente
    try:
        estado = await asyncio.wait_for(
            (bd if bd is not None else db).system_flags.find_one({"id": ID_DO_ESTADO}, {"_id": 0}),
            timeout=TECTO_DA_ESCRITA,
        ) or {}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[IA] Estado da IA ilegível: %s", exc)
        estado = {}
    if not estado.get("sem_creditos"):
        return {"disponivel": True, "motivo": None, "mensagem": None}
    _marcado_localmente = True  # marcado por outro processo (ex.: o worker): a próxima resposta boa limpa
    if _sonda_devida(estado) and (_sonda_em_curso is None or _sonda_em_curso.done()):
        _sonda_em_curso = asyncio.create_task(_sondar(), name="ia-sonda-de-creditos")
    return {"disponivel": False, "motivo": "sem_creditos", "mensagem": MENSAGEM_SEM_CREDITOS}
