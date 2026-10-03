"""Capacidades pelo papel EFECTIVO — o ponto único dos botões (Lote 6, ponto 3).

O QUE ESTAVA MAL
================
O sistema tem um registo canónico de capacidades por cargo
(`models/permissions.ROLE_CAPABILITY_DEFAULTS`), e lá está escrito que o perfil
`indexacao` **não** cria processos (`PROCESS_CREATE: False`). O ecrã não o
consultava: o botão "Novo Processo" aparecia a todos, e quem não podia descobria
pelo erro. Um botão que não funciona é pior do que um botão que não existe — e
pior ainda do que um desactivado, porque não diz porquê.

E a resolução que existia tinha um defeito mais fundo: `resolve_capability` lê
`user["role"]` — o cargo do **JWT**. Quem tem perfil base de consultor e entra
COMO diretor era avaliado como consultor, enquanto a porta do servidor
(`require_roles`) usa o cargo EFECTIVO. É a forma exacta do
`history._is_stealth_user` e do botão de eliminar cliente, terceira ocorrência:
**duas noções de papel no mesmo caminho dão as duas respostas erradas** — menos
botões do que devia num sentido, mais no outro.

COMO SE RESOLVE
===============
`capacidades_do_papel(user, papel)` resolve as defaults do papel PEDIDO e
aplica por cima os overrides pessoais do utilizador. O `/auth/me` devolve
`capabilities_por_papel` — um mapa por cada cargo que o utilizador tem — e o
frontend escolhe pelo perfil activo, sem segunda chamada e sem duplicar a
tabela de defaults (uma cópia no frontend divergiria em silêncio, que é o
defeito dos campos canónicos de atribuição com outro nome).

`exigir_capacidade` é a mesma regra do lado da porta, para a rota não ficar
mais larga do que o botão.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Iterable, Optional

from fastapi import Depends, HTTPException, Request

from models.permissions import CAPABILITIES, SUPER_ADMIN_ROLES, get_role_defaults

logger = logging.getLogger(__name__)


def _papel(valor: Any) -> str:
    return str(getattr(valor, "value", valor) or "").strip().lower()


def capacidades_do_papel(user: Optional[dict], papel: Any) -> dict[str, bool]:
    """As capacidades de um utilizador **enquanto** desempenha `papel`.

    Ordem: defaults do papel → overrides pessoais. Os overrides vivem em
    `permissions.capabilities` e são do utilizador, não do cargo: aplicá-los é
    o que faz um consultor com uma excepção manter a excepção ao trocar de
    chapéu.
    """
    nome = _papel(papel)
    if not nome:
        return {}
    capacidades = get_role_defaults(nome)
    if not user:
        return capacidades
    overrides = ((user.get("permissions") or {}).get("capabilities") or {})
    for chave, valor in overrides.items():
        # Só chaves conhecidas: um override para uma capacidade que já não
        # existe não pode ressuscitar um botão.
        if chave in CAPABILITIES:
            capacidades[chave] = bool(valor)
    return capacidades


def tem_capacidade(
    user: Optional[dict], capability: str, *, papel: Any = None
) -> bool:
    """O utilizador pode fazer isto, com o papel indicado?

    Sem `papel` cai no cargo do JWT — e isso é só compatibilidade: quem tem o
    `Request` à mão deve resolver o papel efectivo e passá-lo.
    """
    if not user or not capability:
        return False
    nome = _papel(papel) or _papel(user.get("role"))
    if nome in {p for p in SUPER_ADMIN_ROLES}:
        return True
    return bool(capacidades_do_papel(user, nome).get(capability, False))


def capacidades_por_papel(user: Optional[dict], papeis: Iterable[Any]) -> dict:
    """`{papel: {CAPACIDADE: bool}}` para os cargos que o utilizador tem.

    É isto que vai no `/auth/me`. Um mapa por papel em vez de um mapa plano
    porque o perfil activo muda sem recarregar a sessão — enviar só as do
    cargo base era garantir que o ecrã fica desactualizado no momento em que
    alguém troca de chapéu.
    """
    resultado: dict[str, dict[str, bool]] = {}
    for p in papeis or []:
        nome = _papel(p)
        if nome and nome not in resultado:
            resultado[nome] = capacidades_do_papel(user, nome)
    return resultado


def exigir_capacidade(capability: str) -> Callable:
    """Dependência FastAPI: 403 se o papel EFECTIVO não tiver a capacidade.

    Mesma forma do `require_roles` (e por isso o mesmo papel: UCR +
    `X-Active-Role`), para a porta e o botão não poderem discordar.
    """
    from services.auth import get_current_user

    async def verificador_de_capacidade(
        request: Request,
        user: dict = Depends(get_current_user),
    ) -> dict:
        from services.auth import authorization_role, get_effective_role_async

        # `authorization_role` traduz o sentinel `__all_roles__` (o modo
        # "todos os perfis" da filtragem de dados) para o cargo do JWT. Sem
        # ele, o sentinel chegava aqui como nome de papel, não casava com
        # nenhuma default e recusava TUDO a quem está em modo agregado.
        papel = authorization_role(
            await get_effective_role_async(request, user), user
        )
        if not tem_capacidade(user, capability, papel=papel):
            logger.info(
                "[CAPACIDADE] %s recusado a %s (papel efectivo=%s)",
                capability, user.get("id"), papel,
            )
            raise HTTPException(
                status_code=403,
                detail="O perfil activo não tem permissão para esta acção.",
            )
        return user

    return verificador_de_capacidade
