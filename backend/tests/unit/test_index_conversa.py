"""Conversa do processo entre o Index e quem o carregou (Out 2026).

Afirma-se: quem carregou resolve-se pelo carimbo, pelo histórico e pela atribuição, nunca um parceiro
nem um inactivo; o Index escreve-lhe e ele recebe no chat interno e numa notificação; a resposta no
detalhe do processo vai para o indexador atribuído; a resposta dada no chat interno volta ao processo;
abrir a conversa marca como lido o que era para mim; e nada disto escreve no histórico (stealth).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from models.chat import ChatMessageCreate
from services import chat_messages, index_conversa as conversa

PID = "p-conversa"
INDEX = {"id": "u-index", "name": "Ana Index", "role": "indexacao"}
INTER = {"id": "u-inter", "name": "Rui Intermediário", "role": "intermediario"}
CONSULTOR = {"id": "u-cons", "name": "Eva Consultora", "role": "consultor"}
PARCEIRO = {"id": "u-parc", "name": "Parceiro", "role": "parceiro"}


class _Contexto:
    def __init__(self, db):
        self.patches = [
            patch.object(conversa, "db", db),
            patch.object(chat_messages, "db", db),
            patch.object(conversa, "entregar_a_utilizador", AsyncMock()),
            patch.object(chat_messages, "entregar_a_utilizador", AsyncMock()),
            patch("services.realtime_notifications.send_realtime_notification", AsyncMock(return_value=True)),
        ]

    def __enter__(self):
        mocks = [p.__enter__() for p in self.patches]
        self.avisar = mocks[-1]
        return self

    def __exit__(self, *exc):
        for p in reversed(self.patches):
            p.__exit__(*exc)


async def _cenario(db, **campos):
    for u in (INDEX, INTER, CONSULTOR, PARCEIRO):
        await db.users.insert_one(dict(u))
    proc = {"id": PID, "process_number": 42, "client_name": "Cliente", "is_deleted": False,
            "assigned_indexacao_id": INDEX["id"], "indexacao_name": INDEX["name"]}
    proc.update(campos)
    await db.processes.insert_one(proc)


@pytest.mark.asyncio
async def test_quem_carregou_pelo_carimbo(fake_async_db):
    await _cenario(fake_async_db, created_by_id=INTER["id"], assigned_consultor_id=CONSULTOR["id"])
    with _Contexto(fake_async_db):
        u = await conversa.resolver_quem_carregou(await fake_async_db.processes.find_one({"id": PID}))
    assert u == {"id": INTER["id"], "name": INTER["name"]}


@pytest.mark.asyncio
async def test_quem_carregou_pelo_historico_nos_processos_antigos(fake_async_db):
    await _cenario(fake_async_db, assigned_mediador_ids=[CONSULTOR["id"]])
    await fake_async_db.history.insert_one({"process_id": PID, "user_id": INTER["id"],
                                            "action": "Criou processo para cliente X", "created_at": "2026-01-01"})
    with _Contexto(fake_async_db):
        u = await conversa.resolver_quem_carregou(await fake_async_db.processes.find_one({"id": PID}))
    assert u["id"] == INTER["id"]


@pytest.mark.asyncio
async def test_quem_carregou_salta_parceiro_e_inactivo_e_cai_na_atribuicao(fake_async_db):
    await _cenario(fake_async_db, created_by_id=PARCEIRO["id"], assigned_mediador_ids=[INTER["id"]],
                   assigned_consultor_id=CONSULTOR["id"])
    await fake_async_db.users.update_one({"id": INTER["id"]}, {"$set": {"is_active": False}})
    with _Contexto(fake_async_db):
        u = await conversa.resolver_quem_carregou(await fake_async_db.processes.find_one({"id": PID}))
    assert u["id"] == CONSULTOR["id"]


@pytest.mark.asyncio
async def test_index_escreve_a_quem_carregou_e_ele_recebe_e_le(fake_async_db):
    await _cenario(fake_async_db, created_by_id=INTER["id"])
    with _Contexto(fake_async_db) as ctx:
        r = await conversa.run_enviar_do_index(INDEX, PID, conversa.MensagemDaConversa(text="Falta o recibo de Março"))
        assert ctx.avisar.await_args.kwargs["user_id"] == INTER["id"]
        assert ctx.avisar.await_args.kwargs["link"].startswith(f"/processo/{PID}")
    msg = r["message"]
    assert msg["receiver_id"] == INTER["id"] and msg["canal"] == "index" and msg["process_id"] == PID
    assert msg["read"] is False

    with _Contexto(fake_async_db):
        lido = await conversa.run_ler_conversa_do_processo(INTER, PID)
    assert lido["interlocutor"]["id"] == INDEX["id"]
    assert [m["content"] for m in lido["messages"]] == ["Falta o recibo de Março"]
    assert lido["messages"][0]["mine"] is False
    assert (await fake_async_db.chat_messages.find_one({"id": msg["id"]}))["read"] is True
    # stealth: o mural do processo não ganha nada
    assert await fake_async_db.history.count_documents({}) == 0


@pytest.mark.asyncio
async def test_resposta_no_detalhe_vai_para_o_indexador_atribuido(fake_async_db):
    await _cenario(fake_async_db, created_by_id=INTER["id"])
    with _Contexto(fake_async_db):
        r = await conversa.run_enviar_do_processo(INTER, PID, conversa.MensagemDaConversa(text="Já carreguei"))
        vista = await conversa.run_ler_conversa_do_index(INDEX, PID)
    assert r["message"]["receiver_id"] == INDEX["id"]
    assert vista["interlocutor"]["id"] == INTER["id"]
    assert vista["messages"][0]["content"] == "Já carreguei"


@pytest.mark.asyncio
async def test_sem_index_atribuido_recusa_a_resposta(fake_async_db):
    await _cenario(fake_async_db, created_by_id=INTER["id"], assigned_indexacao_id=None)
    with _Contexto(fake_async_db), pytest.raises(HTTPException) as erro:
        await conversa.run_enviar_do_processo(INTER, PID, conversa.MensagemDaConversa(text="Olá"))
    assert erro.value.status_code == 409


@pytest.mark.asyncio
async def test_index_que_carregou_nao_fala_consigo_proprio(fake_async_db):
    await _cenario(fake_async_db, created_by_id=INDEX["id"])
    with _Contexto(fake_async_db), pytest.raises(HTTPException) as erro:
        await conversa.run_enviar_do_index(INDEX, PID, conversa.MensagemDaConversa(text="Olá"))
    assert erro.value.status_code == 409


@pytest.mark.asyncio
async def test_resposta_pelo_chat_interno_volta_ao_processo(fake_async_db):
    await _cenario(fake_async_db, created_by_id=INTER["id"])
    with _Contexto(fake_async_db):
        await conversa.run_enviar_do_index(INDEX, PID, conversa.MensagemDaConversa(text="Este IRS é de 2023?"))
        r = await chat_messages.run_send_message(
            ChatMessageCreate(receiver_id=INDEX["id"], content="Sim, é de 2023"), INTER)
        vista = await conversa.run_ler_conversa_do_index(INDEX, PID)
    assert r["message"]["process_id"] == PID and r["message"]["canal"] == "index"
    assert r["message"]["lado"] == "processo"
    assert [m["content"] for m in vista["messages"]] == ["Este IRS é de 2023?", "Sim, é de 2023"]


@pytest.mark.asyncio
async def test_chat_interno_sem_conversa_do_processo_nao_herda(fake_async_db):
    await _cenario(fake_async_db, created_by_id=INTER["id"])
    with _Contexto(fake_async_db):
        r = await chat_messages.run_send_message(ChatMessageCreate(receiver_id=INDEX["id"], content="Olá"), INTER)
    assert r["message"].get("canal") is None and r["message"].get("process_id") is None
