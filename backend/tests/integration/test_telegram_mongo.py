"""Notificações no Telegram, provadas contra um MongoDB REAL.

- A rajada de avisos de um processo (o Index marca como indexado → atribuição, mudança de
  estado, documentos) sai numa SÓ mensagem geral.
- Dois avisos em simultâneo não abrem dois grupos (índice único parcial em `status: pendente`).
- A ligação da conta por código de uso único: o código só serve uma vez.
- A mensagem nunca leva o título da notificação (pode trazer o nome do cliente).

O duplo in-memory não implementa `$push/$slice`, `find_one_and_update` com `$or` nem índices
únicos parciais: só um Mongo real prova isto.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError

from services import db_indexes, notification_policy, telegram_bot, telegram_link, telegram_notifications
from services.telegram_bot import ResultadoDoEnvio

COLECOES = ("telegram_links", "telegram_link_tokens", "telegram_outbox")


@pytest_asyncio.fixture
async def bd(monkeypatch):
    url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    cliente = AsyncIOMotorClient(url, serverSelectionTimeoutMS=2000)
    try:
        await cliente.admin.command("ping")
    except Exception:
        cliente.close()
        pytest.skip("MongoDB não disponível")
    base = cliente[f"test_telegram_{uuid.uuid4().hex[:8]}"]
    resultados = {"created": [], "errors": [], "skipped": []}
    for colecao in COLECOES:
        for idx in db_indexes.INDEX_DEFINITIONS[colecao]:
            await db_indexes._create_index_safe(getattr(base, colecao), idx, colecao, resultados)
    assert resultados["errors"] == []
    # u1 é o consultor de p1 e p2; p3 é de outra pessoa
    await base.processes.insert_many([
        {"id": "p1", "assigned_consultor_ids": ["u1"]},
        {"id": "p2", "assigned_consultor_ids": ["u1"]},
        {"id": "p3", "assigned_consultor_ids": ["outro"]},
    ])

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "PowerCellTesteBot")
    monkeypatch.setenv("TELEGRAM_JANELA_SEGUNDOS", "0")
    monkeypatch.setenv("FRONTEND_URL", "https://app.exemplo.pt")

    enviadas: list[dict] = []

    async def enviar_falso(chat_id, texto, *, url_botao="", texto_botao=""):
        enviadas.append({"chat_id": chat_id, "texto": texto, "url": url_botao})
        return ResultadoDoEnvio(ok=True)

    with patch.object(telegram_link, "db", base), patch.object(telegram_notifications, "db", base), \
            patch.object(notification_policy, "db", base), \
            patch.object(telegram_bot, "enviar_mensagem", enviar_falso):
        base.enviadas = enviadas
        yield base
    await cliente.drop_database(base.name)
    cliente.close()


async def _ligar(bd, user_id="u1", chat_id=555):
    resposta = await telegram_link.run_criar_link({"id": user_id})
    assert resposta["ok"]
    codigo = resposta["url"].split("start=", 1)[1]
    assert resposta["url"].startswith("https://t.me/PowerCellTesteBot?start=")
    await telegram_link.tratar_atualizacao(
        {"message": {"chat": {"id": chat_id, "type": "private"}, "text": f"/start {codigo}"}}
    )
    return codigo


@pytest.mark.asyncio
async def test_ligacao_por_codigo_de_uso_unico(bd):
    codigo = await _ligar(bd)
    ligacao = await bd.telegram_links.find_one({"user_id": "u1"})
    assert ligacao["ativo"] is True and ligacao["chat_id"] == 555
    # o código não fica guardado em claro
    assert await bd.telegram_link_tokens.count_documents({"token_hash": codigo}) == 0

    # outra pessoa a reutilizar o mesmo link não fica ligada
    await telegram_link.tratar_atualizacao(
        {"message": {"chat": {"id": 999, "type": "private"}, "text": f"/start {codigo}"}}
    )
    assert await bd.telegram_links.count_documents({"chat_id": 999}) == 0
    assert "já foi usado" in bd.enviadas[-1]["texto"]


@pytest.mark.asyncio
async def test_parar_desliga(bd):
    await _ligar(bd)
    await telegram_link.tratar_atualizacao(
        {"message": {"chat": {"id": 555, "type": "private"}, "text": "/parar"}}
    )
    ligacao = await bd.telegram_links.find_one({"user_id": "u1"})
    assert ligacao["ativo"] is False and ligacao["chat_id"] is None
    assert await telegram_notifications.agendar("u1", "process_assigned", process_id="p1") is False


@pytest.mark.asyncio
async def test_rajada_do_mesmo_processo_sai_numa_so_mensagem(bd):
    await _ligar(bd)
    bd.enviadas.clear()
    await bd.processes.update_one({"id": "p1"}, {"$set": {"process_number": 1234}})

    # o que nasce quando o Index marca o processo como indexado
    for tipo in ("process_assigned", "process_status_change", "process_status_change", "document_upload"):
        assert await telegram_notifications.agendar("u1", tipo, process_id="p1")
    # um aviso de outro processo fica no seu próprio grupo
    assert await telegram_notifications.agendar("u1", "process_assigned", process_id="p2")

    assert await bd.telegram_outbox.count_documents({"status": "pendente"}) == 2
    assert await telegram_notifications.enviar_pendentes() == 2

    textos = [m["texto"] for m in bd.enviadas]
    geral = next(t for t in textos if "novidades" in t)
    assert "4 novidades no processo nº 1234" in geral
    assert "Mudança de estado (×2)" in geral
    assert "Processo atribuído a si" in geral
    assert any("Processo atribuído a si" in t and "novidades" not in t for t in textos)
    assert all(m["url"].startswith("https://app.exemplo.pt/process/") for m in bd.enviadas)
    assert await bd.telegram_outbox.count_documents({"status": "enviado"}) == 2


@pytest.mark.asyncio
async def test_avisos_em_simultaneo_nao_abrem_dois_grupos(bd):
    await _ligar(bd)
    resultados = await asyncio.gather(
        *[telegram_notifications.agendar("u1", "process_status_change", process_id="p1") for _ in range(10)]
    )
    assert all(resultados)
    grupos = await bd.telegram_outbox.find({"chave": "processo:p1"}).to_list(10)
    assert len(grupos) == 1 and grupos[0]["total"] == 10
    # A corrida do upsert é rara de reproduzir; quem a fecha é o índice: um segundo grupo
    # «pendente» para o mesmo (utilizador, assunto) é recusado pela base de dados.
    with pytest.raises(DuplicateKeyError):
        await bd.telegram_outbox.insert_one({"user_id": "u1", "chave": "processo:p1", "status": "pendente"})
    # ...mas um grupo já a sair não bloqueia o seguinte
    await bd.telegram_outbox.insert_one({"user_id": "u1", "chave": "processo:p1", "status": "enviado"})


@pytest.mark.asyncio
async def test_janela_ainda_aberta_nao_envia(bd, monkeypatch):
    monkeypatch.setenv("TELEGRAM_JANELA_SEGUNDOS", "90")
    await _ligar(bd)
    bd.enviadas.clear()
    await telegram_notifications.agendar("u1", "process_assigned", process_id="p1")
    assert await telegram_notifications.enviar_pendentes() == 0
    assert bd.enviadas == []


@pytest.mark.asyncio
async def test_aviso_novo_durante_o_envio_vai_na_mensagem_seguinte(bd):
    await _ligar(bd)
    await telegram_notifications.agendar("u1", "process_assigned", process_id="p1")
    reclamado = await telegram_notifications._reclamar_proximo(telegram_notifications._agora())
    assert reclamado["status"] == "a_enviar"
    # chega outro aviso enquanto o primeiro grupo está a sair
    assert await telegram_notifications.agendar("u1", "document_upload", process_id="p1")
    assert await bd.telegram_outbox.count_documents({"chave": "processo:p1"}) == 2


@pytest.mark.asyncio
async def test_preferencia_desligada_nao_entra_na_fila(bd):
    await _ligar(bd)
    await telegram_link.run_atualizar_preferencias({"id": "u1"}, {"chat": False}, None)
    assert await telegram_notifications.agendar("u1", "chat_message", conversa="direta:u2", remetente="Ana") is False
    # «outros» vem desligado por defeito
    assert await telegram_notifications.agendar("u1", "property_match", process_id="p1") is False
    assert await telegram_notifications.agendar("u1", "task_assigned") is True


@pytest.mark.asyncio
async def test_chat_agrupa_por_conversa_e_diz_quem_escreveu(bd):
    await _ligar(bd)
    bd.enviadas.clear()
    for _ in range(3):
        await telegram_notifications.agendar("u1", "chat_message", conversa="direta:u2", remetente="Ana")
    await telegram_notifications.enviar_pendentes()
    assert len(bd.enviadas) == 1
    assert "3 mensagens novas no chat de Ana" in bd.enviadas[0]["texto"]


@pytest.mark.asyncio
async def test_bot_bloqueado_desliga_a_conta(bd):
    await _ligar(bd)
    await telegram_notifications.agendar("u1", "process_assigned", process_id="p1")

    async def bloqueado(*_a, **_k):
        return ResultadoDoEnvio(ok=False, bloqueado=True, erro="Forbidden: bot was blocked by the user")

    with patch.object(telegram_bot, "enviar_mensagem", bloqueado):
        await telegram_notifications.enviar_pendentes()
    assert (await bd.telegram_links.find_one({"user_id": "u1"}))["ativo"] is False
    assert await bd.telegram_outbox.count_documents({"status": "descartado"}) == 1


@pytest.mark.asyncio
async def test_falha_temporaria_repete_mais_tarde(bd):
    await _ligar(bd)
    await telegram_notifications.agendar("u1", "process_assigned", process_id="p1")

    async def falha(*_a, **_k):
        return ResultadoDoEnvio(ok=False, erro="502: Bad Gateway")

    with patch.object(telegram_bot, "enviar_mensagem", falha):
        await telegram_notifications.enviar_pendentes()
    grupo = await bd.telegram_outbox.find_one({"chave": "processo:p1"})
    assert grupo["status"] == "a_repetir" and grupo["tentativas"] == 1
    assert grupo["enviar_apos"].replace(tzinfo=None) > (
        telegram_notifications._agora() + timedelta(seconds=30)
    ).replace(tzinfo=None)


@pytest.mark.asyncio
async def test_so_recebe_avisos_dos_processos_atribuidos(bd):
    await _ligar(bd)
    # processo de outra pessoa (ex.: aviso à gestão da rede): fica só na app
    assert await telegram_notifications.agendar("u1", "process_status_change", process_id="p3") is False
    # processo que não existe ou foi eliminado
    assert await telegram_notifications.agendar("u1", "process_status_change", process_id="nao-existe") is False
    await bd.processes.update_one({"id": "p2"}, {"$set": {"is_deleted": True}})
    assert await telegram_notifications.agendar("u1", "document_upload", process_id="p2") is False
    # aviso de processo sem processo (ex.: automação por cargo) também não passa
    assert await telegram_notifications.agendar("u1", "automation") is False
    # o do seu processo passa
    assert await telegram_notifications.agendar("u1", "process_status_change", process_id="p1") is True
    assert await bd.telegram_outbox.count_documents({}) == 1


@pytest.mark.asyncio
async def test_avisos_pessoais_passam_mesmo_sem_atribuicao_ao_processo(bd):
    await _ligar(bd)
    assert await telegram_notifications.agendar("u1", "task_assigned", process_id="p3") is True
    assert await telegram_notifications.agendar("u1", "deadline_reminder", process_id="p3") is True


@pytest.mark.asyncio
async def test_ruido_nunca_vai_para_o_telegram(bd):
    await _ligar(bd)
    for tipo in ("process_updated", "index_sanitize_done", "document_auto_fetch", "new_registration"):
        assert await telegram_notifications.agendar("u1", tipo, process_id="p1") is False
