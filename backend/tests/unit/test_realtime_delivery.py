"""A conduta única do tempo real (Épico 10, Fase 1).

O tempo real tinha DUAS condutas: o Redis (Épicos 4 e 5, 2 emissores) e o
`ConnectionManager` em memória (33 emissores, em 12 módulos). Com
`UVICORN_WORKERS=2`, tudo o que ia pela segunda morria quando o socket vivia
no outro processo uvicorn — sem erro nenhum, o que é pior.

Este ficheiro tem duas metades, e nenhuma vale sozinha:

* uma **guarda sobre o código-fonte**, que afirma que nenhum emissor volta a
  escrever directamente no `manager`;
* a **contraprova** ao lado, que afirma que o sítio certo entrega mesmo —
  sem ela, apagar a entrega satisfaria a guarda.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from tests.unit.helpers_fonte import codigo_sem_comentarios

SERVICES = Path(__file__).resolve().parents[2] / "services"

# Módulos que emitem eventos de tempo real e que foram migrados na Fase 1.
EMISSORES = [
    "process_broadcast.py",
    "process_kanban_move.py",
    "realtime_notifications.py",
    "chat_messages.py",
    "chat_groups.py",
    "chat_presence.py",
    "portal_client_messages.py",
    "portal_client_visits.py",
    "portal_gov_fetch.py",
    "process_portal_messages.py",
    "visit_helpers.py",
    "websocket_api_notifications.py",
]

# As formas de escrita directa no gestor em memória — a falésia.
ENTREGAS_DIRECTAS = (
    "manager.broadcast(",
    "manager.broadcast_to_room(",
    "manager.send_personal_message(",
)


class TestCondutaUnica:
    @pytest.mark.parametrize("modulo", EMISSORES)
    def test_nenhum_emissor_escreve_no_gestor_em_memoria(self, modulo):
        """Ler os comentários seria proibir a explicação do defeito.

        Vários destes ficheiros têm hoje um comentário a dizer
        "isto era um `manager.broadcast()`" — é a explicação que impede que
        alguém reverta a migração por distracção. Uma guarda que lesse os
        comentários tornava essa explicação vermelha, e a saída óbvia
        seria apagá-la.
        """
        fonte = codigo_sem_comentarios((SERVICES / modulo).read_text(encoding="utf-8"))
        for forma in ENTREGAS_DIRECTAS:
            assert forma not in fonte, (
                f"{modulo} voltou a entregar em memória por '{forma}' — "
                "com 2 workers, metade destes eventos não chega a ninguém. "
                "Usar `services/realtime_delivery.py`."
            )

    def test_a_guarda_apanharia_uma_reversao(self):
        """Contraprova da guarda: ela reprova mesmo o padrão que proíbe."""
        fonte = codigo_sem_comentarios(
            'async def emitir():\n    await manager.broadcast(msg)\n'
        )
        assert any(forma in fonte for forma in ENTREGAS_DIRECTAS)

    @pytest.mark.parametrize("modulo", EMISSORES)
    def test_cada_emissor_usa_mesmo_a_conduta(self, modulo):
        """Contraprova: apagar a entrega satisfaria a guarda acima."""
        fonte = codigo_sem_comentarios((SERVICES / modulo).read_text(encoding="utf-8"))
        assert "realtime_delivery" in fonte, (
            f"{modulo} não importa a conduta única — uma guarda satisfeita "
            "por ausência de entrega não prova nada."
        )


class TestAConditaEntregaMesmo:
    """A outra metade: as funções publicam o que dizem publicar."""

    @pytest.fixture
    def publicacoes(self):
        from services import realtime_delivery

        espiao = AsyncMock(return_value=True)
        with patch.object(realtime_delivery, "publish_event", espiao):
            yield espiao

    async def test_entrega_dirigida_leva_destinatario(self, publicacoes):
        from services.realtime_delivery import entregar_a_utilizador

        await entregar_a_utilizador("u1", "new_notification", {"a": 1})
        assert publicacoes.await_args.kwargs["user_id"] == "u1"

    async def test_entrega_sem_destinatario_nao_publica(self, publicacoes):
        from services.realtime_delivery import entregar_a_utilizador

        assert await entregar_a_utilizador("", "new_notification", {}) is False
        publicacoes.assert_not_awaited()

    async def test_entrega_a_processo_deriva_a_audiencia_do_documento(
        self, publicacoes
    ):
        from services.realtime_delivery import entregar_a_processo

        await entregar_a_processo(
            {"network_id": "rede-a", "company_id": "cmp-a"},
            "process_moved",
            {"process_id": "p1"},
        )
        audiencia = publicacoes.await_args.kwargs["audiencia"]
        assert audiencia.network_id == "rede-a"
        assert publicacoes.await_args.kwargs.get("user_id") is None

    async def test_entrega_a_processo_nao_faz_I_O(self):
        """O custo do desenho: uma query por evento mataria a ideia toda."""
        from services import realtime_delivery

        with patch.object(
            realtime_delivery, "publish_event", AsyncMock(return_value=True)
        ):
            with patch("database.db") as bd:
                await realtime_delivery.entregar_a_processo(
                    {"network_id": "r"}, "process_updated", {}
                )
                assert not bd.method_calls

    async def test_sala_leva_sala_e_exclusao(self, publicacoes):
        from services.realtime_delivery import entregar_na_sala

        await entregar_na_sala("process_p1", "portal_message", {}, exclude_user_id="u9")
        assert publicacoes.await_args.kwargs["room"] == "process_p1"
        assert publicacoes.await_args.kwargs["exclude_user_id"] == "u9"

    async def test_presenca_sem_rede_nao_emite_nada(self, publicacoes):
        """Falha fechada: um evento de presença sem fronteira seria o
        broadcast que este Épico fechou."""
        from services.realtime_delivery import entregar_as_redes
        from services.tenant_network import TenantScope

        assert await entregar_as_redes(TenantScope(), "user_online", {}) is False
        assert await entregar_as_redes(None, "user_online", {}) is False
        publicacoes.assert_not_awaited()

    async def test_presenca_emite_uma_por_rede(self, publicacoes):
        from services.realtime_delivery import entregar_as_redes
        from services.tenant_network import TenantScope

        await entregar_as_redes(
            TenantScope(network_ids=("r1", "r2")), "user_online", {}
        )
        redes = [
            c.kwargs["audiencia"].network_id for c in publicacoes.await_args_list
        ]
        assert redes == ["r1", "r2"]
