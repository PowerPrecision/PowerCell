"""Communications feed for executive dashboards.

Extraído de `routes/stats.py`.
"""
from __future__ import annotations

import logging

from database import db
from models.auth import UserRole
from services.stats_scope import com_ambito, processos_no_ambito, resolver_ambito

logger = logging.getLogger(__name__)


async def _processos_com_pendentes(coleccao, filtro: dict, ambito) -> list[str]:
    """Dos processos com itens pendentes, os que são da rede de quem pede.

    O sentido barato: `distinct` sobre a colecção PEQUENA (mensagens não
    lidas, emails não lidos) dá dezenas de processos, e só esses se
    verificam contra a rede. Trazer os processos da rede para um `$in`
    seria doze mil identificadores por pedido.
    """
    ids = [i for i in await coleccao.distinct("process_id", filtro) if i]
    return sorted(await processos_no_ambito(ids, ambito))

async def run_get_communications_feed(user: dict):
    """
    Feed de comunicações para os Dashboards Executivos.

    Retorna dois arrays de dados:
    a) Avisos do Portal: Últimas mensagens submetidas por clientes no portal
       onde read_by_staff é False.
    b) Emails Pendentes: Últimos emails recebidos com is_read a False.

    Filtrado pelo role do utilizador:
    - Admin/CEO/Administrativo/Diretor: vê tudo
    - Consultores/Intermediários: vê apenas dos seus processos
    - Indexação: vê apenas dos seus processos
    - Clientes: não vê nada (dados internos)

    NOTA: TTL curto (5 min) porque comunicações são time-sensitive.
    """
    import logging
    _logger = logging.getLogger(__name__)

    role = user["role"]
    user_id = user["id"]

    # Clientes não têm acesso ao feed de comunicações internas
    if role == UserRole.CLIENTE:
        return {"portal_messages": [], "unread_emails": [], "portal_unread_count": 0, "email_unread_count": 0}

    # ====================================================================
    # ISOLAMENTO DE REDE (Dashboard, ponto 1)
    # ====================================================================
    # Este era o pior dos seis endpoints: para admin/ceo/administrativo/
    # diretor, `process_ids` ficava `None` e não havia filtro NENHUM. E o
    # que este feed devolve não é uma contagem — são os primeiros 150
    # caracteres do que os clientes escreveram no Portal, os assuntos dos
    # emails não lidos e os endereços de quem os enviou. Uma Diretora da
    # Domus lia as mensagens dos clientes da Power.
    #
    # `None` deixa de significar "sem filtro": significa "sem restrição
    # por ATRIBUIÇÃO". A fronteira de REDE aplica-se sempre, aos dois
    # ramos — é isso que o `permitidos` abaixo faz.
    ambito = await resolver_ambito(user)

    # ── Determinar process_ids do utilizador (filtragem por atribuição) ──
    process_ids = None  # None = sem restrição por atribuição

    if role not in [UserRole.ADMIN, UserRole.CEO, UserRole.ADMINISTRATIVO, UserRole.DIRETOR]:
        # Consultores/Intermediários/Indexação: apenas os seus processos
        or_conditions = [
            {"assigned_consultor_id": user_id},
            {"consultor_id": user_id},
            {"assigned_mediador_id": user_id},
            {"intermediario_id": user_id},
        ]
        if role == UserRole.INDEXACAO:
            or_conditions = [{"assigned_indexacao_id": user_id}]

        my_processes = await db.processes.find(
            com_ambito(
                {"$or": or_conditions, "is_deleted": {"$ne": True}}, ambito,
            ),
            {"id": 1, "_id": 0}
        ).to_list(1000)
        process_ids = [p["id"] for p in my_processes]

    # ── Portal Messages (não lidas pelo staff) ──
    portal_query = {"read_by_staff": False}
    if process_ids is not None:
        portal_query["process_id"] = {"$in": process_ids}
    else:
        # Sem restrição por atribuição, a rede é a única fronteira — e
        # tem de estar na query ANTES do `limit(15)`: filtrar depois
        # devolveria uma lista curta (ou vazia) porque as mensagens da
        # outra rede tinham gasto as quinze posições.
        portal_query["process_id"] = {"$in": await _processos_com_pendentes(
            db.portal_messages, {"read_by_staff": False}, ambito,
        )}

    portal_cursor = db.portal_messages.find(
        portal_query,
        {"_id": 0}
    ).sort("created_at", -1).limit(15)

    portal_messages = []
    async for msg in portal_cursor:
        # Enriquecer com nome do processo/cliente
        process_info = await db.processes.find_one(
            {"id": msg.get("process_id")},
            {"client_name": 1, "process_number": 1, "_id": 0}
        )
        portal_messages.append({
            "id": msg.get("id"),
            "process_id": msg.get("process_id"),
            "sender_name": msg.get("sender_name", "Cliente"),
            "content": (msg.get("content") or "")[:150],
            "created_at": msg.get("created_at"),
            "client_name": process_info.get("client_name", "") if process_info else "",
            "process_number": process_info.get("process_number") if process_info else None,
        })

    # ── Emails Pendentes (não lidos) ──
    email_query = {"is_read": False}
    if process_ids is not None:
        email_query["process_id"] = {"$in": process_ids}
    else:
        # `db.emails` NÃO é carimbada com a rede (oito sítios de escrita
        # mais o sync IMAP/Gmail — fica para o lote do webmail), por isso
        # o âmbito resolve-se pelo PROCESSO do email. Consequência
        # assumida: um email sem processo deixa de aparecer aqui a estes
        # papéis. Era o que já acontecia aos consultores, e um email que
        # não se consegue atribuir a uma rede não se pode mostrar a uma.
        email_query["process_id"] = {"$in": await _processos_com_pendentes(
            db.emails, {"is_read": False}, ambito,
        )}

    # A coleção de emails pode variar — verificar se existe 'emails'
    email_cursor = db.emails.find(
        email_query,
        {"_id": 0}
    ).sort("received_at", -1).limit(15)

    unread_emails = []
    async for email in email_cursor:
        # Enriquecer com nome do processo/cliente
        process_info = None
        if email.get("process_id"):
            process_info = await db.processes.find_one(
                {"id": email["process_id"]},
                {"client_name": 1, "process_number": 1, "_id": 0}
            )
        unread_emails.append({
            "id": email.get("id"),
            "process_id": email.get("process_id"),
            "subject": email.get("subject", "(Sem assunto)"),
            "from_address": email.get("from_address", email.get("from", "")),
            "received_at": email.get("received_at", email.get("created_at")),
            "client_name": process_info.get("client_name", "") if process_info else "",
            "process_number": process_info.get("process_number") if process_info else None,
        })

    # Contagens totais (para os KPI cards)
    portal_unread_count = await db.portal_messages.count_documents(portal_query)
    email_unread_count = await db.emails.count_documents(email_query)

    return {
        "portal_messages": portal_messages,
        "unread_emails": unread_emails,
        "portal_unread_count": portal_unread_count,
        "email_unread_count": email_unread_count,
    }

