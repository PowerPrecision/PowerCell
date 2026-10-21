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
        empresas_da_empresa_activa,
        sem_parceiros,
    )

    # A equipa que se vê é SEMPRE a da EMPRESA escolhida (`X-Company-Id`), com ou sem processo
    # (Lote 6, «janela, não porta», e P5): a rede é a fronteira de SEGURANÇA, a empresa é a pergunta
    # «quem trabalha aqui?». Estreitar só pela rede deixava ver, na dropdown de atribuição, as pessoas
    # de outra empresa da mesma rede (e, onde a migração carimbou todas as empresas com a rede de
    # omissão, até a Domus). O cabeçalho NUNCA alarga: `empresas_da_empresa_activa` só o aceita se
    # `resolve_tenant_scope` o aceitou; sem ele (ou forjado) vale o âmbito de rede de sempre.
    # Com um processo, o que ele alcança ainda estreita a lista do Master (abaixo).
    ambito = await empresas_da_empresa_activa(user or {})
    scope_query = await build_users_scope_query(ambito)
    if scope_query:
        query = {"$and": [query, scope_query]} if query else scope_query
    if not for_assignment:
        query = sem_parceiros(query, role)

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
        users = await _juntar_a_equipa_do_processo(user or {}, users, process_id)
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


async def _juntar_a_equipa_do_processo(ator: dict, users: list[dict], process_id: str) -> list[dict]:
    """Quem JÁ está atribuído ao processo continua nas opções, mesmo de outra empresa.

    A dropdown segue a empresa activa; uma colega de outra empresa da rede que já trata este processo
    não está nela, e a interface devolve a lista inteira ao gravar — sem esta junção, gravar retirava-a
    em silêncio. O processo só é lido se estiver no ÂMBITO de quem pergunta (a condição vai na própria
    consulta: um processo alheio nunca chega a ser lido) e só com os campos da equipa; processo
    invisível ou inexistente = nada a juntar, sem distinguir um do outro.
    """
    from services.task_assignment_hygiene import (
        CAMPOS_DE_ATRIBUICAO_DO_PROCESSO,
        ids_atribuidos_do_processo,
    )
    from services.tenant_network import build_process_scope_condition, resolve_tenant_scope

    condicao = build_process_scope_condition(await resolve_tenant_scope(ator))
    projeccao = {"_id": 0, **{campo: 1 for campo in CAMPOS_DE_ATRIBUICAO_DO_PROCESSO}}
    processo = await db.processes.find_one(
        {"$and": [{"id": str(process_id)}, {"is_deleted": {"$ne": True}}, condicao]}, projeccao,
    )
    if not processo:
        return users
    ja_la = {u.get("id") for u in users}
    em_falta = [i for i in sorted(ids_atribuidos_do_processo(processo)) if i not in ja_la]
    if not em_falta:
        return users
    extra = await db.users.find({"id": {"$in": em_falta}}, {"_id": 0, "password": 0}).to_list(len(em_falta))
    return [*users, *extra]
