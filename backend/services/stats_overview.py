"""Dashboard KPI overview stats.

Extraído de `routes/stats.py`.
"""
from __future__ import annotations

import asyncio
import logging

from database import db
from models.auth import UserRole
from services.process_status import DELETED_STATUS_VALUES, STATUS_VALUE_ALIASES
from services.redis_cache import (
    cache_get, cache_set,
    build_user_kpi_key,
)
from services.stats_scope import com_ambito, resolver_ambito

logger = logging.getLogger(__name__)

async def _contar_prazos_do_ambito(user_id: str, ambito) -> int:
    """Prazos abertos dos processos da rede, mais os pessoais do próprio.

    Duas consultas pequenas e uma contagem exacta: os `process_id`
    distintos dos prazos abertos, quais deles são da rede, e a contagem
    final sobre esse conjunto. Nunca uma estimativa — é um cartão de KPI,
    e um número aproximado num KPI é pior do que nenhum.
    """
    from services.stats_scope import processos_no_ambito

    ids = [i for i in await db.deadlines.distinct(
        "process_id", {"completed": False},
    ) if i]
    permitidos = sorted(await processos_no_ambito(ids, ambito))

    ramos: list[dict] = [
        {"created_by": user_id, "process_id": None, "completed": False},
    ]
    if permitidos:
        ramos.append({"process_id": {"$in": permitidos}, "completed": False})

    return await db.deadlines.count_documents({"$or": ramos})


async def run_get_stats(user: dict):
    """Get statistics based on user role. Staff see only their assigned processes.
    
    OTIMIZAÇÃO: Todas as queries count_documents são executadas em paralelo
    com asyncio.gather(), reduzindo o tempo total de ~12 chamadas sequenciais
    para 2-3 chamadas paralelas.
    """
    # O13 - Redis cache: chave hierárquica por user
    # TTL longo (24h) porque invalidação cirúrgica garante fresh data
    # A chave leva o SUFIXO DO ÂMBITO (Dashboard, ponto 1). Por utilizador
    # já era segura — o âmbito é função do utilizador —, mas o TTL é de 24h
    # e tirar alguém de uma empresa só fazia efeito no dia seguinte. Com o
    # sufixo, uma mudança de âmbito estreia uma chave nova no primeiro
    # pedido, e a antiga expira sozinha. O padrão de invalidação
    # (`stats:user:{id}:*`) continua a apanhá-la.
    ambito = await resolver_ambito(user)
    cache_key = f"{build_user_kpi_key(user['id'])}:{ambito.sufixo}"
    cached = await cache_get(cache_key)
    if cached:
        return cached
    
    stats = {}
    role = user["role"]
    user_id = user["id"]

    # ====================================================================
    # ISOLAMENTO DE REDE (Dashboard, ponto 1)
    # ====================================================================
    # Antes disto a query base era `{}` mais um filtro por PAPEL, e para
    # admin/ceo/administrativo/diretor não havia filtro nenhum: uma
    # Diretora da Domus lia os totais, os concluídos e as desistências da
    # Power no seu próprio Dashboard. O filtro por papel nunca foi uma
    # fronteira de tenant — restringe por ATRIBUIÇÃO, e quem vê tudo não
    # tem atribuição que o restrinja.
    #
    # O `ambito` já foi resolvido acima, para a chave de cache.

    # Build query based on role
    process_query = {}

    # ====================================================================
    # FILTRO DE INTEGRIDADE: is_deleted
    # Processos eliminados NUNCA entram nas estatísticas
    # ====================================================================
    process_query["is_deleted"] = {"$ne": True}

    if role == UserRole.CLIENTE:
        process_query["client_id"] = user_id
    elif role == UserRole.CONSULTOR:
        process_query["assigned_consultor_id"] = user_id
    elif role == UserRole.INDEXACAO:
        # INDEXACAO vê apenas os processos atribuídos a ele
        process_query["assigned_indexacao_id"] = user_id
    elif role == UserRole.INTERMEDIARIO:
        process_query["assigned_mediador_id"] = user_id
    # Admin, CEO, Administrativo e Diretor vêem tudo O QUE É DA SUA REDE —
    # é o `com_ambito` abaixo que passou a dizer o que "tudo" significa.

    process_query = com_ambito(process_query, ambito)

    # Process status breakdown
    # NOTA: Estatísticas DEVEM incluir concluídos e desistências para métricas precisas
    # Fix: Normalize process status filters — inclui as variações legadas
    # singular/plural (ver services/process_status.py) para não sub-contar
    # processos concluídos/desistidos gravados no singular.
    concluded_statuses = STATUS_VALUE_ALIASES["concluidos"]
    dropped_statuses = STATUS_VALUE_ALIASES["desistencias"]  # NOTA: "eliminados" não conta como desistência para estatísticas

    # Queries para contagens separadas (todas excluem is_deleted via process_query base)
    concluded_query = {**process_query, "status": {"$in": concluded_statuses}}
    dropped_query = {**process_query, "status": {"$in": dropped_statuses}}
    active_query = {**process_query, "status": {"$nin": concluded_statuses + dropped_statuses + DELETED_STATUS_VALUES}}
    no_indexacao_query = {**active_query, "assigned_indexacao_id": None}
    
    # ── BUSCA PARALELA: 4 contagens de processos + 1 contagem de tarefas ──
    (
        total_processes,
        concluded_processes,
        dropped_processes,
        no_indexacao_processes,
        pending_tasks_count,
    ) = await asyncio.gather(
        db.processes.count_documents(active_query),
        db.processes.count_documents(concluded_query),
        db.processes.count_documents(dropped_query),
        db.processes.count_documents(no_indexacao_query),
        db.tasks.count_documents({"completed": False, "assigned_to": user_id}),
    )
    
    stats["total_processes"] = total_processes
    stats["active_processes"] = total_processes
    stats["concluded_processes"] = concluded_processes
    stats["dropped_processes"] = dropped_processes
    stats["no_indexacao_processes"] = no_indexacao_processes
    stats["pending_tasks"] = pending_tasks_count
    
    # ── DEADLINES: depende do role ──
    if role in [UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO, UserRole.DIRETOR]:
        # ISOLAMENTO (Dashboard, ponto 1) — era `{"completed": False}`, ou
        # seja os prazos abertos de TODAS as redes.
        #
        # O âmbito vem pelo sentido barato: `distinct` sobre os prazos
        # abertos dá as dezenas de processos com prazo, e só esses se
        # verificam contra a rede. O contrário — trazer os processos da
        # rede para um `$in` — seria um filtro com doze mil
        # identificadores em cada pedido de dashboard.
        #
        # MUDANÇA DE SIGNIFICADO, deliberada: os prazos PESSOAIS (sem
        # processo) passam a contar só os do próprio, a mesma regra que o
        # ramo dos consultores já aplicava. Antes, o cartão da Direção
        # somava os lembretes pessoais de todos os utilizadores de todas
        # as redes — um número que não era de ninguém.
        pending_deadlines_coro = _contar_prazos_do_ambito(user_id, ambito)
    elif role == UserRole.CLIENTE:
        # Clientes: buscar IDs dos processos primeiro
        my_process_docs = await db.processes.find(
            com_ambito({"client_id": user_id}, ambito), {"id": 1, "_id": 0}
        ).to_list(1000)
        my_process_ids = [p["id"] for p in my_process_docs]
        if my_process_ids:
            pending_deadlines_coro = db.deadlines.count_documents({
                "process_id": {"$in": my_process_ids}, "completed": False
            })
        else:
            pending_deadlines_coro = asyncio.sleep(0, result=0)
    else:
        # Consultores/Intermediários: buscar IDs dos processos atribuídos
        my_process_docs = await db.processes.find(
            com_ambito({"$or": [
                {"assigned_consultor_id": user_id},
                {"consultor_id": user_id},
                {"assigned_mediador_id": user_id},
                {"intermediario_id": user_id}
            ]}, ambito),
            {"id": 1, "_id": 0}
        ).to_list(1000)
        my_process_ids = [p["id"] for p in my_process_docs]
        if my_process_ids:
            pending_deadlines_coro = db.deadlines.count_documents({
                "$or": [
                    {"process_id": {"$in": my_process_ids}, "completed": False},
                    {"created_by": user_id, "process_id": None, "completed": False}
                ]
            })
        else:
            pending_deadlines_coro = db.deadlines.count_documents({
                "created_by": user_id, "process_id": None, "completed": False
            })
    
    # ── USER STATS (Admin/CEO): executar em paralelo com deadlines ──
    if role in [UserRole.ADMIN, UserRole.CEO]:
        from services.role_query import deep_role_filter, deep_role_in_filter
        from services.admin_users_scope import (
            build_users_scope_query,
            empresas_do_ambito,
        )

        # ISOLAMENTO (Dashboard, ponto 1) — as seis contagens eram sobre
        # `db.users` INTEIRA. "Ser Admin significa ser Admin da sua REDE"
        # (decisão do dono, Lote 5): o painel de administração já contava
        # assim e o cartão do Dashboard contradizia-o.
        #
        # Reutiliza o `admin_users_scope`, que resolve rede → empresas →
        # utilizadores. `users` não tem `network_id` e nunca teve; aplicar
        # a condição de rede a esta colecção devolveria sempre zero.
        # FALHA ALTO de propósito: o `empresas_do_ambito` não engole a
        # excepção de leitura (política dele, Lote 5). Um Dashboard com um
        # erro visível é melhor do que um Dashboard com os números errados.
        escopo_utilizadores = await build_users_scope_query(
            await empresas_do_ambito(user)
        )

        def _users(extra: dict) -> dict:
            return {"$and": [escopo_utilizadores, extra]} if extra else escopo_utilizadores

        (
            pending_deadlines_count,
            total_users,
            active_users,
            inactive_users,
            clients_count,
            consultors_count,
            intermediarios_count,
        ) = await asyncio.gather(
            pending_deadlines_coro,
            db.users.count_documents(_users({})),
            db.users.count_documents(_users({"is_active": {"$ne": False}})),
            db.users.count_documents(_users({"is_active": False})),
            db.users.count_documents(_users(deep_role_filter(UserRole.CLIENTE))),
            db.users.count_documents(_users(deep_role_in_filter([UserRole.CONSULTOR, UserRole.DIRETOR]))),
            db.users.count_documents(_users(deep_role_in_filter([UserRole.INTERMEDIARIO, UserRole.DIRETOR]))),
        )
        
        stats["total_users"] = total_users
        stats["active_users"] = active_users
        stats["inactive_users"] = inactive_users
        stats["clients"] = clients_count
        stats["consultors"] = consultors_count
        stats["intermediarios"] = intermediarios_count
    else:
        pending_deadlines_count = await pending_deadlines_coro
    
    stats["pending_deadlines"] = pending_deadlines_count
    stats["total_pending"] = pending_deadlines_count + pending_tasks_count
    
    # O13 - Cache result for 24 hours (invalidação cirúrgica substitui TTL curto)
    await cache_set(cache_key, stats, ttl=86400)
    return stats

