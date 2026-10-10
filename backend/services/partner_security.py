"""
====================================================================
PORTAL DO PARCEIRO — O PLANO DE IDENTIDADE (V1, Out 2026)
====================================================================
Este módulo é a PORTA do Portal do Parceiro: o segredo, o token e a
dependência `get_current_partner`.

PORQUE É UM PLANO À PARTE E NÃO UM UTILIZADOR DO STAFF COM UM PAPEL
RESTRITO
  1. **O isolamento não pode depender de varrer o staff.** Se o parceiro
     passasse pelo `get_current_user`, a segurança dependia de cada rota
     do CRM perguntar pelo OBJECTO (e o D-31 é a lista das que não
     perguntam). Com um token de outra família, o `get_current_user`
     recusa-o por construção — nem sequer chega a procurar o `sub`.
  2. **Um utilizador sem UCR herda a rede de omissão.**
     `resolve_tenant_scope` dá a um utilizador órfão de empresa a rede
     incumbente. Um parceiro em `db.users` sem UCR passaria a ver, em
     cada endpoint que use esse resolvedor, o «andar inteiro».
  3. **Registo positivo, nunca lista de exclusão.** Hoje `parceiro` vive
     em `block_parceiro` espalhado e em `ROLE_CAPABILITY_DEFAULTS = {}`.
     Aqui o parceiro só alcança as rotas de `routes/partner_portal.py`,
     e há um inventário por AST a afirmá-lo.

O SEGREDO É PRÓPRIO (`JWT_PARTNER_SECRET`)
  O D-2 está aberto porque separar o segredo do Portal do Cliente do do
  staff invalida os magic links em circulação. Aqui não há nada em
  circulação, e a família nasce limpa: um token de parceiro não verifica
  sob o `JWT_SECRET` (nem o de staff sob este), pelo que a claim `type`
  deixa de ser a ÚNICA coisa que separa as famílias — é a segunda linha.

  Em produção sem variável o Portal do Parceiro **desliga-se** (503) em
  vez de matar a aplicação: é uma funcionalidade nova e opcional, e
  um `sys.exit` no arranque derrubaria o CRM inteiro por causa dela. O
  que nunca se faz é assinar com um valor por omissão público (D-3).
  Fora de produção deriva-se, por HMAC, um segredo estável do
  `JWT_SECRET` — estável para os vários workers, e DIFERENTE do
  `JWT_SECRET` para as famílias não se cruzarem nem em dev.

O ESTADO RELÊ-SE EM CADA PEDIDO
  O token só diz quem é (`sub`) e a «geração» (`tv`). Estado (activo ou
  suspenso), redes e geração vêm da base de dados a cada pedido: suspender
  um parceiro, ou mudar-lhe a password, mata as sessões na hora e não
  espera pela expiração do token (a lição do `portal_estado`).
====================================================================
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from database import db

logger = logging.getLogger(__name__)

#: A claim `type` dos tokens desta família. Os do staff são `"access"` e os
#: do Portal do Cliente `magic_link` / `verified_session` /
#: `access_code_session`; nenhuma outra família usa este valor.
TIPO_DO_PARCEIRO = "partner"
AUDIENCIA = "powercell-partner"
ALGORITMO = "HS256"

#: Uma sessão de trabalho. Sem refresh na V1: expirar obriga a novo login,
#: que é o travão de força bruta a funcionar de novo.
HORAS_DE_VALIDADE = 8

ENV_DO_SEGREDO = "JWT_PARTNER_SECRET"
TAMANHO_MINIMO_DO_SEGREDO = 32
AMBIENTES_DE_PRODUCAO = ("production", "prod")

ESTADO_CONVIDADO = "invited"
ESTADO_ACTIVO = "active"
ESTADO_SUSPENSO = "suspended"

_esquema = HTTPBearer(auto_error=False)


class PortalDoParceiroDesligado(HTTPException):
    """Produção sem `JWT_PARTNER_SECRET`: a funcionalidade não arranca."""

    def __init__(self) -> None:
        super().__init__(
            status_code=503,
            detail="O Portal do Parceiro não está disponível de momento.",
        )


def _em_producao() -> bool:
    ambiente = (os.environ.get("ENVIRONMENT") or os.environ.get("APP_ENV") or "dev")
    return ambiente.strip().lower() in AMBIENTES_DE_PRODUCAO


def resolver_segredo(
    *,
    em_producao: bool,
    valor: Optional[str],
    jwt_secret: Optional[str],
) -> Optional[str]:
    """O segredo do Portal do Parceiro, ou `None` (= desligado). PURA.

    * variável definida e com tamanho suficiente → usa-se;
    * variável definida mas CURTA → `None` em qualquer ambiente (um
      segredo fraco é pior do que nenhum: assina tokens e parece ligado);
    * sem variável em produção → `None` (desligado, nunca um literal);
    * sem variável fora de produção → derivado do `JWT_SECRET` por HMAC
      com uma etiqueta própria: estável entre workers e **diferente** do
      `JWT_SECRET`.
    """
    if valor:
        if len(valor) < TAMANHO_MINIMO_DO_SEGREDO:
            logger.error(
                "[PARCEIRO] %s tem %d caracteres (mínimo %d) — Portal do "
                "Parceiro desligado.", ENV_DO_SEGREDO, len(valor),
                TAMANHO_MINIMO_DO_SEGREDO,
            )
            return None
        return valor

    if em_producao:
        return None

    if not jwt_secret:
        return None
    return hmac.new(
        jwt_secret.encode("utf-8"),
        b"powercell:partner-portal:dev-only",
        hashlib.sha256,
    ).hexdigest()


def _segredo() -> str:
    from config import JWT_SECRET

    segredo = resolver_segredo(
        em_producao=_em_producao(),
        valor=os.environ.get(ENV_DO_SEGREDO),
        jwt_secret=JWT_SECRET,
    )
    if not segredo:
        logger.error(
            "[PARCEIRO] %s por definir (ou inválido) em produção — Portal do "
            "Parceiro desligado.", ENV_DO_SEGREDO,
        )
        raise PortalDoParceiroDesligado()
    return segredo


def chave_de_limite_do_parceiro(token: str) -> Optional[str]:
    """`partner:<id>` para um token de parceiro com assinatura válida, ou `None`.

    O limiter chaveia por IDENTIDADE quando consegue: o IP sai do
    `X-Forwarded-For`, que o cliente envia (D-4), e um limite por IP que se
    contorna a cada pedido não é limite. Só confirma a assinatura (não o
    estado): serve para contar, não para autorizar. Nunca levanta.
    """
    try:
        from config import JWT_SECRET

        segredo = resolver_segredo(
            em_producao=_em_producao(),
            valor=os.environ.get(ENV_DO_SEGREDO),
            jwt_secret=JWT_SECRET,
        )
        if not segredo:
            return None
        payload = jwt.decode(token, segredo, algorithms=[ALGORITMO], audience=AUDIENCIA)
        if payload.get("type") == TIPO_DO_PARCEIRO and payload.get("sub"):
            return f"partner:{payload['sub']}"
    except Exception:  # noqa: BLE001 — um token mau cai no IP, como antes
        return None
    return None


def exigir_portal_ligado() -> None:
    """503 se o Portal do Parceiro está desligado (produção sem segredo).

    Chamada à ENTRADA de cada operação que emite ou aceita sessões: um
    login que verificasse a palavra-passe e só depois descobrisse que não
    pode assinar o token já gastou as tentativas do parceiro.
    """
    _segredo()


def portal_do_parceiro_ligado() -> bool:
    try:
        exigir_portal_ligado()
        return True
    except PortalDoParceiroDesligado:
        return False


def create_partner_token(partner: dict, *, agora: Optional[datetime] = None) -> str:
    """Token de sessão do parceiro. Só `sub`, `tv` e o tempo: nada de estado."""
    agora = agora or datetime.now(timezone.utc)
    payload = {
        "sub": partner["id"],
        "type": TIPO_DO_PARCEIRO,
        "aud": AUDIENCIA,
        "tv": int(partner.get("token_epoch") or 0),
        "iat": agora,
        "exp": agora + timedelta(hours=HORAS_DE_VALIDADE),
    }
    return jwt.encode(payload, _segredo(), algorithm=ALGORITMO)


def redes_activas(partner: Optional[dict]) -> list[dict]:
    """As ligações do parceiro às redes que estão activas, na ordem gravada.

    O esquema guarda uma LISTA desde a V1 (um parceiro pode vir a trabalhar
    com mais do que uma rede). Uma ligação sem `network_id` nunca conta.
    """
    if not partner:
        return []
    return [
        r for r in (partner.get("redes") or [])
        if isinstance(r, dict)
        and str(r.get("network_id") or "").strip()
        and (r.get("status") or ESTADO_ACTIVO) == ESTADO_ACTIVO
    ]


def ids_das_redes_activas(partner: Optional[dict]) -> list[str]:
    return list(dict.fromkeys(str(r["network_id"]).strip() for r in redes_activas(partner)))


def _recusa(detalhe: str = "Sessão inválida ou expirada.") -> HTTPException:
    return HTTPException(status_code=401, detail=detalhe)


async def get_current_partner(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_esquema),
) -> dict:
    """Dependência do Portal do Parceiro.

    Valida assinatura, audiência, tipo e geração; relê o parceiro e
    exige-o activo e com pelo menos uma rede activa. **Todas** as recusas
    são o mesmo 401: distinguir «não existe» de «suspenso» a quem apresenta
    um token é dar um directório de contas.

    Devolve o documento do parceiro SEM o hash da password nem o convite.
    """
    if not credentials or not credentials.credentials:
        raise _recusa("Autenticação necessária.")

    segredo = _segredo()
    try:
        payload = jwt.decode(
            credentials.credentials,
            segredo,
            algorithms=[ALGORITMO],
            audience=AUDIENCIA,
        )
    except jwt.ExpiredSignatureError:
        raise _recusa("Sessão expirada. Inicie sessão novamente.")
    except jwt.InvalidTokenError:
        raise _recusa()

    if payload.get("type") != TIPO_DO_PARCEIRO or not payload.get("sub"):
        raise _recusa()

    partner = await db.partners.find_one(
        {"id": payload["sub"]},
        {"_id": 0, "password_hash": 0, "invite": 0},
    )
    if not partner:
        raise _recusa()
    # A projecção já os exclui; retirar aqui também faz a garantia não
    # depender de como cada driver (ou duplo de teste) interpreta uma
    # projecção de exclusão.
    for segredo_do_documento in ("password_hash", "invite"):
        partner.pop(segredo_do_documento, None)
    if partner.get("status") != ESTADO_ACTIVO:
        logger.warning("[PARCEIRO] Token recusado: %s está %s.", partner["id"], partner.get("status"))
        raise _recusa()
    if int(payload.get("tv") or 0) != int(partner.get("token_epoch") or 0):
        raise _recusa()
    if not redes_activas(partner):
        raise _recusa()
    return partner


def hash_de_token(token: str) -> str:
    """SHA-256 do token de convite — na base de dados nunca vai o token."""
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


__all__ = [
    "AUDIENCIA",
    "ESTADO_ACTIVO",
    "ESTADO_CONVIDADO",
    "ESTADO_SUSPENSO",
    "HORAS_DE_VALIDADE",
    "PortalDoParceiroDesligado",
    "TIPO_DO_PARCEIRO",
    "chave_de_limite_do_parceiro",
    "create_partner_token",
    "exigir_portal_ligado",
    "get_current_partner",
    "hash_de_token",
    "ids_das_redes_activas",
    "portal_do_parceiro_ligado",
    "redes_activas",
    "resolver_segredo",
]
