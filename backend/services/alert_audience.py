"""Quem recebe um alerta de um processo — ponto ÚNICO (Lote 6, ponto 8).

DOIS DEFEITOS QUE ESTE MÓDULO FECHA
===================================

1. **A gestão era notificada sem filtro de rede.** `services/alerts.py`
   fazia, em três sítios:

       db.users.find({"$and": [deep_role_in_filter(["admin","ceo","diretor"]),
                               {"is_active": True}]})

   sem uma única condição de tenant. Um alerta de um processo da Power
   notificava a direcção da Domus — que é uma ilha — com o NOME DO CLIENTE
   no título da notificação. É o mesmo furo do Lote 4/5 numa superfície
   que o varrimento não inventariou, porque não é uma listagem: é um
   emissor.

2. **Os atribuídos eram lidos de uma lista escrita à mão.** Os mesmos três
   sítios liam `assigned_consultor_id` / `consultor_id` /
   `assigned_mediador_id` / `intermediario_id` e ignoravam os PLURAIS
   (`assigned_consultor_ids`, `assigned_mediador_ids`), que são a verdade
   desde o Lote 5. Consequência: num processo com dois consultores, o
   segundo nunca era notificado. E uma lista escrita à mão diverge das
   constantes canónicas na primeira mudança — que é exactamente o defeito
   que produziu o resíduo do `consultor_id`.

A REDE DO PROCESSO, E O QUE FAZER SEM CARIMBO
=============================================
A rede sai do carimbo (`network_id`) quando existe; senão, da empresa do
processo; senão, da rede de omissão (`TENANT_DEFAULT_NETWORK_ID`, definida
em produção, que é onde vive a pilha por carimbar).

Se nenhuma das três resolver, a audiência de gestão é **VAZIA** e fica um
`warning`. Falha fechada: a alternativa é difundir o nome de um cliente a
toda a gestão de todas as redes, e um alerta que não chega nota-se — uma
fuga não.

Os ATRIBUÍDOS não passam por este filtro, de propósito: quem está
atribuído a um processo tem, por definição, de saber dele. O filtro é para
a audiência que se obtém por CARGO.
"""
from __future__ import annotations

import logging
from typing import Any, Optional, Sequence

from database import db
from services.process_staff_assignment import (
    CONSULTOR_ID_FIELDS,
    MEDIADOR_ID_FIELDS,
)
from services.tenant_network import (
    CAMPO_REDE,
    CAMPOS_EMPRESA,
    VALORES_SEM_EMPRESA,
    rede_de_omissao,
    rede_implicita,
)

logger = logging.getLogger(__name__)

#: Os plurais são a VERDADE (Lote 5); os singulares repetem o primeiro id.
#: Ambos entram, porque a pilha histórica ainda tem processos em que só os
#: singulares foram escritos — é a mesma dívida que o
#: `scripts/diagnose_assignment_drift.py` mede.
CAMPOS_DE_LISTA: tuple[str, ...] = (
    "assigned_consultor_ids",
    "assigned_mediador_ids",
    "assigned_to",
)

#: Singulares canónicos + os legados que não vivem nas constantes.
CAMPOS_SINGULARES: tuple[str, ...] = (
    *CONSULTOR_ID_FIELDS,
    *MEDIADOR_ID_FIELDS,
    "intermediario_id",
    "assigned_indexacao_id",
)

MAX_UTILIZADORES = 200


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def ids_atribuidos(processo: Optional[dict]) -> list[str]:
    """Todos os utilizadores atribuídos, sem repetições e por ordem estável.

    Os campos vêm das constantes de produção: uma lista escrita aqui à mão
    divergiria do `set`/`clear` e deixaria de notificar alguém sem dar
    erro nenhum.
    """
    processo = processo or {}
    encontrados: list[str] = []

    def acrescentar(valor: Any) -> None:
        texto = _texto(valor)
        if texto and texto not in encontrados:
            encontrados.append(texto)

    for campo in CAMPOS_DE_LISTA:
        valor = processo.get(campo)
        if isinstance(valor, list):
            for item in valor:
                acrescentar(item)
        else:
            # `assigned_to` nem sempre é lista na pilha antiga (Lote 4).
            acrescentar(valor)

    for campo in CAMPOS_SINGULARES:
        acrescentar(processo.get(campo))

    return encontrados


def rede_do_processo(processo: Optional[dict]) -> Optional[str]:
    """Rede a que o processo pertence, ou ``None`` se não se conseguir dizer."""
    processo = processo or {}

    carimbo = _texto(processo.get(CAMPO_REDE))
    if carimbo:
        return carimbo

    for campo in CAMPOS_EMPRESA:
        valor = processo.get(campo)
        if valor not in VALORES_SEM_EMPRESA and _texto(valor):
            # A empresa pode ter grupo configurado; quem sabe é a colecção
            # `companies`. Sem I/O aqui, devolve-se a ilha implícita e o
            # chamador assíncrono refina-a.
            return rede_implicita(valor)

    return rede_de_omissao()


async def _rede_resolvida(processo: Optional[dict]) -> Optional[str]:
    """Como `rede_do_processo`, mas lê o grupo real da empresa."""
    processo = processo or {}

    carimbo = _texto(processo.get(CAMPO_REDE))
    if carimbo:
        return carimbo

    for campo in CAMPOS_EMPRESA:
        chave = _texto(processo.get(campo))
        if not chave or processo.get(campo) in VALORES_SEM_EMPRESA:
            continue
        try:
            empresa = await db.companies.find_one(
                {"$or": [{"id": chave}, {"name": chave}]},
                {"_id": 0, "id": 1, CAMPO_REDE: 1},
            )
        except Exception as exc:
            logger.warning("[alert_audience] Falha a ler a empresa %s (%s).", chave, exc)
            empresa = None
        if empresa and _texto(empresa.get(CAMPO_REDE)):
            return _texto(empresa[CAMPO_REDE])
        return rede_implicita(empresa.get("id") if empresa else chave)

    return rede_de_omissao()


async def gestao_da_rede_do_processo(
    processo: Optional[dict],
    papeis: Sequence[str],
) -> list[str]:
    """Ids da gestão que pertence à MESMA rede do processo.

    Devolve `[]` — e regista o motivo — quando a rede não se consegue
    determinar. Ver o cabeçalho: falha fechada de propósito.
    """
    rede = await _rede_resolvida(processo)
    if not rede:
        logger.warning(
            "[alert_audience] Processo %s sem rede determinável: a gestão não "
            "é notificada (falha fechada). Definir TENANT_DEFAULT_NETWORK_ID "
            "ou carimbar o processo.",
            (processo or {}).get("id"),
        )
        return []

    try:
        empresas = await db.companies.find(
            {CAMPO_REDE: rede}, {"_id": 0, "id": 1, "name": 1},
        ).to_list(MAX_UTILIZADORES)
    except Exception as exc:
        logger.warning("[alert_audience] Falha a listar as empresas de %s (%s).", rede, exc)
        return []

    identificadores = [
        valor
        for empresa in empresas
        for valor in (_texto(empresa.get("id")), _texto(empresa.get("name")))
        if valor
    ]

    # Uma rede implícita (`rede:<id>`) é uma ilha de uma empresa só, e essa
    # empresa pode não ter o campo `network_id` gravado — daí não aparecer
    # na consulta acima. O id vem do próprio nome da rede.
    if not identificadores and rede.startswith("rede:"):
        identificadores = [rede.split("rede:", 1)[1]]

    if not identificadores:
        logger.warning(
            "[alert_audience] Rede %s sem empresas: a gestão não é notificada.", rede,
        )
        return []

    papeis_normalizados = [str(p).lower() for p in papeis if p]
    try:
        ucrs = await db.user_company_roles.find(
            {
                "company_id": {"$in": identificadores},
                "role": {"$in": papeis_normalizados},
                "is_deleted": {"$ne": True},
                "is_active": {"$ne": False},
            },
            {"_id": 0, "user_id": 1},
        ).to_list(MAX_UTILIZADORES)
    except Exception as exc:
        logger.warning("[alert_audience] Falha a listar os UCRs de %s (%s).", rede, exc)
        return []

    vistos: list[str] = []
    for ucr in ucrs:
        uid = _texto(ucr.get("user_id"))
        if uid and uid not in vistos:
            vistos.append(uid)
    return vistos


async def destinatarios_do_alerta(
    processo: Optional[dict],
    *,
    papeis_de_gestao: Sequence[str] = (),
) -> list[str]:
    """Atribuídos (sempre) + gestão da rede do processo (quando pedida).

    Quem está atribuído recebe SEM passar pelo filtro de rede: estar
    atribuído é, por si, a autorização. O filtro existe para a audiência
    que se obtém por CARGO.
    """
    destinatarios = ids_atribuidos(processo)

    if papeis_de_gestao:
        for uid in await gestao_da_rede_do_processo(processo, papeis_de_gestao):
            if uid not in destinatarios:
                destinatarios.append(uid)

    return destinatarios
