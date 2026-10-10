"""Origem financeira de um processo — a quem se atribui o negócio (Bloco 4, ponto 7).

A REGRA DE NEGÓCIO
  O cliente de um processo ou *veio directamente à empresa* (lead
  ORGÂNICA) ou *foi angariado por um utilizador específico* (lead de
  ANGARIAÇÃO). Fundamental para o cálculo posterior das comissões, e
  visível/editável só pela gestão (admin, CEO, diretor).

ONDE VIVE — NUMA COLECÇÃO À PARTE, DE PROPÓSITO
  `ProcessResponse` tem `extra="allow"`, o `GET /processes/{id}` devolve o
  documento inteiro e há dezenas de leitores de `processes` (Kanban,
  listagens, pesquisa, exportações, o próprio frontend a fazer `...processo`).
  Um campo `origem_financeira` no documento de processo vazava para todos
  eles — a um consultor, que não o pode ver — e a única defesa seria
  lembrar-se de o tirar em cada leitor presente e futuro («esconder» em vez
  de «não estar»). Em `process_financial_origins` o único leitor é este
  módulo: a restrição por perfil é uma propriedade da arquitectura e não de
  um filtro que alguém pode esquecer.

AS REGRAS
  1. **Só a gestão** (papel EFECTIVO: admin, CEO, diretor). Os outros recebem
     403 com o motivo — já veem o processo, não há id a esconder.
  2. **O processo tem de estar no âmbito do utilizador** (404 igual ao de
     «não existe» para quem nem o vê). Admin/CEO reconciliam entre redes; o
     diretor só da casa DONA — quem decide quem recebe a comissão de um
     negócio é a casa que o detém, não uma rede convidada (a regra da
     revogação de partilhas).
  3. **O angariador é um utilizador do âmbito de quem decide**, activo. Um id
     inventado, de outra rede ou inactivo é recusado: atribuir comissão a
     quem não se pode ver é o buraco que as outras fronteiras já fecharam.
  4. **`orgânica` não leva angariador.** Escolher «veio directamente» limpa
     o angariador em vez de o guardar como lixo que o cálculo leria.
  5. **Rasto sem revelar o valor.** O histórico do processo é lido por quem
     NÃO vê a origem: regista-se que foi alterada, nunca para quê. O valor
     antigo e o novo vão para o trilho de auditoria (só gestão), que fica
     excluído quando o actor é silenciado.
  6. **Falha de rasto nunca falha a operação.**
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel

from database import db
from services.history import _is_stealth_user, log_history
from services.tenant_access_context import resolver_papel_efectivo
from services.tenant_network import (
    CAMPOS_DO_CARIMBO,
    PROJECCAO_DO_CARIMBO,
    documento_no_ambito,
    processo_no_ambito,
    resolve_tenant_scope,
)

logger = logging.getLogger(__name__)

COLECAO = "process_financial_origins"

TIPO_ORGANICA = "organica"
TIPO_ANGARIACAO = "angariacao"
TIPOS = (TIPO_ORGANICA, TIPO_ANGARIACAO)

ROTULOS = {
    TIPO_ORGANICA: "Veio diretamente à empresa",
    TIPO_ANGARIACAO: "Foi angariado por um utilizador específico",
}

PAPEIS_DE_GESTAO = ("admin", "ceo", "diretor")
#: Atravessam redes (reconciliam a pilha inteira).
PAPEIS_SEM_FRONTEIRA = ("admin", "ceo")

ERRO_PROCESSO_NAO_ENCONTRADO = "Processo não encontrado"
ERRO_SEM_PERMISSAO = "Só a gestão (administração, CEO e direcção) vê e altera a origem financeira."
ERRO_NAO_E_A_CASA_DONA = "Só a empresa dona do processo pode definir a origem financeira."
ERRO_TIPO_INVALIDO = "Origem financeira inválida: escolha «veio diretamente» ou «angariado por»."
ERRO_FALTA_ANGARIADOR = "Indique o utilizador que angariou o cliente."
ERRO_ANGARIADOR_INVALIDO = "O utilizador que angariou o cliente não existe, está inactivo ou não pertence à sua organização."


class OrigemFinanceiraBody(BaseModel):
    """Corpo do PUT. O valor do `tipo` valida-se em `validar_pedido`."""

    tipo: str
    angariador_id: Optional[str] = None


class OrigemFinanceiraInvalida(ValueError):
    """O pedido não descreve uma origem válida (a mensagem é para o utilizador)."""


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def validar_pedido(tipo: Any, angariador_id: Any) -> tuple[str, Optional[str]]:
    """Normaliza o pedido. Pura.

    `organica` descarta o angariador (regra 4): guardá-lo deixava um nome
    que o cálculo de comissões podia ler como se fosse uma atribuição.
    """
    tipo_normalizado = _texto(tipo).lower()
    if tipo_normalizado not in TIPOS:
        raise OrigemFinanceiraInvalida(ERRO_TIPO_INVALIDO)
    if tipo_normalizado == TIPO_ORGANICA:
        return tipo_normalizado, None
    angariador = _texto(angariador_id)
    if not angariador:
        raise OrigemFinanceiraInvalida(ERRO_FALTA_ANGARIADOR)
    return tipo_normalizado, angariador


def descrever(process_id: str, doc: Optional[dict]) -> dict:
    """O que a API devolve. Sem documento: a origem ainda não foi definida."""
    if not doc:
        return {
            "process_id": process_id,
            "definida": False,
            "tipo": None,
            "rotulo": None,
            "angariador": None,
            "definido_por": None,
            "definido_em": None,
        }
    tipo = doc.get("tipo")
    angariador = None
    if tipo == TIPO_ANGARIACAO and doc.get("angariador_id"):
        angariador = {
            "id": doc.get("angariador_id"),
            "nome": doc.get("angariador_nome"),
            "papel": doc.get("angariador_papel"),
        }
    return {
        "process_id": process_id,
        "definida": tipo in TIPOS,
        "tipo": tipo if tipo in TIPOS else None,
        "rotulo": ROTULOS.get(tipo),
        "angariador": angariador,
        "definido_por": doc.get("definido_por_nome"),
        "definido_em": doc.get("definido_em"),
    }


def _resumo_para_o_trilho(doc: Optional[dict]) -> Optional[str]:
    """Texto do trilho de auditoria (só gestão o lê). Aceita `None`."""
    if not doc or doc.get("tipo") not in TIPOS:
        return None
    if doc.get("tipo") == TIPO_ANGARIACAO:
        return f"angariacao:{doc.get('angariador_id')}"
    return TIPO_ORGANICA


async def _exigir_gestao(user: dict, request: Optional[Request]) -> str:
    """O papel EFECTIVO tem de ser de gestão; devolve-o."""
    papel = await resolver_papel_efectivo(
        user, request,
        traduzir_todos_os_perfis=lambda p: str(p or "").strip().lower() in PAPEIS_DE_GESTAO,
    )
    if papel.lower() not in PAPEIS_DE_GESTAO:
        raise HTTPException(status_code=403, detail=ERRO_SEM_PERMISSAO)
    return papel.lower()


async def _carregar_processo(process_id: str, user: dict, papel: str) -> dict:
    """O processo, se o utilizador o vê e a casa dele o detém (404 / 403)."""
    scope = await resolve_tenant_scope(user)
    processo = await db.processes.find_one(
        {"id": process_id},
        {"_id": 0, "id": 1, "process_number": 1, "partner_network_ids": 1, **PROJECCAO_DO_CARIMBO},
    )
    atravessa_redes = papel in PAPEIS_SEM_FRONTEIRA
    if not processo or not (atravessa_redes or processo_no_ambito(processo, scope)):
        raise HTTPException(status_code=404, detail=ERRO_PROCESSO_NAO_ENCONTRADO)
    # Vê o processo — mas é a casa DONA que decide a quem se atribui o negócio.
    if not atravessa_redes and not documento_no_ambito(processo, scope):
        raise HTTPException(status_code=403, detail=ERRO_NAO_E_A_CASA_DONA)
    return processo


async def _utilizadores_do_ambito(user: dict, extra: Optional[dict] = None, limite: int = 300) -> list[dict]:
    from services.admin_users_scope import build_users_scope_query, empresas_do_ambito

    ambito_query = await build_users_scope_query(await empresas_do_ambito(user))
    condicoes = [{"is_active": {"$ne": False}}, ambito_query]
    if extra:
        condicoes.append(extra)
    return await db.users.find(
        {"$and": condicoes}, {"_id": 0, "id": 1, "name": 1, "role": 1},
    ).sort("name", 1).to_list(limite)


async def run_get_origem(process_id: str, user: dict, request: Optional[Request] = None) -> dict:
    """GET — a origem definida (ou `definida: false`)."""
    papel = await _exigir_gestao(user, request)
    await _carregar_processo(process_id, user, papel)
    doc = await db.process_financial_origins.find_one({"process_id": process_id}, {"_id": 0})
    return descrever(process_id, doc)


async def run_list_candidatos(process_id: str, user: dict, request: Optional[Request] = None) -> dict:
    """GET — quem pode ser escolhido como angariador (carregado ao editar)."""
    papel = await _exigir_gestao(user, request)
    await _carregar_processo(process_id, user, papel)
    utilizadores = await _utilizadores_do_ambito(user)
    return {
        "process_id": process_id,
        "candidatos": [
            {"id": u["id"], "nome": u.get("name") or "", "papel": u.get("role")}
            for u in utilizadores if u.get("id")
        ],
    }


async def run_set_origem(
    process_id: str,
    tipo: Any,
    angariador_id: Any,
    user: dict,
    request: Optional[Request] = None,
) -> dict:
    """PUT — define ou altera a origem. Idempotente: igual → sem rasto."""
    papel = await _exigir_gestao(user, request)
    processo = await _carregar_processo(process_id, user, papel)

    try:
        tipo_final, angariador_final = validar_pedido(tipo, angariador_id)
    except OrigemFinanceiraInvalida as erro:
        raise HTTPException(status_code=422, detail=str(erro))

    angariador = None
    if angariador_final:
        encontrados = await _utilizadores_do_ambito(user, {"id": angariador_final}, limite=1)
        if not encontrados:
            raise HTTPException(status_code=422, detail=ERRO_ANGARIADOR_INVALIDO)
        angariador = encontrados[0]

    antes = await db.process_financial_origins.find_one({"process_id": process_id}, {"_id": 0})
    if (
        antes
        and antes.get("tipo") == tipo_final
        and (antes.get("angariador_id") or None) == (angariador_final or None)
    ):
        return descrever(process_id, antes)

    agora = datetime.now(timezone.utc).isoformat()
    documento = {
        "process_id": process_id,
        "tipo": tipo_final,
        "angariador_id": angariador["id"] if angariador else None,
        "angariador_nome": (angariador.get("name") if angariador else None),
        "angariador_papel": (angariador.get("role") if angariador else None),
        "definido_por_id": user.get("id"),
        "definido_por_nome": user.get("name"),
        "definido_em": agora,
        # O carimbo do PROCESSO: a origem é do mesmo âmbito que ele.
        **{c: processo[c] for c in CAMPOS_DO_CARIMBO if processo.get(c) not in (None, "")},
    }
    # Upsert por `process_id` (índice único): duas escritas concorrentes
    # convergem numa só origem — a última vence, sem duplicar.
    await db.process_financial_origins.update_one(
        {"process_id": process_id}, {"$set": documento}, upsert=True,
    )

    await _deixar_rasto(process_id, user, request, papel, antes, documento)
    return descrever(process_id, documento)


async def _deixar_rasto(
    process_id: str,
    user: dict,
    request: Optional[Request],
    papel: str,
    antes: Optional[dict],
    depois: dict,
) -> None:
    """Histórico (sem valores) + trilho de auditoria (com). **Nunca** propaga."""
    if _is_stealth_user(user):
        return
    try:
        # SEM valores: o histórico do processo é lido por quem não vê a origem.
        await log_history(process_id, user, "Atualizou a origem financeira", "origem_financeira")
    except Exception as erro:  # o rasto não falha a operação
        logger.warning("[ORIGEM-FIN] Histórico não gravado para %s: %s", process_id, erro)
    try:
        from services.audit_trail_service import log_audit_event

        await log_audit_event(
            process_id, user, "Atualizou a origem financeira",
            field="origem_financeira",
            old_value=_resumo_para_o_trilho(antes),
            new_value=_resumo_para_o_trilho(depois),
            request=request,
            metadata={"papel_efectivo": papel},
        )
    except Exception as erro:
        logger.warning("[ORIGEM-FIN] Trilho de auditoria não gravado para %s: %s", process_id, erro)
