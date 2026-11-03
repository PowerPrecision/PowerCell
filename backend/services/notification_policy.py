"""
====================================================================
POLÍTICA DAS NOTIFICAÇÕES — quem recebe o quê, e como se juntam
====================================================================
Pedido do dono (Out 2026): «não quero receber notificações de outros
processos nem ruído», e a rajada de avisos de um processo (o Index marca
como indexado → atribuições, mudanças de estado, documentos) tem de
aparecer como UM só aviso, na app como no Telegram.

Regras (as mesmas para a app e para o Telegram, salvo onde se diz):

1. Ruído (`TIPOS_RUIDO`) nunca é notificado.
2. Avisos pessoais (`TIPOS_PESSOAIS`: tarefas, prazos, agenda, chat)
   passam sempre — são dirigidos à pessoa, não ao processo.
3. Na app, a ACTIVIDADE de um processo (`TIPOS_DE_ACTIVIDADE`: estado,
   documentos, atribuição, Portal…) só passa a quem está ATRIBUÍDO a esse
   processo (consultor, intermediário, Index…) e se o processo não estiver
   eliminado. Os outros avisos de processo são dirigidos de propósito a
   alguém que não está atribuído — a gestão (registo novo, SLA do Index,
   pedido de atribuição), quem pediu a análise, quem perdeu o processo —
   e continuam a chegar.
4. No Telegram é mais estrito: qualquer aviso de processo só vai a quem lá
   está atribuído, e um aviso sem processo só vai se for pessoal.
5. Ninguém é avisado do que ele próprio fez (Flavio, Nov 2026). Quem fez a
   acção é o utilizador autenticado do pedido (`ator_atual`, preenchido em
   `services/auth.get_current_user`). Só vale para a ACTIVIDADE e para as
   tarefas (`TIPOS_DO_PROPRIO`): o resultado de um trabalho que a pessoa pediu
   (análise do Index concluída, email que não saiu) continua a chegar-lhe.
6. Só «apita» (som, toast, push) o que também iria para o Telegram
   (`vai_apitar`): o resto fica calado no sino, como histórico.
====================================================================
"""
from __future__ import annotations

import contextvars
from typing import Optional

from database import db

TIPOS_RUIDO: frozenset[str] = frozenset({
    "process_updated",       # «alguém mexeu no processo», sem dizer o quê
    "index_sanitize_done",   # manutenção do Index
    "document_auto_fetch",   # recolha automática, sem acção pedida
})

TIPOS_PESSOAIS: frozenset[str] = frozenset({
    "task_assigned",
    "task_unassigned",
    "task_completed",
    "deadline",
    "deadline_reminder",
    "deadline_approaching",
    "deadline_missed",
    "event_reminder",
    "chat_message",
    "chat_group_message",
    "index_conversa",
})

TIPOS_DE_ACTIVIDADE: frozenset[str] = frozenset({
    "process_created",
    "new_process",
    "process_assigned",
    "process_status_change",
    "status_change",
    "document_upload",
    "document_uploaded",
    "document_verification",
    "indexing_complete",
    "portal_message",
    "visit_request",
    "visit_update",
    "partner_note",
})


#: Avisos que nunca vão a quem fez a acção (regra 5).
TIPOS_DO_PROPRIO: frozenset[str] = TIPOS_DE_ACTIVIDADE | frozenset({
    "task_assigned",
    "task_unassigned",
    "task_completed",
    "process_unassigned",
})

#: Quem fez a acção do pedido em curso (o utilizador autenticado). Fora de um pedido é None.
ator_atual: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("ator_atual", default=None)


def definir_ator(user_id: Optional[str]) -> None:
    ator_atual.set(str(user_id) if user_id else None)


def e_o_proprio(user_id: str, tipo: str) -> bool:
    """O aviso é sobre algo que o próprio destinatário acabou de fazer?"""
    ator = ator_atual.get()
    return bool(ator) and ator == str(user_id) and tipo in TIPOS_DO_PROPRIO


async def atribuido_ao_processo(user_id: str, process_id: str, bd=None) -> bool:
    """O utilizador está atribuído ao processo (e o processo não foi eliminado)?"""
    from services.alert_audience import ids_atribuidos

    processo = await (bd if bd is not None else db).processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}}, {"_id": 0}
    )
    return bool(processo) and user_id in ids_atribuidos(processo)


async def deve_notificar(
    user_id: str, tipo: str, process_id: Optional[str], *, canal: str = "app", bd=None
) -> bool:
    """Aplica as regras do topo. `canal` é "app" ou "telegram".

    `bd` é a base de quem chama (o worker tem o seu cliente; os testes trocam o `db` do módulo).
    """
    if not user_id or tipo in TIPOS_RUIDO:
        return False
    if e_o_proprio(user_id, tipo):
        return False
    if tipo in TIPOS_PESSOAIS:
        return True
    if canal == "app":
        if tipo not in TIPOS_DE_ACTIVIDADE or not process_id:
            return True
    elif not process_id:
        # No Telegram, um aviso sem processo que não seja pessoal é ruído.
        return False
    return await atribuido_ao_processo(user_id, process_id, bd)


async def vai_apitar(user_id: str, tipo: str, *, urgente: bool = False, bd=None) -> bool:
    """O aviso merece som/toast/push? Sim quando a sua categoria do Telegram está ligada
    para esta pessoa (as escolhas dela, ou as omissões se nunca escolheu). Nunca levanta."""
    try:
        from services import telegram_link
        from services.telegram_notifications import TIPOS_SEM_TELEGRAM, categoria_de

        if tipo in TIPOS_SEM_TELEGRAM:
            return False
        ligacao = await (bd if bd is not None else db).telegram_links.find_one(
            {"user_id": user_id}, {"_id": 0, "preferencias": 1, "preferencias_versao": 1}
        )
        preferencias = telegram_link.preferencias_efectivas(ligacao)
        return bool(preferencias.get(categoria_de(tipo, urgente=urgente), False))
    except Exception:  # noqa: BLE001 - na dúvida, não apita
        return False
