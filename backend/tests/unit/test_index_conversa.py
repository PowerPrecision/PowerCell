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
        self.avisar = mocks[4]  # send_realtime_notification
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
    assert u == {"id": INTER["id"], "name": INTER["name"], "tipo": "utilizador"}


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


# ====================================================================
# PARCEIRO — quando foi o parceiro a carregar o processo
# ====================================================================
from types import SimpleNamespace  # noqa: E402

PT = {"id": "pt-1", "name": "Rui Parceiro"}


class _ComParceiro(_Contexto):
    def __init__(self, db, activo=True, e_processo=True):
        super().__init__(db)
        contacto = {"id": PT["id"], "name": PT["name"], "email": "rui@parceiro.pt"} if activo else None
        self.email = AsyncMock()
        self.emails: list = []
        self.patches += [
            patch("services.partner_accounts.parceiro_activo", AsyncMock(return_value=contacto)),
            patch("services.partner_portal_read.resolver_caso",
                  AsyncMock(return_value=SimpleNamespace(e_processo=e_processo, id=PID))),
            patch("services.process_closed_guard.processo_esta_fechado", AsyncMock(return_value=False)),
            patch("services.background_tasks.spawn_background_task", lambda coro, name=None: self.emails.append(name) or coro.close()),
            patch.object(conversa, "_enviar_email_ao_parceiro", self.email),
        ]


async def _cenario_do_parceiro(db, **campos):
    await db.clients.insert_one({"id": "c1", "submitted_by_partner_id": PT["id"]})
    await _cenario(db, client_id="c1", assigned_parceiro_id=PT["id"], created_by_id=INTER["id"], **campos)


@pytest.mark.asyncio
async def test_parceiro_que_submeteu_a_lead_e_quem_carregou(fake_async_db):
    await _cenario_do_parceiro(fake_async_db)
    with _ComParceiro(fake_async_db):
        u = await conversa.resolver_quem_carregou(await fake_async_db.processes.find_one({"id": PID}))
    assert u == {"id": PT["id"], "name": PT["name"], "tipo": "parceiro"}


@pytest.mark.asyncio
async def test_parceiro_so_atribuido_ou_inactivo_nao_conta(fake_async_db):
    await fake_async_db.clients.insert_one({"id": "c1", "submitted_by_partner_id": "outro"})
    await _cenario(fake_async_db, client_id="c1", assigned_parceiro_id=PT["id"], created_by_id=INTER["id"])
    with _ComParceiro(fake_async_db):
        u = await conversa.resolver_quem_carregou(await fake_async_db.processes.find_one({"id": PID}))
    assert u["id"] == INTER["id"]
    await fake_async_db.clients.update_one({"id": "c1"}, {"$set": {"submitted_by_partner_id": PT["id"]}})
    with _ComParceiro(fake_async_db, activo=False):
        u = await conversa.resolver_quem_carregou(await fake_async_db.processes.find_one({"id": PID}))
    assert u["id"] == INTER["id"]


@pytest.mark.asyncio
async def test_index_fala_com_o_parceiro_e_ele_responde_no_portal(fake_async_db):
    await _cenario_do_parceiro(fake_async_db)
    with _ComParceiro(fake_async_db) as ctx:
        await conversa.run_enviar_do_index(INDEX, PID, conversa.MensagemDaConversa(text="Falta o IRS"))
        await conversa.run_enviar_do_index(INDEX, PID, conversa.MensagemDaConversa(text="E o recibo"))
        # um email só pela primeira por ler; nada vai ao chat interno nem às notificações do CRM
        assert len(ctx.emails) == 1
        assert ctx.avisar.await_count == 0
        lido = await conversa.run_ler_conversa_do_parceiro(PT, PID)
        assert [m["content"] for m in lido["messages"]] == ["Falta o IRS", "E o recibo"]
        assert lido["interlocutor"] == {"name": INDEX["name"]}
        r = await conversa.run_enviar_do_parceiro(PT, PID, conversa.MensagemDaConversa(text="Envio amanhã"))
        assert ctx.avisar.await_args.kwargs["user_id"] == INDEX["id"]
        vista = await conversa.run_ler_conversa_do_index(INDEX, PID)
    assert r["message"]["mine"] is True
    assert vista["messages"][-1]["content"] == "Envio amanhã"
    assert vista["messages"][-1]["sender_name"] == "Rui Parceiro (Parceiro)"
    assert await fake_async_db.chat_messages.count_documents({"receiver_id": PT["id"], "read": False}) == 0


@pytest.mark.asyncio
async def test_parceiro_nao_ve_as_mensagens_internas_da_equipa(fake_async_db):
    await _cenario_do_parceiro(fake_async_db)
    with _ComParceiro(fake_async_db):
        await conversa.run_enviar_do_processo(INTER, PID, conversa.MensagemDaConversa(text="nota interna"))
        await conversa.run_enviar_do_index(INDEX, PID, conversa.MensagemDaConversa(text="Para o parceiro"))
        lido = await conversa.run_ler_conversa_do_parceiro(PT, PID)
    assert [m["content"] for m in lido["messages"]] == ["Para o parceiro"]


@pytest.mark.asyncio
async def test_numa_lead_nao_ha_conversa(fake_async_db):
    await _cenario_do_parceiro(fake_async_db)
    with _ComParceiro(fake_async_db, e_processo=False), pytest.raises(HTTPException) as erro:
        await conversa.run_enviar_do_parceiro(PT, PID, conversa.MensagemDaConversa(text="Olá"))
    assert erro.value.status_code == 409


@pytest.mark.asyncio
async def test_mensagens_do_parceiro_nao_contam_no_chat_interno(fake_async_db):
    from services import chat_presence

    await _cenario_do_parceiro(fake_async_db)
    with _ComParceiro(fake_async_db), patch.object(chat_presence, "db", fake_async_db):
        await conversa.run_enviar_do_parceiro(PT, PID, conversa.MensagemDaConversa(text="Olá"))
        r = await chat_presence.run_get_unread_count(INDEX)
    assert r["direct_unread"] == 0


# ── «Carregado por» na fila do Index: mostrar, não contactar ─────────────────────────────────────────
@pytest.mark.asyncio
async def test_nomes_de_quem_carregou_por_pagina(fake_async_db):
    for u in (INTER, CONSULTOR, PARCEIRO):
        await fake_async_db.users.insert_one(dict(u))
    await fake_async_db.users.update_one({"id": INTER["id"]}, {"$set": {"is_active": False, "email": "rui@x.pt"}})
    await fake_async_db.clients.insert_many([
        {"id": "c-parc", "submitted_by_partner_id": "par-1"},
        {"id": "c-outro", "submitted_by_partner_id": "par-2"},
    ])
    await fake_async_db.partners.insert_one({"id": "par-1", "name": "Imobiliária Sol", "status": "suspenso"})
    await fake_async_db.history.insert_many([
        {"process_id": "p-hist", "user_id": CONSULTOR["id"], "action": "Criou processo", "created_at": "2026-01-01"},
        {"process_id": "p-hist", "user_id": INTER["id"], "action": "Criou processo", "created_at": "2026-02-01"},
    ])
    processos = [
        # parceiro: o cliente foi submetido pelo parceiro atribuído (mesmo com a conta suspensa, foi ele)
        {"id": "p-parc", "client_id": "c-parc", "assigned_parceiro_id": "par-1", "created_by_id": CONSULTOR["id"]},
        # parceiro atribuído que NÃO submeteu o cliente: vale o carimbo
        {"id": "p-nao-parc", "client_id": "c-outro", "assigned_parceiro_id": "par-1", "created_by_id": CONSULTOR["id"]},
        {"id": "p-nome", "created_by_name": "Nome Gravado", "created_by_id": CONSULTOR["id"]},
        # um inactivo continua a ter o nome: foi quem carregou
        {"id": "p-inactivo", "created_by_id": INTER["id"]},
        {"id": "p-portal", "source": "onboarding_auto", "created_by": "onboarding_auto"},
        {"id": "p-email", "created_by": "RUI@x.pt"},
        {"id": "p-hist"},
        # sem autor: nunca cai no mediador/consultor atribuído (não carregaram nada)
        {"id": "p-nada", "assigned_mediador_ids": [INTER["id"]], "assigned_consultor_id": CONSULTOR["id"]},
        # um id de parceiro em `users` nunca aparece como utilizador
        {"id": "p-user-parceiro", "created_by_id": PARCEIRO["id"]},
    ]
    with patch.object(conversa, "db", fake_async_db):
        nomes = await conversa.nomes_de_quem_carregou(processos)
    assert nomes["p-parc"] == {"name": "Imobiliária Sol", "tipo": "parceiro"}
    assert nomes["p-nao-parc"] == {"name": CONSULTOR["name"], "tipo": "utilizador"}
    assert nomes["p-nome"]["name"] == "Nome Gravado"
    assert nomes["p-inactivo"]["name"] == INTER["name"]
    assert nomes["p-portal"] == {"name": conversa.ROTULO_CLIENTE_PORTAL, "tipo": "cliente"}
    assert nomes["p-email"]["name"] == INTER["name"]
    assert nomes["p-hist"]["name"] == CONSULTOR["name"]  # o PRIMEIRO «Criou processo»
    assert "p-nada" not in nomes
    assert "p-user-parceiro" not in nomes


@pytest.mark.asyncio
async def test_nomes_de_quem_carregou_nunca_derruba_a_fila(fake_async_db):
    rebenta = AsyncMock(side_effect=RuntimeError("mongo em baixo"))
    with patch.object(conversa, "_nomes_de_quem_carregou", rebenta):
        assert await conversa.nomes_de_quem_carregou([{"id": "p"}]) == {}
