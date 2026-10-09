"""Controlo de histórico: o admin liga/desliga o registo por pessoa e por perfil.

O PEDIDO (Bloco 1, ponto 4)
===========================
O master/admin activa ou desactiva, na área de gestão, se as acções ficam
guardadas no histórico para uma pessoa ou para um perfil. Por omissão,
tudo activo.

OS DOIS EIXOS — PESSOA VENCE PERFIL
===================================
* **pessoa** — `users.track_history` (`bool`, ausente = segue o perfil).
  O `history._is_stealth_user` já o honrava; faltava quem o gravasse;
* **perfil** — colecção `history_policy`, documento `_id: "roles"`:
  `{roles: {consultor: false}}`. Só se guardam os perfis DESLIGADOS: o
  default é «activo», e guardar `True` seria uma segunda forma de dizer
  a mesma coisa;
* a ordem é a dos overrides pessoais do `capability_gate`: o que é da
  pessoa vence o que é do cargo, e é por isso que uma excepção sobrevive
  à troca de chapéu.

A política segue o perfil EFECTIVO (UCR + `X-Active-Role`) e não o do
JWT — a forma do `history._is_stealth_user`, quinta ocorrência: base
consultor a trabalhar COMO diretor é avaliado como diretor.

ONDE SE APLICA, E PORQUÊ ALI
============================
No `get_current_user`, que já resolve o perfil efectivo: se a política
desliga o perfil e a pessoa não tem override, o utilizador chega às rotas
com `track_history = False` — que é a chave que `_is_stealth_user` e os
escritores com utilizadores "de sistema" já leem. Resolver no
`log_history` obrigava a um acesso à base de dados por cada linha de
histórico; o `_is_stealth_user` é puro e síncrono e assim fica.

A política tem cache em memória de 30 s por worker (uma leitura a mais
por pedido, não). Uma escrita invalida a do worker que a recebeu; os
outros apanham-na no máximo 30 s depois — aceitável para um interruptor
de gestão, e dito no ecrã.

AS TRÊS REGRAS DE SEGURANÇA
===========================
1. **`indexacao` nunca se liga.** É silenciosa por regra de ouro
   (`_is_stealth_user`, regra 1/1b) e nada aqui a toca: a API recusa
   guardar uma política para ela e recusa um override ligado a quem tem
   `indexacao` como perfil de base. Mesmo com o estado forjado na base de
   dados o `_is_stealth_user` ganha — defesa em profundidade;
2. **falha na leitura da política = tudo activo** (com aviso). Registar de
   mais é recuperável; perder histórico não é;
3. **o `audit_trail_service` fica fora**: é conformidade (IP, retenção) e
   este interruptor é sobre o histórico visível do processo.

A decisão de ligar/desligar fica escrita em `audit_logs` — quem desligou
o histórico de quem tem de se saber — EXCEPTO quando o actor é, ele
próprio, silenciado (restrição de segurança: o perfil `indexacao` não
gera registos).
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Optional

from fastapi import HTTPException

from database import db
from models.auth import UserRoleEnum
from services.admin_helpers import _audit_log
from services.history import _is_stealth_user

logger = logging.getLogger(__name__)

COLECCAO = "history_policy"
DOCUMENTO = "roles"
TTL_SEGUNDOS = 30

#: Sempre silencioso. O interruptor nunca lhe toca.
PERFIL_SEMPRE_SILENCIOSO = UserRoleEnum.INDEXACAO.value

#: `cliente` é um pseudo-perfil (processos, não utilizadores do sistema).
PERFIS_GERIVEIS = tuple(
    papel.value for papel in UserRoleEnum
    if papel.value not in {UserRoleEnum.CLIENTE.value, PERFIL_SEMPRE_SILENCIOSO}
)
TODOS_OS_PERFIS = PERFIS_GERIVEIS + (PERFIL_SEMPRE_SILENCIOSO,)

MOTIVO_INDEXACAO = (
    "O perfil Indexação é sempre silencioso: as suas acções nunca geram "
    "registos, e este interruptor não o pode alterar."
)

_cache: dict[str, Any] = {"politica": None, "em": 0.0}


def _texto(valor: Any) -> str:
    return str(getattr(valor, "value", valor) or "").strip().lower()


def invalidar_cache() -> None:
    _cache["politica"] = None
    _cache["em"] = 0.0


async def _ler_politica_da_base() -> dict[str, bool]:
    doc = await db[COLECCAO].find_one({"_id": DOCUMENTO}, {"_id": 0, "roles": 1}) or {}
    roles = doc.get("roles") or {}
    if not isinstance(roles, dict):
        return {}
    return {_texto(k): bool(v) for k, v in roles.items() if _texto(k)}


async def carregar_politica() -> dict[str, bool]:
    """A política por perfil (só os desligados), com cache curta.

    Falha FECHADA para o lado do registo: sem poder ler, devolve `{}` —
    tudo activo — e avisa.
    """
    agora = time.monotonic()
    if _cache["politica"] is not None and agora - _cache["em"] < TTL_SEGUNDOS:
        return _cache["politica"]
    try:
        politica = await _ler_politica_da_base()
    except Exception as exc:
        logger.warning(
            "[HISTÓRICO] Falha a ler a política de histórico por perfil (%s); "
            "o histórico fica ACTIVO para todos até a leitura recuperar.", exc,
        )
        return {}
    _cache["politica"] = politica
    _cache["em"] = agora
    return politica


def historico_efectivo(user: Optional[dict], papel_efectivo: Any, politica: dict[str, bool]) -> bool:
    """Este utilizador deixa rasto no histórico? Pura.

    1. `indexacao` (de base ou em exercício) → nunca;
    2. override da PESSOA (`bool`) → vence o perfil;
    3. perfil desligado na política → não;
    4. o resto → sim.
    """
    papeis = {_texto((user or {}).get("role")), _texto(papel_efectivo)}
    if PERFIL_SEMPRE_SILENCIOSO in papeis:
        return False
    pessoal = (user or {}).get("track_history")
    if isinstance(pessoal, bool):
        return pessoal
    return politica.get(_texto(papel_efectivo)) is not False


async def aplicar_politica_de_historico(user: dict) -> dict:
    """Chamado pelo `get_current_user`, depois de resolver o perfil efectivo.

    Só ESCREVE no utilizador quando a política desliga o registo e a pessoa
    não tem override: o campo `track_history` do documento é a decisão da
    pessoa e não se sobrepõe; o resto do sistema continua a ver o mesmo
    payload de sempre.
    """
    if not user:
        return user
    politica = await carregar_politica()
    if politica and not historico_efectivo(user, user.get("effective_role"), politica):
        user["track_history"] = False
    return user


# ────────────────────────────────────────────────────────────────────
#  Gestão (ADMIN)
# ────────────────────────────────────────────────────────────────────
async def _auditar(accao: str, entidade: str, entidade_id: str, actor: dict, detalhes: dict) -> None:
    """Quem desligou o histórico de quem. Nunca para o actor silenciado."""
    if _is_stealth_user(actor):
        return
    await _audit_log(accao, entidade, entidade_id, actor, detalhes)


async def run_get_history_tracking(user: dict) -> dict:
    """Os perfis e o estado do registo de cada um."""
    politica = await _ler_politica_da_base_ou_vazia()
    perfis = []
    for papel in TODOS_OS_PERFIS:
        bloqueado = papel == PERFIL_SEMPRE_SILENCIOSO
        perfis.append({
            "role": papel,
            "enabled": False if bloqueado else politica.get(papel) is not False,
            "locked": bloqueado,
            "motivo": MOTIVO_INDEXACAO if bloqueado else None,
        })
    return {"perfis": perfis, "padrao": True, "cache_segundos": TTL_SEGUNDOS}


async def _ler_politica_da_base_ou_vazia() -> dict[str, bool]:
    try:
        return await _ler_politica_da_base()
    except Exception as exc:
        logger.warning("[HISTÓRICO] Falha a ler a política (%s); a mostrar tudo activo.", exc)
        return {}


async def run_set_role_history(role: str, enabled: bool, user: dict) -> dict:
    papel = _texto(role)
    if papel == PERFIL_SEMPRE_SILENCIOSO:
        raise HTTPException(status_code=400, detail=MOTIVO_INDEXACAO)
    if papel not in PERFIS_GERIVEIS:
        raise HTTPException(status_code=400, detail=f"Perfil inválido: '{role}'")

    antes = (await _ler_politica_da_base_ou_vazia()).get(papel) is not False
    if enabled:
        # O default é «activo»: remove-se a entrada em vez de guardar True.
        await db[COLECCAO].update_one(
            {"_id": DOCUMENTO}, {"$unset": {f"roles.{papel}": ""}}, upsert=True
        )
    else:
        await db[COLECCAO].update_one(
            {"_id": DOCUMENTO}, {"$set": {f"roles.{papel}": False}}, upsert=True
        )
    invalidar_cache()
    await _auditar(
        "history_tracking_role_changed", "role", papel, user,
        {"anterior": antes, "novo": bool(enabled)},
    )
    return {"success": True, "role": papel, "enabled": bool(enabled)}


async def run_list_users_history(
    search: Optional[str] = None, page: int = 1, size: int = 25
) -> dict:
    """Utilizadores com o override pessoal e o estado EFECTIVO do registo."""
    query: dict = {}
    termo = (search or "").strip()
    if termo:
        regex = {"$regex": re.escape(termo), "$options": "i"}
        query = {"$or": [{"name": regex}, {"email": regex}]}

    total = await db.users.count_documents(query)
    cursor = db.users.find(
        query, {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "is_active": 1, "track_history": 1}
    ).sort("name", 1).skip(max(page - 1, 0) * size).limit(size)
    linhas = await cursor.to_list(size)

    politica = await _ler_politica_da_base_ou_vazia()
    utilizadores = []
    for u in linhas:
        bloqueado = _texto(u.get("role")) == PERFIL_SEMPRE_SILENCIOSO
        override = u.get("track_history") if isinstance(u.get("track_history"), bool) else None
        utilizadores.append({
            "id": u.get("id"),
            "name": u.get("name"),
            "email": u.get("email"),
            "role": u.get("role"),
            "is_active": u.get("is_active", True),
            "track_history": override,
            "efectivo": historico_efectivo(u, u.get("role"), politica),
            "bloqueado": bloqueado,
        })
    return {"utilizadores": utilizadores, "total": total, "page": page, "size": size}


async def run_set_user_history(user_id: str, enabled: Optional[bool], user: dict) -> dict:
    alvo = await db.users.find_one(
        {"id": user_id}, {"_id": 0, "id": 1, "role": 1, "track_history": 1}
    )
    if not alvo:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    if _texto(alvo.get("role")) == PERFIL_SEMPRE_SILENCIOSO:
        raise HTTPException(status_code=400, detail=MOTIVO_INDEXACAO)

    antes = alvo.get("track_history") if isinstance(alvo.get("track_history"), bool) else None
    if enabled is None:
        await db.users.update_one({"id": user_id}, {"$unset": {"track_history": ""}})
    else:
        await db.users.update_one({"id": user_id}, {"$set": {"track_history": bool(enabled)}})
    await _auditar(
        "history_tracking_user_changed", "user", user_id, user,
        {"anterior": antes, "novo": enabled},
    )
    return {"success": True, "user_id": user_id, "track_history": enabled}
