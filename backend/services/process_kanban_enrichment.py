"""
Helpers de enriquecimento/ordenação do Kanban.

Extraído de `routes/processes.py` (`get_kanban_board`) para isolar
ordenação por prioridade, agrupamento por status e cards enriquecidos.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

from database import db
from services.process_status import STATUS_VALUE_ALIASES
from services.workflow_phases import nomes_terminais

logger = logging.getLogger(__name__)

PRIORITY_WEIGHT = {"alta": 3, "media": 2, "baixa": 1}
# Fix: Normalize process status filters — inclui as variações legadas
# singular/plural (ver services/process_status.py).
CONCLUDED_STATUSES = STATUS_VALUE_ALIASES["concluidos"]
DROPPED_STATUSES = STATUS_VALUE_ALIASES["desistencias"]


def group_processes_by_status(
    processes: list[dict],
    fases: Optional[list[dict]] = None,
) -> dict[str, list[dict]]:
    """Agrupa processos pela fase do motor (lookup O(1) por coluna).

    Com ``fases``, o nome gravado passa pelo RESOLVEDOR
    (`workflow_phases.resolver_nome`): gralhas e nomes antigos caem na
    coluna certa e o que não resolve vai para `FASE_DESCONHECIDA`, em vez
    de desaparecer.

    Sem ``fases`` mantém-se o agrupamento por igualdade exacta. Não é um
    atalho de compatibilidade: é o comportamento correcto quando não há
    motor para consultar — inventar colunas a partir de nada seria pior.

    O processo traduzido entra numa CÓPIA rasa com `status_resolvido_de`
    preenchido. Cópia, porque o `status` gravado não muda: a resolução é
    de leitura. O campo existe para a UI poder dizer "este cartão está
    aqui por tradução" e para um diagnóstico não ter de refazer a conta.
    """
    if not fases:
        processes_by_status: dict[str, list[dict]] = {}
        for p in processes:
            s = p.get("status", "")
            processes_by_status.setdefault(s, []).append(p)
        return processes_by_status

    from services.workflow_phases import FASE_DESCONHECIDA, resolver_muitos

    resolucoes = resolver_muitos(
        [p.get("status") for p in processes if isinstance(p, dict)], fases,
    )
    agrupados: dict[str, list[dict]] = {}
    for p in processes:
        if not isinstance(p, dict):
            continue
        gravado = p.get("status") or ""
        resolucao = resolucoes.get(gravado)
        if resolucao is None or not resolucao.resolvida:
            agrupados.setdefault(FASE_DESCONHECIDA, []).append(p)
            continue
        if resolucao.traduzida:
            p = {**p, "status_resolvido_de": gravado}
        agrupados.setdefault(resolucao.fase, []).append(p)
    return agrupados


def sort_kanban_column_processes(processes: list[dict]) -> list[dict]:
    """
    Ordena in-place: 1º prioridade (Alta>Média>Baixa), 2º updated_at DESC.

    Two-step stable sort: first by updated_at DESC, then by priority DESC.
    """
    processes.sort(key=lambda p: p.get("updated_at") or "", reverse=True)
    processes.sort(
        key=lambda p: -PRIORITY_WEIGHT.get(p.get("prioridade") or p.get("priority"), 0)
    )
    return processes


def sort_all_kanban_columns(processes_by_status: dict[str, list[dict]]) -> None:
    """Aplica sort_kanban_column_processes a cada coluna."""
    for status_key in processes_by_status:
        sort_kanban_column_processes(processes_by_status[status_key])


def enrich_kanban_process_card(
    process: dict,
    user_map: dict[str, dict],
    current_user_id: str,
) -> dict:
    """
    Card Kanban com nomes de assignees + flags is_assigned_to_me.

    `user_map` é id → {id, name, role}.
    """
    p = process
    consultor_ids = p.get("assigned_consultor_ids") or []
    if not isinstance(consultor_ids, list):
        consultor_ids = []
    primary_consultor = p.get("assigned_consultor_id")
    if primary_consultor and primary_consultor not in consultor_ids:
        consultor_ids = list(consultor_ids) + [primary_consultor]
    consultor_names = [
        user_map.get(cid, {}).get("name", "")
        for cid in consultor_ids
        if cid and isinstance(cid, str) and user_map.get(cid)
    ]

    mediador_ids = p.get("assigned_mediador_ids") or []
    if not isinstance(mediador_ids, list):
        mediador_ids = []
    primary_mediador = p.get("assigned_mediador_id")
    if primary_mediador and primary_mediador not in mediador_ids:
        mediador_ids = list(mediador_ids) + [primary_mediador]
    mediador_names = [
        user_map.get(mid, {}).get("name", "")
        for mid in mediador_ids
        if mid and isinstance(mid, str) and user_map.get(mid)
    ]

    idx_id = p.get("assigned_indexacao_id")
    indexacao_name = p.get("indexacao_name") or ""
    if not indexacao_name and idx_id and isinstance(idx_id, str):
        indexacao_name = user_map.get(idx_id, {}).get("name", "")

    par_id = p.get("assigned_parceiro_id")
    parceiro_name = p.get("parceiro_name") or ""
    if not parceiro_name and par_id and isinstance(par_id, str):
        parceiro_name = user_map.get(par_id, {}).get("name", "")

    assigned_consultor_ids_list = p.get("assigned_consultor_ids") or []
    if not isinstance(assigned_consultor_ids_list, list):
        assigned_consultor_ids_list = []
    assigned_mediador_ids_list = p.get("assigned_mediador_ids") or []
    if not isinstance(assigned_mediador_ids_list, list):
        assigned_mediador_ids_list = []

    is_my_consultor = (
        p.get("assigned_consultor_id") == current_user_id
        or current_user_id in assigned_consultor_ids_list
    )
    is_my_mediador = (
        p.get("assigned_mediador_id") == current_user_id
        or current_user_id in assigned_mediador_ids_list
    )

    return {
        **p,
        "consultor_name": ", ".join(consultor_names) if consultor_names else (p.get("consultor_name") or ""),
        "mediador_name": ", ".join(mediador_names) if mediador_names else (p.get("mediador_name") or ""),
        "indexacao_name": indexacao_name,
        "parceiro_name": parceiro_name,
        "is_assigned_to_me": is_my_consultor or is_my_mediador,
        "my_role_in_process": (
            "consultor" if is_my_consultor
            else ("intermediario" if is_my_mediador else None)
        ),
    }


def build_kanban_columns(
    statuses: list[dict],
    processes_by_status: dict[str, list[dict]],
    user_map: dict[str, dict],
    current_user_id: str,
    *,
    incluir_desconhecidas: bool = False,
) -> list[dict]:
    """Monta a lista de colunas do Kanban com cards enriquecidos.

    ``incluir_desconhecidas`` acrescenta no fim a coluna que recolhe os
    processos cujo `status` o motor não reconhece. Só quem reconcilia
    (ADMIN/CEO) a recebe — mas esconder a coluna NÃO é esconder o
    problema: o número vai na resposta para toda a gente
    (`total_desconhecidos`), e a coluna é onde ele se resolve.
    """
    kanban: list[dict] = []
    for status in statuses:
        if not isinstance(status, dict):
            continue
        status_name = status.get("name") or ""
        status_processes = processes_by_status.get(status_name, [])
        enriched_processes = []
        for p in status_processes:
            if not isinstance(p, dict):
                continue
            enriched_processes.append(
                enrich_kanban_process_card(p, user_map, current_user_id)
            )
        kanban.append({
            "id": status.get("id") or status_name,
            "name": status_name,
            "label": status.get("label") or status_name.replace("_", " ").title(),
            "color": status.get("color") or "#6B7280",
            "order": status.get("order", 0),
            "processes": enriched_processes,
            "count": len(enriched_processes),
        })

    if incluir_desconhecidas:
        from services.workflow_phases import (
            ETIQUETA_DESCONHECIDA, FASE_DESCONHECIDA,
        )

        orfaos = processes_by_status.get(FASE_DESCONHECIDA) or []
        if orfaos:
            kanban.append({
                "id": FASE_DESCONHECIDA,
                "name": FASE_DESCONHECIDA,
                "label": ETIQUETA_DESCONHECIDA,
                "color": "#6B7280",
                # Depois de todas as fases: é uma caixa de entrada de
                # reconciliação, não um passo do workflow.
                "order": 10_000,
                "reconciliacao": True,
                "processes": [
                    enrich_kanban_process_card(p, user_map, current_user_id)
                    for p in orfaos if isinstance(p, dict)
                ],
                "count": len([p for p in orfaos if isinstance(p, dict)]),
            })
    return kanban


def client_contact_summary(client_doc: dict) -> dict[str, str]:
    """Extrai nome/email/telefone/nif de um doc cliente (já desencriptado)."""
    contacto = client_doc.get("contacto") or {}
    dados_pessoais = client_doc.get("dados_pessoais") or {}
    return {
        "nome": client_doc.get("nome", "") or "",
        "email": contacto.get("email", "") or "",
        "telefone": contacto.get("telefone", "") or "",
        "nif": dados_pessoais.get("nif", client_doc.get("nif", "")) or "",
    }


def apply_client_contacts_to_processes(
    processes: list[dict],
    client_map: dict[str, dict[str, str]],
) -> None:
    """Preenche client_* em falta via setdefault (não sobrescreve)."""
    for p in processes:
        cid = p.get("client_id")
        if not cid or cid not in client_map:
            continue
        cinfo = client_map[cid]
        p.setdefault("client_name", cinfo["nome"])
        p.setdefault("client_email", cinfo["email"])
        p.setdefault("client_phone", cinfo["telefone"])
        p.setdefault("client_nif", cinfo["nif"])


async def fill_missing_process_client_contacts(processes: list[dict]) -> None:
    """
    Batch lookup em clients para processos sem client_name (paradigma relacional).
    """
    client_ids_to_fetch = {
        p["client_id"]
        for p in processes
        if p.get("client_id") and not p.get("client_name")
    }
    if not client_ids_to_fetch:
        return

    # PACOTE DG — excluir clientes eliminados (soft-delete) do enriquecimento
    # de contactos do kanban (defesa em profundidade — o processo já deve
    # estar filtrado, mas garantimos que não arrastamos dados de clientes
    # eliminados).
    client_docs = await db.clients.find(
        {"$and": [
            {"id": {"$in": list(client_ids_to_fetch)}},
            {"is_deleted": {"$ne": True}},
        ]},
        {"_id": 0, "id": 1, "nome": 1, "contacto": 1, "dados_pessoais": 1, "nif": 1},
    ).to_list(len(client_ids_to_fetch))

    try:
        from services.encryption import decrypt_client_data
        client_docs = [decrypt_client_data(c) for c in client_docs]
    except Exception:
        pass

    client_map = {
        c["id"]: client_contact_summary(c)
        for c in client_docs
        if c.get("id")
    }
    apply_client_contacts_to_processes(processes, client_map)


def build_active_inactive_count_queries(
    query: Optional[dict],
    terminais: Optional[list[str]] = None,
) -> tuple[dict, dict]:
    """Queries de contagem activa/inactiva alinhadas com o filtro do board.

    ``terminais`` vem do motor (`workflow_phases.nomes_terminais`). Sem
    ele mantém-se a lista legada — que era a origem da contradição: o
    contador conhecia aliases que o quadro ignorava, e o número por cima
    do quadro contava cartões que não estavam lá.
    """
    nomes = list(terminais) if terminais else CONCLUDED_STATUSES + DROPPED_STATUSES
    base = dict(query) if query else {}
    active = dict(base)
    active["status"] = {"$nin": nomes}
    inactive = dict(base)
    inactive["status"] = {"$in": nomes}
    return active, inactive


async def count_kanban_active_inactive(
    query: Optional[dict],
    *,
    terminais: Optional[list[str]] = None,
) -> tuple[int, int]:
    """Conta processos activos e inactivos em paralelo."""
    active_q, inactive_q = build_active_inactive_count_queries(query, terminais)
    active_count, inactive_count = await asyncio.gather(
        db.processes.count_documents(active_q),
        db.processes.count_documents(inactive_q),
    )
    return active_count, inactive_count


def safe_build_kanban_columns(
    statuses: list[dict],
    processes_by_status: dict[str, list[dict]],
    user_map: dict[str, dict],
    current_user_id: str,
    *,
    incluir_desconhecidas: bool = False,
) -> list[dict]:
    """
    PACOTE AY failsafe: nunca propaga exceção — devolve [] se build falhar.
    """
    try:
        return build_kanban_columns(
            statuses, processes_by_status, user_map, current_user_id,
            incluir_desconhecidas=incluir_desconhecidas,
        )
    except Exception as e:
        logger.exception(
            f"[KANBAN] Exceção capturada (failsafe): {type(e).__name__}: {e}. "
            f"Devolvendo 0 colunas."
        )
        return []


def build_kanban_board_payload(
    *,
    columns: list[dict],
    active_count: int,
    inactive_count: int,
    role: Any,
    user_id: str,
    view_mode: Optional[str],
    completed_days: Optional[int],
    total_desconhecidos: int = 0,
) -> dict[str, Any]:
    """Payload JSON do GET /kanban.

    `total_desconhecidos` vai para TODA a gente, mesmo para quem não
    recebe a coluna. Esconder a coluna é uma decisão de arrumação;
    esconder o número seria varrer o problema para baixo do tapete.
    """
    return {
        "columns": columns if columns else [],
        "total_processes": active_count,
        "total_inactive": inactive_count,
        "total_desconhecidos": total_desconhecidos,
        "user_role": role,
        "current_user_id": user_id,
        "view_mode": view_mode,
        "completed_days": completed_days,
    }


def resolver_papel_do_quadro(papel_efectivo, user: dict) -> str:
    """Papel a usar no quadro, a partir do perfil ACTIVO do utilizador.

    `__all_roles__` (o perfil "all" do ContextSwitcher) é um conceito das
    LISTAGENS: lá, `all_roles=` faz a união das visibilidades. O
    `build_kanban_role_base_query` não o conhece e cairia no ramo de
    gestão, sem filtro nenhum — o que para quem tem `indexacao` como
    papel base seria um ALARGAMENTO: hoje vê a fila da Indexação,
    passaria a ver o quadro inteiro.

    A regra vive em `services.auth.resolve_concrete_role`, que é o ponto
    único partilhado com as decisões de permissão de escrita. Esta função
    mantém-se como o nome que o quadro usa.
    """
    from services.auth import resolve_concrete_role

    return resolve_concrete_role(papel_efectivo, user)


async def run_get_kanban_board(
    *,
    user: dict,
    role: Any,
    show_all: bool,
    consultor_id: Optional[str],
    mediador_id: Optional[str],
    indexacao_id: Optional[str],
    parceiro_id: Optional[str],
    view_mode: Optional[str],
    completed_days: Optional[int],
    labels: Optional[Any] = None,
    labels_logic: Optional[str] = "OR",
    decrypt_list_fn=None,
    kanban_projection: dict,
) -> dict[str, Any]:
    """Orquestra GET /kanban."""
    from services.process_list_enrichment import (
        enrich_processes_portal_flags,
        enrich_processes_latest_activity,
    )
    from services.process_list_filters import build_kanban_query

    # Isolamento por Rede (Lote 5, ponto 1). O Kanban tem um construtor
    # de query SEPARADO do das listagens, e por isso ficou de fora do
    # Lote 4: um utilizador de uma empresa isolada não via processos na
    # lista e via-os todos no quadro. A condição vem do mesmo ponto único.
    from services.tenant_network import build_tenant_condition

    tenant_condition = await build_tenant_condition(user)

    user_id = user["id"]
    query = build_kanban_query(
        user,
        # Perfil ACTIVO, não o do JWT (achado lateral do ponto 15): este
        # era o único endpoint de listagem a ler `user["role"]`.
        resolver_papel_do_quadro(role, user),
        tenant_condition=tenant_condition,
        show_all=bool(show_all),
        consultor_id=consultor_id,
        mediador_id=mediador_id,
        indexacao_id=indexacao_id,
        parceiro_id=parceiro_id,
        view_mode=view_mode,
        completed_days=completed_days,
        labels=labels,
        labels_logic=labels_logic,
    )
    if str(role).lower() == "indexacao":
        logger.info(
            f"[KANBAN-BQ] Indexacao {user_id} — vista scoped global: "
            f"atribuídos a si OU em fila_espera"
        )

    statuses = await db.workflow_statuses.find(
        {}, {"_id": 0},
    ).sort("order", 1).to_list(100)
    processes = await db.processes.find(query, kanban_projection).to_list(1000)
    processes = decrypt_list_fn(
        processes,
        fields_to_decrypt=["client_phone", "client_nif"],
    )

    await fill_missing_process_client_contacts(processes)
    await enrich_processes_portal_flags(processes)
    await enrich_processes_latest_activity(processes)

    users = await db.users.find(
        {}, {"_id": 0, "id": 1, "name": 1, "role": 1},
    ).to_list(1000)
    user_map = {u["id"]: u for u in users}

    indexacao_count = sum(1 for p in processes if p.get("assigned_indexacao_id"))
    parceiro_count = sum(1 for p in processes if p.get("assigned_parceiro_id"))
    logger.info(
        f"[Kanban Export] {len(processes)} processos: "
        f"{indexacao_count} com indexação, {parceiro_count} com parceiro"
    )

    # As colunas são DITADAS pelo motor, e o agrupamento passa pelo
    # resolvedor: gralhas e nomes antigos caem na coluna certa em vez de
    # desaparecerem do quadro (Épico 10, Parte 3).
    from services.workflow_phases import (
        FASE_DESCONHECIDA, pode_ver_desconhecidas,
    )

    processes_by_status = group_processes_by_status(processes, statuses)
    total_desconhecidos = len(processes_by_status.get(FASE_DESCONHECIDA) or [])

    active_count, inactive_count = await count_kanban_active_inactive(
        query, terminais=nomes_terminais(statuses),
    )
    sort_all_kanban_columns(processes_by_status)

    # O papel do QUADRO (perfil activo), o mesmo que já decide o filtro —
    # não o do JWT. Quem entra como Indexação não reconcilia.
    reconcilia = pode_ver_desconhecidas(resolver_papel_do_quadro(role, user))
    kanban = safe_build_kanban_columns(
        statuses, processes_by_status, user_map, user_id,
        incluir_desconhecidas=reconcilia,
    )
    if total_desconhecidos and not reconcilia:
        logger.info(
            f"[KANBAN] {total_desconhecidos} processo(s) em fases que o motor "
            f"não reconhece — coluna oculta para o papel {role}."
        )

    return build_kanban_board_payload(
        columns=kanban,
        active_count=active_count,
        inactive_count=inactive_count,
        role=role,
        user_id=user_id,
        view_mode=view_mode,
        completed_days=completed_days,
        total_desconhecidos=total_desconhecidos,
    )
