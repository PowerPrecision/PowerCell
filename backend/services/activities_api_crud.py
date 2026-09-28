"""Activities CRUD handlers.

Extraído de `routes/activities.py`.
"""
from __future__ import annotations

from typing import Optional

from fastapi import HTTPException

from database import db
from models.auth import UserRole
from models.activity import ActivityCreate, ActivityResponse

# NOTA (Ponto 9): `uuid`, `datetime`, `log_history`, `_is_stealth_user`,
# `sanitize_string` saíram daqui com o corpo do
# `run_create_activity`. A guarda de indexação silenciosa não se perdeu —
# tornou-se redundante neste módulo, porque já NINGUÉM cria atividades
# por aqui, seja qual for o perfil. O ponto único da regra continua a ser
# `history._is_stealth_user`, para os escritores que restam.


#: O que se responde a quem ainda tente escrever aqui. Um 410 sem destino
#: manda a pessoa procurar às cegas.
ATIVIDADE_MANUAL_DESCONTINUADA = (
    "O histórico do processo é uma trilha de auditoria gerada pelo sistema "
    "e deixou de aceitar registos manuais. As notas do consultor escrevem-se "
    "no campo Observações, no separador Resumo do processo."
)


async def run_create_activity(data: ActivityCreate, user: dict):
    """DESCONTINUADO (Ponto 9) — o histórico é só de leitura.

    O separador Histórico perdeu a UI de adição e este endpoint morreu
    com ela: fechar o ecrã e deixar a porta aberta seria uma regra só na
    aparência.

    **410 e não a rota apagada.** Sem o stub, um `POST /api/activities`
    responde 405 — o caminho continua a existir para o GET e o DELETE —
    e um 405 lê-se como avaria de encaminhamento, mandando quem lá bater
    procurar o defeito no router. O 410 diz o que aconteceu e para onde
    ir. É o precedente que o `POST /auth/login` já usa aqui.

    **A escrita foi REMOVIDA, não desligada.** O corpo antigo (insert em
    `db.activities` + `log_history`) saiu daqui de propósito: código
    adormecido atrás de um `raise` é um convite a religá-lo, e há um
    teste sobre a fonte a afirmar que não voltou.

    **Continuam a escrever, e é assim que tem de ser:** o
    `voice_note_engine` (a nota ditada entra na timeline) e o
    `temp_link_api_public` (o cliente que envia por link temporário).
    Escrevem em `db.activities` directamente e nunca passaram por aqui —
    o que se fechou foi a escrita MANUAL, não o registo automático.

    A recusa vem ANTES de tocar na base de dados: um endpoint que valida
    e só depois recusa continua a ser uma superfície que lê a base de
    dados por ordem de quem chama.
    """
    raise HTTPException(
        status_code=410,
        detail=ATIVIDADE_MANUAL_DESCONTINUADA,
    )


async def run_get_activities(
    process_id: Optional[str],
    limit: int,
    user: dict,
):
    if process_id:
        process = await db.processes.find_one({"id": process_id})
        if not process:
            raise HTTPException(status_code=404, detail="Processo não encontrado")

        if user["role"] == UserRole.CLIENTE and process.get("client_id") != user["id"]:
            raise HTTPException(status_code=403, detail="Acesso negado")

        activities = await db.activities.find(
            {"process_id": process_id}, {"_id": 0}
        ).sort("created_at", -1).to_list(1000)
    else:
        if user["role"] == UserRole.CLIENTE:
            raise HTTPException(status_code=403, detail="Acesso negado")

        activities = await db.activities.find({}, {"_id": 0}).sort(
            "created_at", -1
        ).to_list(limit)

    valid_activities = []
    for a in activities:
        if all(k in a for k in ["id", "user_id", "user_name", "user_role", "comment", "created_at"]):
            valid_activities.append(ActivityResponse(**a))
        elif "comment" in a:
            a.setdefault("user_id", "system")
            a.setdefault("user_name", "Sistema")
            a.setdefault("user_role", "admin")
            valid_activities.append(ActivityResponse(**a))

    return valid_activities


async def run_delete_activity(activity_id: str, user: dict):
    activity = await db.activities.find_one({"id": activity_id})
    if not activity:
        raise HTTPException(status_code=404, detail="Comentário não encontrado")

    if activity["user_id"] != user["id"] and user["role"] != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Só pode eliminar os seus próprios comentários")

    await db.activities.delete_one({"id": activity_id})
    return {"message": "Comentário eliminado"}
