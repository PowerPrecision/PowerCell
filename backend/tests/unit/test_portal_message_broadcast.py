"""
Testes unitários — a mensagem do cliente chega à sala mesmo sem atribuição.

O DEFEITO (produção, Set 2026, Lote 6 ponto 5)
==============================================
O broadcast para a sala WebSocket do processo era a ÚLTIMA instrução de
`_notify_assigned_team_message`, e essa função abre com:

    assigned_ids = _get_all_assigned_user_ids(process)
    if not assigned_ids:
        return

Num processo sem ninguém atribuído, a mensagem do cliente não era
difundida — e um processo sem atribuição é exactamente o processo novo em
que alguém da equipa está a olhar para o ecrã. No CRM a mensagem só
aparecia quando o polling de 30 s passasse.

A entrega em tempo real e a notificação têm destinatários DIFERENTES: a
sala é de quem tem o processo ABERTO, a notificação é de quem está
ATRIBUÍDO. Ao viverem na mesma função, a primeira herdou a condição da
segunda.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from services import portal_client_messages as pcm


MENSAGEM = {
    "id": "m-1",
    "content": "Bom dia, já enviei o recibo.",
    "created_at": "2026-09-27T11:00:00+00:00",
}


@pytest.mark.asyncio
async def test_difunde_num_processo_SEM_ninguem_atribuido():
    """O caso que estava partido."""
    entregar = AsyncMock()
    with patch.object(pcm, "entregar_na_sala", entregar):
        await pcm._difundir_mensagem_na_sala("p-1", "Ana", MENSAGEM)

    entregar.assert_awaited_once()
    _sala, _evento, payload = entregar.await_args.args
    assert payload["id"] == "m-1"
    assert payload["sender_type"] == "client"


@pytest.mark.asyncio
async def test_a_difusao_nao_depende_da_notificacao():
    """Contraprova de ESTRUTURA: `run_send_portal_message` chama as duas.

    Sem esta afirmação, mover o broadcast para uma função própria e
    esquecer de a chamar deixava os testes de cima verdes e a produção
    igualmente muda.
    """
    processo = {"id": "p-1", "client_name": "Ana"}  # sem atribuições
    entregar = AsyncMock()

    with patch.object(pcm, "db") as fake_db, \
         patch.object(pcm, "entregar_na_sala", entregar), \
         patch.object(pcm, "send_notification_with_preference_check", AsyncMock()):
        fake_db.portal_messages.insert_one = AsyncMock()
        await pcm.run_send_portal_message(
            {"content": "Bom dia"},
            {"process": processo, "process_id": "p-1"},
        )

    entregar.assert_awaited_once()


@pytest.mark.asyncio
async def test_o_conteudo_vai_truncado_a_200():
    """O evento é um SINAL, não o registo.

    `utils/portalRealtime.js` conta com isto: inserir o payload na lista
    deixava uma mensagem longa truncada no ecrã para sempre.
    """
    entregar = AsyncMock()
    longa = {**MENSAGEM, "content": "x" * 500}
    with patch.object(pcm, "entregar_na_sala", entregar):
        await pcm._difundir_mensagem_na_sala("p-1", "Ana", longa)

    _sala, _evento, payload = entregar.await_args.args
    assert len(payload["content"]) == 200


@pytest.mark.asyncio
async def test_uma_falha_da_difusao_nunca_propaga():
    """A mensagem já está gravada e o cliente já recebeu o 200."""
    with patch.object(pcm, "entregar_na_sala", AsyncMock(side_effect=RuntimeError("socket em baixo"))):
        await pcm._difundir_mensagem_na_sala("p-1", "Ana", MENSAGEM)
