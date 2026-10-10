"""
====================================================================
PROMOVER A MASTER: O PASSO OPERACIONAL DA ADENDA DE RBAC
====================================================================
Até aqui o `admin` era o perfil global. Depois da adenda, o Admin é
LOCAL e o único perfil global é o `master` — e **nenhuma conta existente
tem esse papel**. Sem este passo, no dia do deploy ninguém consegue
fazer backups, ver os logs, configurar a infra, nem editar as fases.

POR QUE NÃO SE FAZ SOZINHO
  Promover «todos os admins» a Master reproduzia exactamente o problema
  que a adenda resolve (um Admin de empresa com acesso global). Quem é
  Master é uma decisão de PESSOAS, tomada pelo dono do produto, e por
  isso o script pede os emails **explicitamente** e **só escreve com
  `--aplicar`**. A omissão é mostrar o que faria.

REGRAS (todas com teste)
  * só promove contas EXISTENTES, activas e com email resolvido — um
    email que não existe é um erro dito, nunca ignorado;
  * por omissão só promove quem hoje é `admin` ou `ceo` (as contas que
    tinham poder global ou quase). Promover um consultor a Master é
    plausível mas improvável; exige `--qualquer-papel`;
  * não altera `additional_roles` nem os UCRs — o Master continua a poder
    «vestir» o chapéu de Admin de uma empresa para testar o que um Admin vê;
  * deixa rasto em `audit_logs` (quem foi promovido, de que papel);
  * promover quem já é Master é um não-faz-nada, não um erro.
====================================================================
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

from models.auth import UserRole

PAPEIS_PROMOVIVEIS = (UserRole.ADMIN, UserRole.CEO)


@dataclass
class PlanoDePromocao:
    promover: list[dict] = field(default_factory=list)
    ja_master: list[dict] = field(default_factory=list)
    recusados: list[tuple[str, str]] = field(default_factory=list)  # (email, motivo)

    @property
    def pode_aplicar(self) -> bool:
        """Só se aplica um plano sem recusas: meio plano é pior do que nenhum."""
        return bool(self.promover) and not self.recusados


def normalizar_emails(emails: Iterable[str]) -> list[str]:
    vistos: dict[str, None] = {}
    for bruto in emails or ():
        for parte in str(bruto).split(","):
            e = parte.strip().lower()
            if e:
                vistos.setdefault(e, None)
    return list(vistos)


def planear(
    emails: Iterable[str],
    utilizadores: Iterable[dict],
    *,
    qualquer_papel: bool = False,
) -> PlanoDePromocao:
    """Decide, sem escrever, quem é promovido. Pura."""
    por_email = {str(u.get("email") or "").strip().lower(): u for u in utilizadores}
    plano = PlanoDePromocao()

    for email in normalizar_emails(emails):
        utilizador = por_email.get(email)
        if not utilizador:
            plano.recusados.append((email, "não existe nenhuma conta com este email"))
            continue
        if utilizador.get("is_active") is False:
            plano.recusados.append((email, "a conta está desactivada"))
            continue
        papel = str(utilizador.get("role") or "").strip().lower()
        if papel == UserRole.MASTER:
            plano.ja_master.append(utilizador)
            continue
        if papel not in PAPEIS_PROMOVIVEIS and not qualquer_papel:
            plano.recusados.append((
                email,
                f"o papel actual é '{papel or '—'}'; só se promove admin/ceo "
                "sem --qualquer-papel",
            ))
            continue
        plano.promover.append(utilizador)
    return plano


async def aplicar(plano: PlanoDePromocao, base, *, executado_por: str = "script") -> int:
    """Escreve a promoção e o rasto. Devolve quantas contas mudaram."""
    if not plano.pode_aplicar:
        raise ValueError("O plano tem recusas (ou nada a promover): nada foi escrito.")
    agora = datetime.now(timezone.utc).isoformat()
    mudadas = 0
    for utilizador in plano.promover:
        anterior = utilizador.get("role")
        resultado = await base.users.update_one(
            {"id": utilizador["id"]},
            {"$set": {"role": UserRole.MASTER, "previous_role": anterior, "role_changed_at": agora}},
        )
        if getattr(resultado, "modified_count", 1):
            mudadas += 1
            await base.audit_logs.insert_one({
                "id": str(uuid.uuid4()),
                "action": "promoted_to_master",
                "entity": "user",
                "entity_id": utilizador["id"],
                "performed_by_id": None,
                "performed_by_name": executado_por,
                "performed_by_email": None,
                "details": {"email": utilizador.get("email"), "previous_role": anterior},
                "timestamp": agora,
            })
    return mudadas


async def carregar_utilizadores(base, emails: Iterable[str]) -> list[dict]:
    alvo = normalizar_emails(emails)
    if not alvo:
        return []
    return await base.users.find(
        {"email": {"$in": alvo}},
        {"_id": 0, "id": 1, "email": 1, "name": 1, "role": 1, "is_active": 1},
    ).to_list(len(alvo) + 10)


__all__ = [
    "PAPEIS_PROMOVIVEIS",
    "PlanoDePromocao",
    "aplicar",
    "carregar_utilizadores",
    "normalizar_emails",
    "planear",
]
