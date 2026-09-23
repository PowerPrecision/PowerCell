"""
Estado do motor de background — GET /api/automations (Lote 4, ponto 14).

READ-ONLY de propósito: um disparo manual a partir da web não chegaria ao
processo worker de qualquer maneira (são processos distintos do
`render.yaml`), e um botão que não faz nada é pior do que não existir.

A lista sai do REGISTO DECLARADO (`job_heartbeat.JOBS_DECLARADOS`), não da
colecção: se listássemos só o que bateu, o job mais avariado de todos — o
que nunca arrancou — era o único invisível.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from services.job_heartbeat import (
    ESTADO_ATRASADO,
    ESTADO_FALHOU,
    ESTADO_NUNCA_CORREU,
    JOBS_DECLARADOS,
    estado_do_job,
    job_esta_activo,
    ler_batimentos,
    proxima_execucao,
)

logger = logging.getLogger(__name__)

# Estados que merecem atenção humana. "desactivado" NÃO está aqui: em dev
# quase tudo está desligado de propósito (kill switches por RAM), e um
# painel a gritar vermelho em dev ensina toda a gente a ignorá-lo.
ESTADOS_COM_PROBLEMA = frozenset({ESTADO_FALHOU, ESTADO_ATRASADO, ESTADO_NUNCA_CORREU})


def montar_linha(declarado: dict, registo: dict | None, *, agora: datetime) -> dict[str, Any]:
    """Uma linha do painel: o declarado + o observado + o estado derivado."""
    estado = estado_do_job(declarado, registo, agora=agora)
    registo = registo or {}
    return {
        "chave": declarado["chave"],
        "nome": declarado["nome"],
        "descricao": declarado.get("descricao", ""),
        "processo": declarado["processo"],
        "interval_seconds": declarado["interval_seconds"],
        "activo": job_esta_activo(declarado),
        "estado": estado,
        "ultima_execucao": registo.get("finished_at"),
        "ultimo_inicio": registo.get("started_at"),
        "proxima_execucao": proxima_execucao(declarado, registo or None),
        "duracao_ms": registo.get("duration_ms"),
        "erro": registo.get("error"),
        "run_count": registo.get("run_count", 0),
        "failure_count": registo.get("failure_count", 0),
        # Com dois processos e dois workers uvicorn, saber QUEM bateu é
        # metade do diagnóstico.
        "host": registo.get("host"),
        "pid": registo.get("pid"),
    }


def resumir(linhas: list[dict]) -> dict[str, Any]:
    """Contagens para o cabeçalho do painel."""
    com_problema = [l for l in linhas if l["estado"] in ESTADOS_COM_PROBLEMA]
    return {
        "total": len(linhas),
        "com_problema": len(com_problema),
        "desactivados": sum(1 for l in linhas if not l["activo"]),
        "saudaveis": sum(
            1 for l in linhas
            if l["activo"] and l["estado"] not in ESTADOS_COM_PROBLEMA
        ),
    }


async def run_get_automations_status() -> dict[str, Any]:
    """GET /api/automations — sinais vitais do motor de background."""
    agora = datetime.now(timezone.utc)
    batimentos = await ler_batimentos()

    linhas = [
        montar_linha(declarado, batimentos.get(declarado["chave"]), agora=agora)
        for declarado in JOBS_DECLARADOS
    ]

    return {
        "jobs": linhas,
        "resumo": resumir(linhas),
        "gerado_em": agora.isoformat(),
    }
