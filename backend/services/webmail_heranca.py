"""Webmail: quem pode HERDAR a configuração global de email (e quem não pode).

O QUE FALHAVA
  Um utilizador de uma rede satélite (Domus) abria a configuração de Webmail e
  via a «Caixa Geral» da rede de omissão (Power) com o aviso «Servidores
  IMAP/SMTP herdados da configuração global». Três caminhos faziam herança:

    * ``load_caixa_geral_config(<empresa>)`` chamava ``get_system_config``, que
      — para uma empresa sem config própria — GRAVA uma cópia da global
      (``company:<id>`` com o utilizador/servidores da Power) e a devolvia como
      se fosse a caixa dessa empresa; e, mesmo sem cópia, recorria a ``default``
      e às contas de ambiente (``POWER_*`` / ``PRECISION_*``);
    * ``resolve_email_config`` acabava em ``system_config.main`` (os servidores
      globais) para qualquer utilizador sem config de empresa;
    * a indicação «email configurado» do perfil considerava a global para todos.

A REGRA (isolamento estrito, sem fallback)
  A configuração GLOBAL (``system_config.main``, o recurso ``default``, as
  contas de ambiente) é da **rede de omissão** (``TENANT_DEFAULT_NETWORK_ID``).
  Uma empresa de outra rede só tem Caixa Geral se a CONFIGUROU ela: uma
  configuração por empresa cujo utilizador é o da global é a cópia que a
  herança gravou — a caixa de OUTRA rede — e não conta. Sem caixa própria o
  ecrã fica vazio (só «Adicionar conta»); nunca mostra a da empresa-mãe.

  * Falha fechada: empresa desconhecida, rede por determinar ou erro a ler →
    não herda (um Webmail vazio nota-se; a caixa de outra rede é uma fuga).
  * Dev/CI sem ``TENANT_DEFAULT_NETWORK_ID`` mantêm o comportamento anterior
    (não há rede de omissão a que atribuir a global) — o mesmo critério das
    outras colecções.
  * O sentinel ``"default"`` (sem empresa) só herda se o utilizador pertencer à
    rede de omissão.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from database import db
from services.tenant_network import (
    VALORES_SEM_EMPRESA,
    _redes_das_empresas,
    rede_de_omissao,
    resolve_tenant_scope,
)

logger = logging.getLogger(__name__)


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


async def rede_da_empresa(company_id: Any) -> Optional[str]:
    """A rede de uma empresa (id ou nome); a ilha implícita se não tiver grupo."""
    cid = _texto(company_id)
    if not cid or cid in VALORES_SEM_EMPRESA:
        return None
    return (await _redes_das_empresas([cid])).get(cid)


async def pode_herdar_configuracao_global(
    company_id: Any,
    *,
    user: Optional[dict] = None,
) -> bool:
    """Esta empresa (no contexto deste utilizador) pode usar a configuração global?

    ``True`` só para a rede de omissão. Sem ``TENANT_DEFAULT_NETWORK_ID`` (dev/CI)
    devolve ``True`` — comportamento anterior ao isolamento.
    """
    omissao = rede_de_omissao()
    if not omissao:
        return True

    cid = _texto(company_id)
    if cid and cid not in VALORES_SEM_EMPRESA:
        try:
            return await rede_da_empresa(cid) == omissao
        except Exception as exc:  # noqa: BLE001 - falha fechada
            logger.warning(
                "[WebmailHeranca] Falha a resolver a rede de %s (%s): não herda a global.",
                cid, exc,
            )
            return False

    # Sem empresa («default»): decide a rede do utilizador, nunca um valor por omissão.
    if not user:
        return False
    try:
        scope = await resolve_tenant_scope(user)
    except Exception as exc:  # noqa: BLE001 - falha fechada
        logger.warning("[WebmailHeranca] Âmbito indisponível (%s): não herda a global.", exc)
        return False
    return bool(scope.sem_fronteira or omissao in scope.network_ids)


async def empresa_no_ambito_do_utilizador(company_id: Any, user: Optional[dict]) -> bool:
    """A rede da empresa pedida está no âmbito do utilizador?

    Impede que um ``X-Company-Id`` / ``?company_id=`` de outra rede faça listar
    a caixa dessa rede. Sem utilizador ou sem empresa concreta não há o que
    validar (devolve ``True``: o chamador decide pela herança).
    """
    cid = _texto(company_id)
    if not user or not cid or cid in VALORES_SEM_EMPRESA:
        return True
    try:
        scope = await resolve_tenant_scope(user)
        if scope.sem_fronteira:
            return True
        rede = await rede_da_empresa(cid)
    except Exception as exc:  # noqa: BLE001 - falha fechada
        logger.warning("[WebmailHeranca] Âmbito indisponível (%s): empresa recusada.", exc)
        return False
    return bool(rede) and rede in set(scope.network_ids)


def utilizador_de_email(cfg: Optional[dict]) -> str:
    """O utilizador (login) de um bloco ``email`` do system_config, em minúsculas."""
    return _texto((cfg or {}).get("imap_user") or (cfg or {}).get("smtp_user")).lower()


async def email_do_documento(doc_id: str) -> Optional[dict]:
    """O bloco ``email`` de um documento do system_config, SEM o criar por herança.

    Ler com ``get_system_config(<empresa>)`` grava uma cópia da global quando a
    empresa não tem config; isto lê o documento tal como está.
    """
    try:
        doc = await db.system_config.find_one({"_id": doc_id}, {"_id": 0, "email": 1})
    except Exception as exc:  # noqa: BLE001
        logger.warning("[WebmailHeranca] Falha a ler system_config %s: %s", doc_id, exc)
        return None
    email = (doc or {}).get("email")
    return email if isinstance(email, dict) else None


async def e_copia_da_global(company_id: Any) -> bool:
    """A config de email desta empresa é a cópia que a herança gravou da global?"""
    cid = _texto(company_id)
    if not cid or cid in VALORES_SEM_EMPRESA:
        return False
    propria = utilizador_de_email(await email_do_documento(f"company:{cid}"))
    global_ = utilizador_de_email(await email_do_documento("main"))
    return bool(propria) and propria == global_
