"""
Notificações: só as do próprio (Lote 5, ponto 3).

O DEFEITO
  As notificações TÊM `user_id` — quem as deve receber (ver
  `ScheduledTasksService.create_notification`). `run_get_notifications`
  nunca o usava. Nem uma vez.

    if user["role"] not in [ADMIN, CEO, DIRETOR]:
        ...filtra por PROCESSO...

  Duas consequências:
    1. Admin, CEO e Diretor caem FORA do `if`: `query = {}`. Recebiam
       tudo o que existe na colecção, incluindo notificações endereçadas
       a pessoas concretas — e, depois do Lote 4, de outras REDES.
    2. Toda a gente o resto era filtrada por PROCESSO, não por
       destinatário: um consultor via as notificações dirigidas ao
       mediador do mesmo processo. E `{"process_id": None}` mandava
       todas as notificações sem processo para TODA A GENTE.

  O eixo do filtro estava errado — visibilidade de processo em vez de
  destinatário — e depois isento para a gestão.

DECISÃO DO DONO
  Corta tudo o que não seja dirigido ao utilizador. Um administrador
  prefere não ver avisos de sistema avulsos a arriscar que um consultor
  leia as notificações de quem está do outro lado da parede da rede.
  O isolamento multi-tenant é superior a tudo o resto.

SEGUNDO DEFEITO, ENCONTRADO A CORRIGIR O PRIMEIRO
  `run_mark_notification_read(notification_id)` não recebia utilizador
  nenhum: com um id, qualquer pessoa marcava como lida a notificação de
  outra. O caminho WebSocket (`mark_all_read`) já filtrava por
  `user_id`; o REST não.
"""
from unittest.mock import patch

import pytest
from fastapi import HTTPException


ANA = {"id": "u-ana", "name": "Ana", "role": "consultor"}
ADMIN = {"id": "u-admin", "name": "Admin", "role": "admin"}
DIRETORA = {"id": "u-dir", "name": "Diretora", "role": "diretor"}


def _notificacoes():
    return [
        {"id": "n-ana", "user_id": "u-ana", "message": "A tua tarefa",
         "read": False, "process_id": "p-1", "created_at": "2026-09-24T10:00:00Z"},
        {"id": "n-bruno", "user_id": "u-bruno", "message": "A tarefa do Bruno",
         "read": False, "process_id": "p-1", "created_at": "2026-09-24T10:01:00Z"},
        {"id": "n-sistema", "user_id": None, "message": "Aviso de sistema",
         "read": False, "process_id": None, "created_at": "2026-09-24T10:02:00Z"},
        {"id": "n-admin", "user_id": "u-admin", "message": "Para o admin",
         "read": True, "process_id": None, "created_at": "2026-09-24T10:03:00Z"},
    ]


async def _listar(fake_db, utilizador, *, unread_only=False):
    import services.alerts_api_notifications as alertas

    fake_db.notifications.docs.extend(_notificacoes())
    with patch.object(alertas, "db", fake_db):
        return await alertas.run_get_notifications(unread_only, utilizador)


class TestSoAsDoProprio:
    @pytest.mark.asyncio
    async def test_consultor_ve_apenas_as_suas(self, fake_async_db):
        resposta = await _listar(fake_async_db, ANA)
        assert {n["id"] for n in resposta["notifications"]} == {"n-ana"}

    @pytest.mark.asyncio
    async def test_consultor_NAO_ve_as_do_colega_no_mesmo_processo(self, fake_async_db):
        """A fuga concreta: o filtro era por processo, e a Ana e o Bruno
        partilham o processo p-1."""
        resposta = await _listar(fake_async_db, ANA)
        assert "n-bruno" not in {n["id"] for n in resposta["notifications"]}

    @pytest.mark.asyncio
    async def test_ADMIN_tambem_so_ve_as_suas(self, fake_async_db):
        """O administrador deixa de ser excepção. Era esta isenção que
        lhe punha as notificações de toda a gente no sino."""
        resposta = await _listar(fake_async_db, ADMIN)
        assert {n["id"] for n in resposta["notifications"]} == {"n-admin"}

    @pytest.mark.asyncio
    async def test_diretora_tambem_nao_e_excepcao(self, fake_async_db):
        resposta = await _listar(fake_async_db, DIRETORA)
        assert resposta["notifications"] == []

    @pytest.mark.asyncio
    async def test_avisos_sem_destinatario_nao_vao_para_todos(self, fake_async_db):
        """`{"process_id": None}` fazia chover avisos de sistema em toda
        a gente. Por decisão do dono, sem destinatário = ninguém."""
        for utilizador in (ANA, ADMIN, DIRETORA):
            resposta = await _listar(fake_async_db, utilizador)
            assert "n-sistema" not in {n["id"] for n in resposta["notifications"]}


class TestContagemPorLer:
    @pytest.mark.asyncio
    async def test_a_contagem_segue_o_mesmo_ambito(self, fake_async_db):
        """Um sino com um número que não bate certo com a lista é pior do
        que um sino sem número."""
        resposta = await _listar(fake_async_db, ANA)
        assert resposta["unread"] == 1

    @pytest.mark.asyncio
    async def test_unread_only_filtra_dentro_do_ambito(self, fake_async_db):
        resposta = await _listar(fake_async_db, ADMIN, unread_only=True)
        assert resposta["notifications"] == []
        assert resposta["unread"] == 0


class TestMarcarComoLida:
    @pytest.mark.asyncio
    async def test_marca_a_propria(self, fake_async_db):
        import services.alerts_api_notifications as alertas

        fake_async_db.notifications.docs.extend(_notificacoes())
        with patch.object(alertas, "db", fake_async_db):
            await alertas.run_mark_notification_read("n-ana", ANA)

        alvo = next(n for n in fake_async_db.notifications.docs if n["id"] == "n-ana")
        assert alvo["read"] is True

    @pytest.mark.asyncio
    async def test_NAO_marca_a_de_outro(self, fake_async_db):
        """Com um id na mão, qualquer pessoa marcava a notificação de
        outra como lida — uma escrita na linha de outrem."""
        import services.alerts_api_notifications as alertas

        fake_async_db.notifications.docs.extend(_notificacoes())
        with patch.object(alertas, "db", fake_async_db):
            with pytest.raises(HTTPException) as erro:
                await alertas.run_mark_notification_read("n-bruno", ANA)

        assert erro.value.status_code == 404
        alvo = next(n for n in fake_async_db.notifications.docs if n["id"] == "n-bruno")
        assert alvo["read"] is False

    @pytest.mark.asyncio
    async def test_o_admin_tambem_nao_marca_a_de_outro(self, fake_async_db):
        import services.alerts_api_notifications as alertas

        fake_async_db.notifications.docs.extend(_notificacoes())
        with patch.object(alertas, "db", fake_async_db):
            with pytest.raises(HTTPException):
                await alertas.run_mark_notification_read("n-ana", ADMIN)


class TestGuardaDoAmbito:
    def test_o_papel_deixa_de_decidir_a_visibilidade(self):
        """Guarda sobre o código-fonte: o ramo `if role not in [ADMIN,
        CEO, DIRETOR]` era a isenção. Se voltar, volta a fuga."""
        from pathlib import Path

        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = (
            Path(__file__).resolve().parents[2]
            / "services" / "alerts_api_notifications.py"
        ).read_text("utf-8")
        codigo = codigo_sem_comentarios(fonte)
        assert "UserRole.ADMIN" not in codigo, (
            "a visibilidade das notificações voltou a depender do cargo"
        )

    def test_a_consulta_filtra_mesmo_por_destinatario(self):
        """Contraprova: sem isto, apagar o filtro satisfazia o guarda."""
        from pathlib import Path

        fonte = (
            Path(__file__).resolve().parents[2]
            / "services" / "alerts_api_notifications.py"
        ).read_text("utf-8")
        assert '"user_id"' in fonte
