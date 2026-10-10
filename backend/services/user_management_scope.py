"""
====================================================================
GESTÃO DE UTILIZADORES: QUEM PODE TOCAR EM QUEM (adenda de RBAC, Out 2026)
====================================================================
`require_roles` autoriza o VERBO («este perfil pode gerir utilizadores»),
não o OBJECTO («este utilizador»). Até aqui a gestão de utilizadores
tinha a listagem restringida à rede (Lote 5, ponto 11) mas **as escritas
não**:

  * `PUT /admin/users/{id}` aceitava `password` — o CEO da empresa A
    redefinia a password do CEO da empresa B sabendo o id;
  * `DELETE /admin/users/{id}` e `POST /admin/impersonate/{id}` idem;
  * `POST /admin/users/{id}/roles` e todo o router
    `/admin/user-company-roles` criavam, editavam e apagavam UCRs de
    qualquer pessoa em qualquer empresa — incluindo dar-se a si próprio
    o cargo `master`, que é a escalada de privilégios mais curta que
    este sistema podia ter.

Com o Admin passado a perfil LOCAL, estas escritas são a fronteira que
falta. Este módulo é o ponto único:

  1. **o alvo tem de estar no âmbito** de quem actua (as empresas da sua
     rede), senão **404** — nunca 403: distinguir «não existe» de «não é
     teu» transforma o endpoint num directório de utilizadores;
  2. **um perfil global nunca é alvo de um perfil local** — nem ver, nem
     editar, nem personificar. O Master não existe para o Admin;
  3. **só o Master concede `master`** — na criação, na edição, nos
     `additional_roles` e nos UCRs;
  4. **só se concede acesso a empresas do próprio âmbito** — um Admin da
     Domus não associa ninguém à Power.

Cobertura: `tests/unit/test_gestao_de_utilizadores_isolada.py`.
====================================================================
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

from fastapi import HTTPException

from database import db
from models.auth import normalizar_papel
from services.admin_users_scope import (
    build_users_scope_query,
    empresas_do_ambito,
)
from services.role_scope import (
    PAPEIS_GLOBAIS,
    e_papel_global,
    pode_conceder_papel,
    utilizador_e_global,
)

logger = logging.getLogger(__name__)

ERRO_UTILIZADOR_NAO_ENCONTRADO = "Utilizador não encontrado"
ERRO_EMPRESA_FORA_DO_AMBITO = "Empresa não encontrada"
ERRO_PAPEL_RESERVADO = "Apenas o perfil Master pode atribuir o perfil Master."


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor not in (None, "") else ""


async def carregar_utilizador_gerivel(
    alvo_id: str,
    actor: dict,
    *,
    projeccao: Optional[dict] = None,
) -> dict:
    """O utilizador-alvo, se quem actua o pode gerir. **404** caso contrário.

    O próprio actor é sempre gerível (editar o seu perfil). Para o resto:
    Master vê tudo; os restantes só os utilizadores das empresas da sua
    rede e **nunca** um perfil global.
    """
    projeccao = projeccao or {"_id": 0, "password": 0}
    alvo = await db.users.find_one({"id": alvo_id}, projeccao)
    if not alvo:
        raise HTTPException(status_code=404, detail=ERRO_UTILIZADOR_NAO_ENCONTRADO)

    if _texto((actor or {}).get("id")) == _texto(alvo_id):
        return alvo
    if utilizador_e_global(actor):
        return alvo

    if e_papel_global(alvo.get("role")):
        # Mesma resposta de «não existe»: o Master não é visível a quem não é.
        raise HTTPException(status_code=404, detail=ERRO_UTILIZADOR_NAO_ENCONTRADO)

    ambito = await empresas_do_ambito(actor or {})
    consulta = await build_users_scope_query(ambito)
    dentro = await db.users.find_one(
        {"$and": [{"id": alvo_id}, consulta]} if consulta else {"id": alvo_id},
        {"_id": 0, "id": 1},
    )
    if not dentro:
        logger.warning(
            "[GESTAO-UTILIZADORES] %s tentou gerir %s, fora do seu âmbito.",
            (actor or {}).get("id"), alvo_id,
        )
        raise HTTPException(status_code=404, detail=ERRO_UTILIZADOR_NAO_ENCONTRADO)
    return alvo


def exigir_papeis_concediveis(actor: dict, papeis: Iterable[Any]) -> None:
    """403 se algum dos perfis a conceder é reservado e quem actua não é Master."""
    for papel in papeis or ():
        if not pode_conceder_papel(actor, papel):
            raise HTTPException(status_code=403, detail=ERRO_PAPEL_RESERVADO)


async def exigir_empresas_concediveis(
    actor: dict,
    empresas: Iterable[Any],
) -> None:
    """404 se alguma empresa não pertence às redes de quem actua.

    404 e não 403, pela mesma razão do utilizador: não confirmar que a
    empresa existe. O Master concede em qualquer uma.
    """
    pedidas = [_texto(e) for e in (empresas or ()) if _texto(e)]
    if not pedidas or utilizador_e_global(actor):
        return

    ambito = await empresas_do_ambito(actor or {})
    permitidas = {_texto(e).lower() for e in (*ambito.ids, *ambito.nomes)}
    for empresa in pedidas:
        if empresa.lower() not in permitidas:
            logger.warning(
                "[GESTAO-UTILIZADORES] %s tentou conceder acesso à empresa %r, "
                "fora do seu âmbito.", (actor or {}).get("id"), empresa,
            )
            raise HTTPException(status_code=404, detail=ERRO_EMPRESA_FORA_DO_AMBITO)


async def ids_dos_autores_no_ambito(actor: dict) -> Optional[list[str]]:
    """Os ids dos utilizadores cuja actividade quem actua pode consultar.

    `None` para o Master (sem restrição). Para os restantes: os
    utilizadores das empresas da sua rede **mais o próprio**. Serve os
    registos de auditoria, que levam o autor mas não o carimbo de rede.
    A lista é cortada nos 5000 — uma rede com mais utilizadores do que
    isso tem outros problemas; e cortar errado é fechado (vê menos).
    """
    if utilizador_e_global(actor):
        return None
    consulta = await build_users_scope_query(await empresas_do_ambito(actor or {}))
    colegas = (
        await db.users.find(consulta, {"_id": 0, "id": 1}).to_list(5000)
        if consulta else []
    )
    ids = {str(c["id"]) for c in colegas if c.get("id")}
    if (actor or {}).get("id"):
        ids.add(str((actor or {})["id"]))
    return sorted(ids)


def papeis_globais() -> frozenset[str]:
    return frozenset(PAPEIS_GLOBAIS)


__all__ = [
    "ERRO_EMPRESA_FORA_DO_AMBITO",
    "ERRO_PAPEL_RESERVADO",
    "ERRO_UTILIZADOR_NAO_ENCONTRADO",
    "carregar_utilizador_gerivel",
    "exigir_empresas_concediveis",
    "exigir_papeis_concediveis",
    "ids_dos_autores_no_ambito",
    "normalizar_papel",
    "papeis_globais",
]
