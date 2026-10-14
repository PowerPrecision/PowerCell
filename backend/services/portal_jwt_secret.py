"""O segredo dos tokens do Portal do Cliente — separado do do staff, com janela de rotação (D-2, Lote 5).

O DEFEITO
  Os tokens do Portal (magic link, sessão verificada, sessão por código) e os do staff eram assinados
  com o MESMO `JWT_SECRET`. O que os separava era a claim `type` (autoritativa nos dois verificadores) —
  defesa em profundidade a menos: um erro futuro num verificador de tipo voltava a ser explorável em vez
  de inofensivo.

A MUDANÇA, SEM INVALIDAR NADA
  Separar os segredos invalida todos os magic links em circulação (90 dias de validade) — por isso é uma
  decisão do operador, em dois passos:

    1. definir `PORTAL_JWT_SECRET` (≥ 32 caracteres, diferente do `JWT_SECRET`): os tokens NOVOS passam a
       ser assinados com ele; os antigos (assinados com `JWT_SECRET`) continuam a ser aceites;
    2. passados 90 dias (o magic link mais longo) — ou quando se aceitar a invalidação —,
       `PORTAL_JWT_ACCEPT_LEGACY=false`: só o segredo do Portal é aceite.

  Sem `PORTAL_JWT_SECRET` nada muda (assina-se e verifica-se com `JWT_SECRET`). Um valor curto ou igual
  ao `JWT_SECRET` é IGNORADO com um erro no log, nunca usado: um segredo igual ao do staff seria só o
  mesmo defeito com mais um passo.

O QUE O STAFF GANHA
  Um token assinado com o segredo do Portal não valida no `get_current_user` (nem no socket de staff):
  a separação deixa de depender de ninguém ter escrito bem uma comparação de `type`.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import jwt

from config import JWT_ALGORITHM, JWT_SECRET

logger = logging.getLogger(__name__)

TAMANHO_MINIMO = 32
_ja_avisou: set[str] = set()


def _avisar_uma_vez(chave: str, mensagem: str) -> None:
    if chave not in _ja_avisou:
        _ja_avisou.add(chave)
        logger.error(mensagem)


def segredo_proprio_do_portal() -> Optional[str]:
    """O `PORTAL_JWT_SECRET`, se estiver definido E for utilizável; senão ``None``."""
    valor = (os.environ.get("PORTAL_JWT_SECRET") or "").strip()
    if not valor:
        return None
    if len(valor) < TAMANHO_MINIMO:
        _avisar_uma_vez(
            "curto",
            f"[PORTAL-JWT] PORTAL_JWT_SECRET tem menos de {TAMANHO_MINIMO} caracteres: IGNORADO "
            "(o Portal continua a usar o JWT_SECRET).",
        )
        return None
    if valor == JWT_SECRET:
        _avisar_uma_vez(
            "igual",
            "[PORTAL-JWT] PORTAL_JWT_SECRET é igual ao JWT_SECRET: IGNORADO (não separa nada).",
        )
        return None
    return valor


def aceita_o_segredo_antigo() -> bool:
    """Durante a janela de rotação o `JWT_SECRET` continua a valer para tokens do Portal."""
    return (os.environ.get("PORTAL_JWT_ACCEPT_LEGACY") or "true").strip().lower() not in {"0", "false", "no", "nao", "não"}


def segredo_de_assinatura() -> str:
    """Com que segredo se ASSINA um token novo do Portal."""
    return segredo_proprio_do_portal() or JWT_SECRET


def segredos_de_verificacao() -> list[str]:
    """Os segredos que um token do Portal pode trazer, por ordem de tentativa."""
    proprio = segredo_proprio_do_portal()
    if not proprio:
        return [JWT_SECRET]
    return [proprio, JWT_SECRET] if aceita_o_segredo_antigo() else [proprio]


def descodificar_token_do_portal(token: str, **opcoes) -> dict:
    """Descodifica um token do Portal contra os segredos em vigor.

    Uma assinatura que não bate com um segredo passa ao seguinte; um token EXPIRADO é reportado como
    tal (o PyJWT só verifica a expiração depois da assinatura, logo `ExpiredSignatureError` prova que a
    assinatura é válida). Se nenhum segredo servir, levanta o último erro.
    """
    ultimo: Optional[Exception] = None
    for segredo in segredos_de_verificacao():
        try:
            return jwt.decode(token, segredo, algorithms=[JWT_ALGORITHM], **opcoes)
        except jwt.ExpiredSignatureError:
            raise
        except jwt.PyJWTError as exc:
            ultimo = exc
    assert ultimo is not None
    raise ultimo


__all__ = [
    "aceita_o_segredo_antigo",
    "descodificar_token_do_portal",
    "segredo_de_assinatura",
    "segredo_proprio_do_portal",
    "segredos_de_verificacao",
]
