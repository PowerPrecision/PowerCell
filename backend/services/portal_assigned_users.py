"""IDs de utilizadores atribuídos a um processo (portal notify helpers).

Extraído de `routes/portal.py`. Fonte de verdade para
`process_portal_messages.collect_assigned_user_ids`.
"""
from __future__ import annotations


def get_all_assigned_user_ids(process: dict) -> list:
    """Lista deduplicada de TODOS os user_ids atribuídos. Delega no ponto único.

    A docstring desta função chamava-se a si mesma "fonte de verdade"
    (ver `process_portal_messages.collect_assigned_user_ids`) e era uma
    das TRÊS cópias da lista de campos, com SEIS campos escritos à mão.
    Faltavam-lhe `consultor_id`, `consultant_id` e `mediador_id`, pelo
    que um processo atribuído só por esses campos não notificava
    ninguém — nem o consultor que trata dele.

    A fonte de verdade é o `ASSIGNMENT_ID_FIELDS`, que vive ao lado dos
    campos que os escritores carimbam e deriva deles.
    """
    from services.process_staff_assignment import collect_assigned_ids

    return collect_assigned_ids(process)


# Compat alias (routes.portal used underscore prefix)
_get_all_assigned_user_ids = get_all_assigned_user_ids
