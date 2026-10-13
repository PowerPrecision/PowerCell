"""User list / get-by-id handlers.

Extraído de `routes/users.py`.
"""
from __future__ import annotations

from database import db
from services.staff_assignment import (
    apply_assignment_staff_filter,
    filter_assignment_staff,
)

# Pacote EB — lista global sem paginação curta (alinhado com /admin/users).
USERS_LIST_LIMIT = 10000


async def run_get_users(
    role: str | None,
    user: dict,
    for_assignment: bool = False,
    process_id: str | None = None,
):
    """Listar utilizadores do sistema (filtro opcional por role).

    Pacote DT: `for_assignment=True` exclui admin das dropdowns.
    Pacote FL: inclui indexação nas dropdowns de atribuição.
    Pacote EB: por defeito devolve TODOS (admin, indexação, inativos).

    `process_id` (Out 2026): a dropdown de atribuição diz de que processo
    se trata. Só muda a lista do Master — o único sem fronteira de dados —,
    que passa a ver apenas quem o processo já alcança (dono + convidadas),
    ou seja, exactamente o que o servidor aceitaria ao gravar.
    """
    from services.role_query import build_deep_role_query

    query = {}
    if role:
        query = build_deep_role_query(query, role=role)
    query = apply_assignment_staff_filter(query, for_assignment)

    # FRONTEIRA DE REDE (Out 2026). Esta lista alimenta as dropdowns de
    # atribuição, e não tinha filtro nenhum — só `/admin/users` o tinha.
    # A regra é a da atribuição directa (`assignment_network_guard`): só
    # se escolhe gente da própria rede; passar um processo a outra rede é
    # a Partilha Explícita. A lista sai do SERVIDOR e não de um filtro no
    # browser, para a regra não viver em dois sítios. O âmbito é o mesmo
    # do painel de administração (rede → empresas → utilizadores).
    from services.admin_users_scope import (
        build_users_scope_query,
        empresas_do_ambito,
    )

    # Com um processo manda o que o processo alcança (abaixo); sem ele, a equipa que o
    # Master vê é a da EMPRESA que tem seleccionada (`X-Company-Id`).
    ambito = await empresas_do_ambito(user or {}, vista=not process_id)
    scope_query = await build_users_scope_query(ambito)
    if scope_query:
        query = {"$and": [query, scope_query]} if query else scope_query

    users = await db.users.find(query, {"_id": 0, "password": 0}).to_list(
        USERS_LIST_LIMIT
    )
    if process_id:
        from services.assignment_network_guard import (
            utilizadores_atribuiveis_ao_processo,
        )

        users = await utilizadores_atribuiveis_ao_processo(
            user or {}, users, process_id
        )
    if for_assignment:
        users = filter_assignment_staff(users)

    # A empresa de cada pessoa, para quem escolhe saber a quem atribui. Calculada
    # ao servir, restrita às empresas do ÂMBITO de quem pede.
    from services.user_company_labels import anexar_empresas

    return await anexar_empresas(users, ambito=ambito)


async def run_get_staff_users(user: dict, process_id: str | None = None):
    """Staff elegível para atribuição (consultor/intermediario/diretor/ceo)."""
    return await run_get_users(
        role=None, user=user, for_assignment=True, process_id=process_id,
    )


async def run_get_user(user_id: str, user: dict):
    """Obter utilizador por ID — só se estiver no âmbito de quem pede.

    `require_staff` autoriza o VERBO, não o OBJECTO: sem esta guarda
    bastava conhecer um id para ler o perfil (email, telefone, empresas)
    de alguém de uma rede concorrente. A regra é a da gestão de
    utilizadores e a da lista (`carregar_utilizador_gerivel`): o próprio,
    o Master (tudo) ou alguém das empresas da minha rede; um perfil
    global nunca é visível a um local. **404 e nunca 403** — distinguir
    «não existe» de «não é teu» faria do endpoint um directório de ids.
    """
    from services.user_management_scope import carregar_utilizador_gerivel

    return await carregar_utilizador_gerivel(user_id, user or {})
