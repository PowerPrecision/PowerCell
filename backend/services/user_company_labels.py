"""
====================================================================
Empresa(s) de cada utilizador nas listas de atribuição
====================================================================
(QA, Out 2026.) Nas modais e listas de atribuição de um processo só aparecia
`Nome (perfil)`: com a atribuição entre redes a passar pela Partilha Explícita
e gente com acesso a mais do que uma empresa, quem atribui precisa de ver a que
EMPRESA pertence cada pessoa. A etiqueta é calculada AO SERVIR e nunca gravada
(uma empresa que muda de nome desactualizava todas as cópias).

DE ONDE VEM A EMPRESA
  Os UCRs (`user_company_roles`) são o registo canónico; `users.company` é o
  NOME legado e só vale para quem não tem UCR. O `company_id` nunca se infere
  do nome (a confusão de 2026-09-21).

QUEM SE VÊ
  Um perfil local só vê as empresas do SEU âmbito: uma pessoa com acesso a
  duas redes não revela a quem pertence a outra o nome de empresas que
  não são dele. O Master (sem fronteira) vê todas.

NUNCA LEVANTA
  É um enfeite sobre uma lista que já existe: falhar a juntá-lo não pode
  esvaziar a dropdown de atribuição. Sem etiqueta a lista funciona como antes.
====================================================================
"""
from __future__ import annotations

import logging
from typing import Iterable

from database import db

logger = logging.getLogger(__name__)

#: Quantas empresas se escrevem na etiqueta antes de resumir («+N»).
MAXIMO_NA_ETIQUETA = 3


def _nome(valor) -> str:
    return str(valor).strip() if isinstance(valor, str) and valor.strip() else ""


def formatar_etiqueta(empresas: Iterable[str]) -> str:
    """«Power · Precision»; acima do limite resume («Power · Precision · Domus +2»)."""
    nomes = [n for n in empresas if n]
    if not nomes:
        return ""
    visiveis = nomes[:MAXIMO_NA_ETIQUETA]
    resto = len(nomes) - len(visiveis)
    etiqueta = " · ".join(visiveis)
    return f"{etiqueta} +{resto}" if resto > 0 else etiqueta


def empresas_do_utilizador(
    utilizador: dict, ucrs: list[dict], *, ambito=None
) -> list[str]:
    """Nomes das empresas de UM utilizador (puro).

    `ambito` é o `EmpresasDoAmbito` de quem pede (ou `None` = sem restrição).
    Restringe-se por id OU por nome — o UCR antigo só tem o nome.
    """
    sem_restricao = ambito is None or getattr(ambito, "sem_fronteira", False) \
        or not getattr(ambito, "fechado", True)
    ids_permitidos = set(getattr(ambito, "ids", []) or [])
    nomes_permitidos = set(getattr(ambito, "nomes", []) or [])

    def visivel(company_id: str, company_name: str) -> bool:
        if sem_restricao:
            return True
        return (company_id in ids_permitidos) or (company_name in nomes_permitidos)

    vistos: list[str] = []
    for ucr in ucrs:
        nome = _nome(ucr.get("company_name"))
        if not nome:
            continue
        if visivel(str(ucr.get("company_id") or ""), nome) and nome not in vistos:
            vistos.append(nome)

    if not vistos:
        # Sem UCR: o campo legado (o NOME). É a empresa da própria pessoa; só se
        # esconde se estiver fora do âmbito de quem pede.
        legado = _nome(utilizador.get("company")) or _nome(utilizador.get("company_name"))
        if legado and visivel("", legado):
            vistos.append(legado)
    return sorted(vistos, key=str.casefold)


async def anexar_empresas(utilizadores: list[dict], *, ambito=None) -> list[dict]:
    """Junta `empresas` (lista) e `empresa_etiqueta` (texto) a cada utilizador.

    Uma só consulta aos UCRs para a lista inteira. Nunca levanta.
    """
    try:
        ids = [str(u["id"]) for u in utilizadores if u.get("id")]
        por_utilizador: dict[str, list[dict]] = {}
        if ids:
            ucrs = await db.user_company_roles.find(
                {"user_id": {"$in": ids}},
                {"_id": 0, "user_id": 1, "company_id": 1, "company_name": 1},
            ).to_list(20000)
            for ucr in ucrs:
                por_utilizador.setdefault(str(ucr.get("user_id")), []).append(ucr)
        for utilizador in utilizadores:
            nomes = empresas_do_utilizador(
                utilizador, por_utilizador.get(str(utilizador.get("id")), []), ambito=ambito
            )
            utilizador["empresas"] = nomes
            utilizador["empresa_etiqueta"] = formatar_etiqueta(nomes)
    except Exception as exc:  # pragma: no cover — degradação graciosa
        logger.warning("[USERS] Não foi possível juntar as empresas à lista: %s", exc)
    return utilizadores
