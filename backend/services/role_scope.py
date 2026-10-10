"""
====================================================================
HIERARQUIA DE PERFIS: UM GLOBAL, O RESTO LOCAL (Out 2026, adenda ao Bloco 5)
====================================================================
Ponto ÚNICO da pergunta «este perfil atravessa empresas?».

AS REGRAS DO DONO DO PRODUTO
  * MASTER — o único perfil GLOBAL: todas as empresas, a configuração
    global do sistema (`default`) e a infraestrutura (backups, índices,
    encriptação, S3, jobs, logs).
  * ADMIN — perfil LOCAL: tudo da sua própria empresa (rede), nada fora.
  * CEO — perfil LOCAL, igual ao Admin no âmbito de dados.
  * Diretor, Administrativo, Consultor, Intermediário, Parceiro e
    Index (`indexacao`) — locais, e restritos pelas suas atribuições.

O QUE MUDOU FACE AO ANTERIOR
  Até aqui o ADMIN era o perfil global: passava todas as guardas de
  papel e, em ~15 serviços, atravessava a fronteira de rede (o CEO
  também). Isso era um «Admin da empresa A vê a empresa B» — o que o
  Lote 5 já tinha declarado inaceitável para o Painel de Administração
  mas que ficou vivo nos calendários, visitas, imóveis, finanças,
  emails, partilhas e origem financeira.

  Hoje a fronteira de rede tem UMA excepção, e é este módulo que a
  declara: `PAPEIS_GLOBAIS`. Nenhum serviço volta a escrever
  `{ADMIN, CEO}` à mão para dizer «sem fronteira» — usa
  `e_papel_global`. Há um inventário por AST (`test_hierarquia_de_perfis`)
  que falha por OMISSÃO se uma lista de papéis sem fronteira reaparecer.

DUAS COISAS DIFERENTES, QUE NÃO SE MISTURAM
  1. **Guarda de papel** (`require_roles`): «este perfil pode usar esta
     funcionalidade?». O Master passa SEMPRE; o Admin passa tudo menos o
     que for declarado só-Master.
  2. **Âmbito de dados** (`tenant_network`): «que dados vê?». O Master
     vê tudo; todos os outros só a(s) sua(s) rede(s).
  Um Admin pode ter a guarda de uma funcionalidade e continuar a ver só
  os dados da sua empresa — é essa a combinação pretendida.
====================================================================
"""
from __future__ import annotations

from typing import Any, Optional

from models.auth import UserRole, normalizar_papel

#: Os perfis que atravessam empresas. Uma lista de UM elemento, de propósito.
PAPEIS_GLOBAIS: frozenset[str] = frozenset({UserRole.MASTER})

#: Perfis que NUNCA podem ser concedidos por quem não é Master. Conceder
#: `master` a si próprio (ou a um cúmplice) pela API de utilizadores seria
#: a escalada de privilégios mais curta do sistema.
PAPEIS_SO_MASTER_CONCEDE: frozenset[str] = frozenset({UserRole.MASTER})


def e_papel_global(papel: Any) -> bool:
    """Este perfil atravessa empresas? (só o Master)"""
    return normalizar_papel(papel) in PAPEIS_GLOBAIS


def papel_concreto_do_utilizador(user: Optional[dict]) -> str:
    """O perfil CONCRETO em que o utilizador está a trabalhar agora.

    `effective_role` é o perfil activo resolvido contra os UCRs; o
    sentinel «Todos os perfis» (`__all_roles__`) é um conceito de
    listagem e não decide permissões — recua para o perfil base, que é o
    recuo conservador (mesma regra de `resolve_concrete_role`).
    """
    user = user or {}
    efectivo = normalizar_papel(user.get("effective_role"))
    if efectivo and efectivo != "__all_roles__":
        return efectivo
    return normalizar_papel(user.get("role"))


def utilizador_e_global(user: Optional[dict]) -> bool:
    """O utilizador está a trabalhar como Master?

    Decide pelo perfil ACTIVO, não pelo da conta: um Master que troca
    para o seu perfil de Consultor numa empresa passa a ver o que um
    Consultor dessa empresa vê. Alargar o âmbito pelo perfil BASE era a
    forma do `history._is_stealth_user` ao contrário.
    """
    return e_papel_global(papel_concreto_do_utilizador(user))


def pode_conceder_papel(quem_concede: Optional[dict], papel: Any) -> bool:
    """Quem concede um perfil pode concedê-lo?

    Só o Master concede `master`. Isto é verificado em TODOS os pontos
    que escrevem um perfil (criar/editar utilizador, UCR) — um só que
    falte é a escalada de privilégios.
    """
    if normalizar_papel(papel) in PAPEIS_SO_MASTER_CONCEDE:
        return utilizador_e_global(quem_concede)
    return True


__all__ = [
    "PAPEIS_GLOBAIS",
    "PAPEIS_SO_MASTER_CONCEDE",
    "e_papel_global",
    "papel_concreto_do_utilizador",
    "pode_conceder_papel",
    "utilizador_e_global",
]
