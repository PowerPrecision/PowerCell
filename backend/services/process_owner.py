"""A empresa DONA de um processo, para o ecrã de detalhe (Multi-Tenant, Out 2026).

Com a partilha B2B (D-25) um utilizador abre processos que não são da sua
casa. A gestão precisa de saber, ao abrir um, a que empresa ele pertence — e se
é um processo que lhe foi partilhado.

O QUE SE DEVOLVE (``empresa_dona``)
  ``company_id`` / ``company_name`` / ``network_id`` do DONO e ``e_de_outra_rede``
  (o processo está a ser visto por quem não é da rede dona — ou seja, foi-lhe
  partilhado). ``None`` quando não se consegue dizer sem adivinhar.

DE ONDE VEM O NOME (por ordem, sem nunca inventar)
  1. ``company_name`` gravado no carimbo do processo;
  2. a empresa de ``company_id`` (carimbo antigo sem nome);
  3. a(s) empresa(s) da rede dona — para os processos antigos, que só têm
     ``network_id`` ou nem isso (a pilha por carimbar é da rede de omissão).
     Com várias empresas na rede mostram-se todas: dizer só uma seria adivinhar.

Módulo de LEITURA: falhar aqui nunca pode estragar o detalhe do processo, por
isso o ponto de entrada devolve ``None`` com um aviso em vez de levantar.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from database import db
from services.tenant_network import (
    CAMPO_REDE,
    TenantScope,
    documento_sem_marca_de_tenant,
    rede_de_omissao,
    resolve_tenant_scope,
)

logger = logging.getLogger(__name__)

#: Tecto das empresas listadas quando a rede dona tem várias.
MAXIMO_DE_EMPRESAS = 3
SEPARADOR = " · "


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def rede_dona(processo: dict) -> Optional[str]:
    """A rede dona: o carimbo; sem nenhuma marca, a rede de omissão; senão ``None``."""
    carimbo = _texto((processo or {}).get(CAMPO_REDE))
    if carimbo:
        return carimbo
    if documento_sem_marca_de_tenant(processo):
        return rede_de_omissao()
    return None


def e_de_outra_rede(rede: Optional[str], scope: TenantScope) -> bool:
    """O processo é de uma rede que NÃO é a de quem o vê?

    Sem rede dona conhecida não se afirma nada (``False``): dizer «partilhado»
    sem saber seria pior do que não dizer.
    """
    if not rede or scope.sem_fronteira:
        return False
    if rede in {_texto(r) for r in scope.network_ids}:
        return False
    return not (scope.inclui_rede_de_omissao and rede == rede_de_omissao())


async def _nomes_da_rede(rede: str) -> list[str]:
    if rede.startswith("rede:"):  # ilha implícita: a própria empresa
        empresa = await db.companies.find_one({"id": rede[len("rede:"):]}, {"_id": 0, "name": 1})
        return [_texto((empresa or {}).get("name"))] if _texto((empresa or {}).get("name")) else []
    docs = await db.companies.find(
        {CAMPO_REDE: rede, "is_active": {"$ne": False}}, {"_id": 0, "id": 1, "name": 1},
    ).to_list(10)
    return sorted({n for n in (_texto(d.get("name")) for d in docs) if n})[:MAXIMO_DE_EMPRESAS]


async def calcular_empresa_dona(processo: dict, scope: TenantScope) -> Optional[dict]:
    """``empresa_dona`` de um processo para quem tem este âmbito (ver o módulo)."""
    rede = rede_dona(processo)
    company_id = _texto(processo.get("company_id"))
    nome = _texto(processo.get("company_name"))

    if not nome and company_id:
        empresa = await db.companies.find_one({"id": company_id}, {"_id": 0, "name": 1})
        nome = _texto((empresa or {}).get("name"))

    if not nome and rede:
        nome = SEPARADOR.join(await _nomes_da_rede(rede))

    if not nome:
        return None
    return {
        "company_id": company_id or None,
        "company_name": nome,
        "network_id": rede,
        "e_de_outra_rede": e_de_outra_rede(rede, scope),
    }


async def anexar_empresa_dona(processo: dict, user: dict) -> None:
    """Põe ``empresa_dona`` no documento que vai para o ecrã. Nunca levanta."""
    try:
        scope = await resolve_tenant_scope(user or {})
        processo["empresa_dona"] = await calcular_empresa_dona(processo, scope)
    except Exception as exc:  # noqa: BLE001 - leitura: nunca estragar o detalhe
        logger.warning(
            "[ProcessOwner] Falha a resolver a empresa dona de %s: %s",
            (processo or {}).get("id"), exc,
        )
        processo["empresa_dona"] = None
