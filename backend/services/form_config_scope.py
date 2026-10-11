"""Formulário público POR REDE — onde vive, como se lê e como se escreve (Out 2026, D-37).

O PROBLEMA
  O `form_config` (campos, passos, rótulos e opções do registo público) era um
  único documento global: editá-lo mudava o formulário de todas as empresas. Cada
  empresa tem o seu próprio registo público — a Domus não pergunta o que a
  Precision pergunta — e quem a gere (Admin/CEO) tem de poder editar o seu sem
  tocar no de ninguém.

O MODELO  (o mesmo do workflow, de propósito)
  * um documento `{type: "public_form", network_id: <rede>}` POR REDE;
  * o documento SEM `network_id` é o MODELO: é o que existia antes da migração,
    a semente das redes novas e o recurso das que ainda não têm o seu;
  * **leitura**: a cópia da rede, senão o modelo, senão os defaults do código;
  * **escrita (copy-on-write)**: a primeira escrita materializa a cópia da rede a
    partir do modelo (`garantir_formulario_da_rede`) e é nela que se escreve. O
    modelo nunca é editado por esta via.

QUEM DIZ QUE REDE
  * o ecrã de administração: a rede EM CONTEXTO de quem edita (a empresa activa —
    `workflow_scope.rede_em_contexto`);
  * o link público: o identificador da EMPRESA (`?empresa=<company_id>`), resolvido
    aqui para a rede dela. Um identificador desconhecido ou de uma empresa
    inactiva é 404 — **nunca** cai no formulário de outra empresa: carregar o
    formulário errado e registar nele era o defeito que isto veio fechar. Um link
    SEM identificador (os que já andam em emails e favoritos) usa a rede de
    omissão, e di-lo no log.
"""
from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException

from database import db
from services.form_config_defaults import DEFAULT_FORM_CONFIG, DEFAULT_STEP_CONFIG
from services.tenant_network import CAMPO_REDE, rede_de_omissao, resolve_network_id

logger = logging.getLogger(__name__)

TIPO = "public_form"
SEM_REDE = {"$in": [None, ""]}
ERRO_EMPRESA_DESCONHECIDA = "Link de registo inválido ou empresa indisponível"


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor not in (None, "") else ""


async def ler_documento(rede: Optional[str]) -> Optional[dict]:
    """O documento do formulário que a `rede` vê: o seu, senão o modelo, senão ``None``."""
    chave = _texto(rede)
    if chave:
        proprio = await db.form_config.find_one({"type": TIPO, CAMPO_REDE: chave}, {"_id": 0})
        if proprio:
            return proprio
    return await db.form_config.find_one({"type": TIPO, CAMPO_REDE: SEM_REDE}, {"_id": 0})


async def tem_formulario_proprio(rede: str) -> bool:
    return bool(await db.form_config.find_one({"type": TIPO, CAMPO_REDE: _texto(rede)}, {"_id": 0, "type": 1}))


async def garantir_formulario_da_rede(rede: str) -> bool:
    """Materializa a cópia do formulário da rede a partir do modelo. ``True`` se criou.

    Idempotente e seguro sob concorrência: um `upsert` por (tipo, rede) com
    `$setOnInsert` — um segundo pedido, ou um concorrente, não sobrescreve nada.
    **Nunca** altera um formulário que a rede já tenha.
    """
    chave = _texto(rede)
    if not chave:
        raise ValueError("garantir_formulario_da_rede: rede vazia")

    modelo = await db.form_config.find_one({"type": TIPO, CAMPO_REDE: SEM_REDE}, {"_id": 0})
    base = {
        "fields": copy.deepcopy((modelo or {}).get("fields") or DEFAULT_FORM_CONFIG),
        "step_config": copy.deepcopy((modelo or {}).get("step_config") or DEFAULT_STEP_CONFIG),
        "step_labels": copy.deepcopy((modelo or {}).get("step_labels") or {}),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "copied_from_model": True,
    }
    resultado = await db.form_config.update_one(
        {"type": TIPO, CAMPO_REDE: chave},
        {"$setOnInsert": base},
        upsert=True,
    )
    # `matched_count == 0` e não `upserted_id`: a pergunta que o Mongo e o duplo respondem igual.
    criou = getattr(resultado, "matched_count", 1) == 0
    if criou:
        logger.info("[FORM_CONFIG] Rede %s: formulário materializado a partir do modelo.", chave)
    return criou


async def rede_do_link_publico(empresa: Optional[str]) -> tuple[Optional[str], Optional[dict]]:
    """``(rede, empresa)`` de um link de registo público.

    * com identificador: a EMPRESA tem de existir e estar activa, e a rede é a dela
      (uma empresa sem rede é uma ilha de uma só); senão 404 — nunca um recurso;
    * sem identificador: a rede de omissão (links antigos), ``empresa`` é ``None``.
    """
    ident = _texto(empresa)
    if not ident:
        omissao = rede_de_omissao()
        if not omissao:
            logger.warning(
                "[FORM_CONFIG] Link de registo sem empresa e sem TENANT_DEFAULT_NETWORK_ID: "
                "serve-se o modelo."
            )
        else:
            logger.info("[FORM_CONFIG] Link de registo sem empresa: rede de omissão %s.", omissao)
        return (omissao or None), None

    # Só o `id`: o nome não é uma identidade (dois homónimos escolhiam o formulário à sorte).
    doc = await db.companies.find_one(
        {"id": ident}, {"_id": 0, "id": 1, "name": 1, CAMPO_REDE: 1, "is_active": 1},
    )
    if not doc or doc.get("is_active") is False:
        raise HTTPException(status_code=404, detail=ERRO_EMPRESA_DESCONHECIDA)
    rede = resolve_network_id(doc, company_id=doc.get("id"))
    if not rede:
        raise HTTPException(status_code=404, detail=ERRO_EMPRESA_DESCONHECIDA)
    return rede, doc


__all__ = [
    "ERRO_EMPRESA_DESCONHECIDA",
    "SEM_REDE",
    "TIPO",
    "garantir_formulario_da_rede",
    "ler_documento",
    "rede_do_link_publico",
    "tem_formulario_proprio",
]
