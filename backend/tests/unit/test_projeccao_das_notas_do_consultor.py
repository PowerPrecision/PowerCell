"""A coluna "Notas do Consultor" só existe se a projecção a servir (Ponto 9).

O DEFEITO QUE ISTO FECHA
========================
As duas listagens do frontend liam `latest_activity_preview`,
`latest_note` e `latest_activity_note`. Esses três nomes têm **zero**
ocorrências em `backend/` — nunca existiram. Na `FilteredProcessList`,
onde a cascata só lia esses três, a coluna dizia "Sem notas recentes" em
TODOS os processos, sempre, desde que foi escrita; na `ProcessesPage` a
cascata tinha ramos por baixo que chegavam a `notes`, e foi essa metade a
funcionar que escondeu a outra.

Ninguém deu por isso porque **uma coluna vazia não produz erro nenhum** e
nenhum teste monta aquelas páginas.

PORQUE É QUE A GUARDA VIVE DO LADO DO BACKEND
=============================================
O frontend não consegue afirmar o que a projecção traz — só vê o que lhe
chega. Quem sabe é este lado. O contrato é: os campos que
`frontend/src/utils/processObservationNotes.js` lê têm de estar nas
projecções das listagens, senão a coluna volta a ficar vazia em silêncio.

É a mesma lição do `{config, fields}` dos SLAs e do `/portal/status`:
**ler o endpoint antes de escrever o ecrã**. Aqui a guarda é o que impede
que a próxima pessoa tenha de a aprender outra vez.
"""
from __future__ import annotations

import pytest

from services.process_service import (
    PROCESS_KANBAN_PROJECTION,
    PROCESS_LIST_PROJECTION,
)

#: O que `resolveProcessObservationNotes` lê para as notas de PESSOA.
#: `ai_extracted_notes` fica deliberadamente de fora das listagens — ver
#: `notaMaisRecenteDoConsultor`.
CAMPOS_DAS_NOTAS = ("observation_notes", "observations", "notes")

#: Nomes que o frontend chegou a ler e que o backend NUNCA produziu.
CAMPOS_INVENTADOS = (
    "latest_activity_preview",
    "latest_note",
    "latest_activity_note",
)


@pytest.mark.parametrize("campo", CAMPOS_DAS_NOTAS)
def test_a_listagem_serve_os_campos_das_notas(campo):
    assert PROCESS_LIST_PROJECTION.get(campo) == 1, (
        f"`{campo}` saiu da projecção da listagem — a coluna "
        "'Notas do Consultor' fica vazia sem dar erro nenhum."
    )


@pytest.mark.parametrize("campo", CAMPOS_DAS_NOTAS)
def test_o_kanban_serve_os_mesmos_campos(campo):
    # O cartão do Kanban mostra o mesmo texto livre; divergir daqui é a
    # forma de os dois ecrãs mostrarem coisas diferentes do mesmo campo.
    assert PROCESS_KANBAN_PROJECTION.get(campo) == 1


@pytest.mark.parametrize("campo", CAMPOS_INVENTADOS)
def test_os_campos_inventados_continuam_a_nao_existir(campo):
    """Contraprova, e é ela que dá sentido às asserções de cima.

    Se alguém acrescentar um destes à projecção, é porque o passou a
    calcular — e então a decisão do Ponto 9 (a listagem espelha o Resumo,
    não o Histórico) está a ser desfeita sem se dizer.
    """
    assert campo not in PROCESS_LIST_PROJECTION
    assert campo not in PROCESS_KANBAN_PROJECTION
