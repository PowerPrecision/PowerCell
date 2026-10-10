"""Quem vê e quem mexe num registo financeiro — `db.process_finances` (D-24).

O QUE CORREU MAL
================
`GET /finance/processes` abria com `query = {}` e o `company_id` era um
parâmetro OPCIONAL da query string. **Um filtro escolhido por quem
pergunta nunca é uma parede** — é o placebo do
`build_company_scope_condition` outra vez, agora numa colecção que leva
`client_name`, o valor esperado e as comissões repartidas. E os
`FINANCE_READ_ROLES` incluem `consultor`, `administrativo` e
`indexacao`.

Os cinco handlers de um registo (`get`, `update`, `status`, `delete` e o
`summary`) eram `find_one({"id": finance_id})` e mais nada: a rota
autoriza o VERBO, não o OBJECTO.

A FRONTEIRA DERIVA DA EMPRESA, NÃO DE UM CARIMBO NOVO
=====================================================
Aqui **não** se usa o `build_tenant_condition`, e a razão é de dados e
não de estilo: `process_finances` é chaveada por
`(process_id, company_id)` — um registo por empresa no mesmo processo,
que é exactamente a repartição de comissões de uma partilha — logo
**todos os registos já identificam a empresa**. `network_id` nunca
existiu nesta colecção e o `backfill_network_id --documentos` não a
cobre.

Filtrar pelas empresas do UTILIZADOR resolvia a fuga e abria outro
buraco no sentido contrário: a Precision deixava de ver os registos da
Power, que estão na mesma rede e que ela deve ver. **Dados a menos não
se notam menos do que dados a mais: notam-se pior**, porque parecem um
erro de contabilidade e ninguém suspeita de uma guarda.

Resolver rede → empresas (`empresas_das_minhas_redes`) fecha a fronteira
com um campo que está preenchido em todos os registos, sem migração
nenhuma e sem perder o que a rede partilha.

O PARÂMETRO PEDIDO VALIDA-SE, NÃO SE CONFIA
===========================================
Há endpoints em que o `company_id` é **obrigatório** (o `summary`, a
exportação, a pool). Esses continuam a filtrar pelo que foi pedido — mas
`exigir_empresa_no_ambito` verifica primeiro que a empresa pedida é de
uma das redes do utilizador. Sem isso, bastava escrever o id da outra
empresa no URL.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from fastapi import HTTPException, Request

from services.deadline_scope import e_papel_sem_fronteira
from services.tenant_network import (
    CONDICAO_IMPOSSIVEL,
    build_company_field_condition,
    empresas_das_minhas_redes,
    resolve_tenant_scope,
)

logger = logging.getLogger(__name__)

#: A MESMA mensagem para "não existe" e para "não é da tua rede".
ERRO_REGISTO_NAO_ENCONTRADO = "Registo financeiro não encontrado"

#: O campo que identifica a empresa num registo financeiro.
CAMPO_EMPRESA = "company_id"


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor not in (None, "") else ""


@dataclass(frozen=True)
class AmbitoFinanceiro:
    """Papel efectivo, empresas das minhas redes e condição Mongo."""

    papel: str = ""
    empresas: tuple[str, ...] = ()
    condicao: dict = field(default_factory=dict)


def pode_ver_registo(
    registo: Optional[dict],
    *,
    papel: Any,
    empresas: Iterable[str],
) -> bool:
    """Predicado GÉMEO da condição — a mesma pergunta em Python.

    Um registo **sem empresa** é recusado a quem não é Master. É
    deliberadamente mais estrito do que a tolerância do legado nas
    outras colecções: o `company_id` é obrigatório na criação desde
    sempre, logo um registo sem ele é dados corrompidos e não história —
    e adivinhar a quem pertence é escolher a quem vazar.
    """
    if not registo:
        return False
    if e_papel_sem_fronteira(papel):
        return True
    empresa = _texto(registo.get(CAMPO_EMPRESA))
    if not empresa:
        return False
    return empresa in {_texto(e) for e in empresas if _texto(e)}


async def carregar_ambito_financeiro(
    user: dict,
    request: Optional[Request] = None,
) -> AmbitoFinanceiro:
    """Resolve o papel efectivo e as empresas das redes do utilizador."""
    from services.property_scope import papel_efectivo

    papel = await papel_efectivo(user, request)
    scope = await resolve_tenant_scope(user)
    empresas = await empresas_das_minhas_redes(scope)

    if e_papel_sem_fronteira(papel):
        # O MASTER (único perfil global) vê a pilha inteira — é o único `{}`
        # que atravessa redes de propósito, e diz-se.
        return AmbitoFinanceiro(papel=papel, empresas=empresas, condicao={})

    condicao = build_company_field_condition(empresas, campo=CAMPO_EMPRESA)
    if condicao == CONDICAO_IMPOSSIVEL:
        logger.warning(
            "[FINANCAS] %s (papel=%s) sem empresas resolvidas nas redes %s: "
            "a listagem financeira fica VAZIA (falha fechada).",
            (user or {}).get("id"), papel, list(scope.network_ids),
        )
    return AmbitoFinanceiro(papel=papel, empresas=empresas, condicao=condicao)


async def exigir_registo_no_ambito(
    registo: Optional[dict],
    *,
    user: dict,
    request: Optional[Request] = None,
    ambito: Optional[AmbitoFinanceiro] = None,
) -> AmbitoFinanceiro:
    """Levanta **404** quando o registo não é de uma rede deste utilizador."""
    ambito = ambito or await carregar_ambito_financeiro(user, request)
    if not pode_ver_registo(registo, papel=ambito.papel, empresas=ambito.empresas):
        logger.warning(
            "[FINANCAS] Registo %s (empresa=%r) fora do âmbito de %s "
            "(papel=%s, empresas=%s)",
            (registo or {}).get("id"),
            (registo or {}).get(CAMPO_EMPRESA),
            (user or {}).get("id"),
            ambito.papel,
            ambito.empresas,
        )
        raise HTTPException(status_code=404, detail=ERRO_REGISTO_NAO_ENCONTRADO)
    return ambito


async def exigir_empresa_no_ambito(
    company_id: Any,
    *,
    user: dict,
    request: Optional[Request] = None,
    ambito: Optional[AmbitoFinanceiro] = None,
) -> AmbitoFinanceiro:
    """Valida um `company_id` que veio do PEDIDO.

    **404 e não 403**: distinguir «essa empresa não existe» de «essa
    empresa não é tua» transforma o endpoint num directório das empresas
    do sistema.
    """
    ambito = ambito or await carregar_ambito_financeiro(user, request)
    if e_papel_sem_fronteira(ambito.papel):
        return ambito

    pedida = _texto(company_id)
    if pedida and pedida in {_texto(e) for e in ambito.empresas if _texto(e)}:
        return ambito

    logger.warning(
        "[FINANCAS] %s (papel=%s) pediu a empresa %r, fora das suas redes.",
        (user or {}).get("id"), ambito.papel, company_id,
    )
    raise HTTPException(status_code=404, detail=ERRO_REGISTO_NAO_ENCONTRADO)


__all__ = [
    "CAMPO_EMPRESA",
    "ERRO_REGISTO_NAO_ENCONTRADO",
    "AmbitoFinanceiro",
    "carregar_ambito_financeiro",
    "exigir_empresa_no_ambito",
    "exigir_registo_no_ambito",
    "pode_ver_registo",
]
