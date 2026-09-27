"""A Parede no Envelope, ao nível do transporte (Épico 10, Fases 1 e 2).

O `route_system_event` já entregava SÓ ao `user_id` do envelope e descartava
quem não o tivesse — uma garantia forte, mas que só servia eventos de um
destinatário. Um delta de processo tem audiência, não destinatário: enumerá-la
custaria a query por evento que o desenho evita.

Este ficheiro cobre o alargamento dessa invariante, que é o ponto mais
perigoso de todo o Épico:

    antes:  entregável  ⇔  user_id
    agora:  entregável  ⇔  user_id  OU  audiência        (nunca nenhum)

e o encaminhamento por audiência, que decide em memória contra o
``TenantScope`` que cada ligação trouxe do handshake.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.auth import UserRoleEnum as UserRole
from services.realtime_audience import Audiencia
from services.redis_pubsub import build_event_envelope, is_deliverable
from services.tenant_network import TenantScope

REDE_POWER = "grupo_power_precision"
REDE_DOMUS = "domus"

AUD_POWER = Audiencia(network_id=REDE_POWER, company_id="cmp-power")
AUD_DOMUS = Audiencia(network_id=REDE_DOMUS, company_id="cmp-domus")

ESCOPO_POWER = TenantScope(network_ids=(REDE_POWER,), company_ids=("cmp-power",))
ESCOPO_DOMUS = TenantScope(network_ids=(REDE_DOMUS,), company_ids=("cmp-domus",))


class TestInvarianteDoEnvelope:
    """Alargar a regra sem a furar: ou destinatário, ou audiência."""

    def test_envelope_com_destinatario_continua_entregavel(self):
        assert is_deliverable(build_event_envelope("task_progress", {}, user_id="u1"))

    def test_envelope_com_audiencia_e_entregavel_sem_user_id(self):
        env = build_event_envelope(
            "process_moved", {}, user_id=None, audiencia=AUD_POWER
        )
        assert is_deliverable(env)

    def test_envelope_sem_destinatario_e_sem_audiencia_e_descartado(self):
        """A garantia de sempre: nada de fan-out por omissão de campo."""
        assert not is_deliverable({"type": "process_moved", "payload": {}})
        assert not is_deliverable(
            build_event_envelope("process_moved", {}, user_id=None)
        )

    def test_audiencia_vazia_nao_torna_o_envelope_entregavel(self):
        """Uma audiência que não alcança ninguém não é um passe livre.

        Se `Audiencia()` bastasse para passar o `is_deliverable`, bastaria
        um emissor esquecer-se de a preencher para reabrir o broadcast —
        exactamente o defeito que este Épico fecha.
        """
        env = build_event_envelope(
            "process_moved", {}, user_id=None, audiencia=Audiencia()
        )
        assert not is_deliverable(env)

    def test_audiencia_sobrevive_a_serializacao(self):
        from services.redis_pubsub import parse_envelope, serialize_envelope

        env = build_event_envelope(
            "process_moved", {"process_id": "p1"}, user_id=None, audiencia=AUD_POWER
        )
        volta = parse_envelope(serialize_envelope(env))
        assert Audiencia.do_envelope(volta["audience"]) == AUD_POWER


class TestEncaminhamentoPorAudiencia:
    """O worker decide em memória, contra o âmbito de cada ligação."""

    @pytest.fixture
    def manager_espiao(self):
        from services import websocket_manager

        espiao = MagicMock()
        espiao.send_personal_message = AsyncMock()
        espiao.is_user_connected = MagicMock(return_value=True)
        with patch.object(websocket_manager, "manager", espiao):
            yield espiao

    def _ligados(self, espiao, ligacoes):
        """ligacoes: {user_id: (scope, role)}"""
        espiao.get_connected_users = MagicMock(return_value=list(ligacoes))
        espiao.get_scope = MagicMock(side_effect=lambda uid: ligacoes.get(uid))

    async def test_entrega_a_quem_esta_na_rede(self, manager_espiao):
        from services.websocket_manager import route_system_event

        self._ligados(manager_espiao, {
            "u-power": (ESCOPO_POWER, UserRole.ADMIN),
        })
        env = build_event_envelope(
            "process_moved", {"process_id": "p1"}, user_id=None, audiencia=AUD_POWER
        )
        assert await route_system_event(env) is True
        assert manager_espiao.send_personal_message.await_args.args[1] == "u-power"

    async def test_a_domus_nao_recebe_um_evento_da_power(self, manager_espiao):
        """A fuga que motivou o Épico 10, no ponto onde é decidida."""
        from services.websocket_manager import route_system_event

        self._ligados(manager_espiao, {
            "u-domus": (ESCOPO_DOMUS, UserRole.ADMIN),
        })
        env = build_event_envelope(
            "process_moved",
            {"process_id": "p1", "client_name": "Maria Silva"},
            user_id=None,
            audiencia=AUD_POWER,
        )
        assert await route_system_event(env) is False
        manager_espiao.send_personal_message.assert_not_awaited()

    async def test_separa_os_ligados_no_mesmo_worker(self, manager_espiao):
        """O caso real: dois inquilinos no mesmo processo uvicorn."""
        from services.websocket_manager import route_system_event

        self._ligados(manager_espiao, {
            "u-power": (ESCOPO_POWER, UserRole.CEO),
            "u-domus": (ESCOPO_DOMUS, UserRole.CEO),
        })
        env = build_event_envelope(
            "process_moved", {}, user_id=None, audiencia=AUD_POWER
        )
        await route_system_event(env)

        destinatarios = [
            c.args[1] for c in manager_espiao.send_personal_message.await_args_list
        ]
        assert destinatarios == ["u-power"]

    async def test_ligacao_sem_ambito_conhecido_nao_recebe(self, manager_espiao):
        """Falha fechada: sem âmbito resolvido, não se adivinha."""
        from services.websocket_manager import route_system_event

        manager_espiao.get_connected_users = MagicMock(return_value=["u-misterio"])
        manager_espiao.get_scope = MagicMock(return_value=None)

        env = build_event_envelope(
            "process_moved", {}, user_id=None, audiencia=AUD_POWER
        )
        assert await route_system_event(env) is False
        manager_espiao.send_personal_message.assert_not_awaited()

    async def test_respeita_a_necessidade_de_saber(self, manager_espiao):
        """Mesma rede, carteiras diferentes: só o atribuído recebe."""
        from services.websocket_manager import route_system_event

        self._ligados(manager_espiao, {
            "u1": (ESCOPO_POWER, UserRole.CONSULTOR),
            "u2": (ESCOPO_POWER, UserRole.CONSULTOR),
        })
        env = build_event_envelope(
            "process_moved",
            {},
            user_id=None,
            audiencia=Audiencia(network_id=REDE_POWER, consultor_ids=("u1",)),
        )
        await route_system_event(env)

        destinatarios = [
            c.args[1] for c in manager_espiao.send_personal_message.await_args_list
        ]
        assert destinatarios == ["u1"]

    async def test_o_envelope_dirigido_nunca_passa_pela_audiencia(self, manager_espiao):
        """Um envelope com user_id mantém o caminho antigo, intacto."""
        from services.websocket_manager import route_system_event

        manager_espiao.get_connected_users = MagicMock(
            side_effect=AssertionError("caminho errado: tinha destinatário")
        )
        env = build_event_envelope("task_progress", {}, user_id="u1")
        assert await route_system_event(env) is True

    async def test_uma_entrega_que_rebenta_nao_impede_as_outras(self, manager_espiao):
        from services.websocket_manager import route_system_event

        self._ligados(manager_espiao, {
            "mau": (ESCOPO_POWER, UserRole.CEO),
            "bom": (ESCOPO_POWER, UserRole.CEO),
        })

        async def falha_no_mau(mensagem, uid):
            if uid == "mau":
                raise RuntimeError("socket morto")

        manager_espiao.send_personal_message = AsyncMock(side_effect=falha_no_mau)
        env = build_event_envelope(
            "process_moved", {}, user_id=None, audiencia=AUD_POWER
        )
        assert await route_system_event(env) is True


class TestAmbitoNaLigacao:
    """O âmbito resolve-se UMA vez, no handshake — não por evento."""

    def test_manager_guarda_e_devolve_o_ambito(self):
        from services.websocket_manager import ConnectionManager

        m = ConnectionManager()
        m.register_scope("u1", ESCOPO_POWER, role=UserRole.CONSULTOR)
        scope, role = m.get_scope("u1")
        assert scope == ESCOPO_POWER
        assert role == UserRole.CONSULTOR

    def test_ambito_desconhecido_devolve_none(self):
        from services.websocket_manager import ConnectionManager

        assert ConnectionManager().get_scope("ninguem") is None

    def test_o_ambito_sai_com_a_ultima_ligacao(self):
        """Senão um âmbito antigo sobrevive à saída e decide por um socket
        que já não existe — ou pior, por outro que reutilize o id."""
        from services.websocket_manager import ConnectionManager

        m = ConnectionManager()
        ws = MagicMock()
        m.active_connections["u1"] = {ws}
        m.websocket_to_user[ws] = "u1"
        m.register_scope("u1", ESCOPO_POWER, role=UserRole.CEO)

        m.disconnect(ws)
        assert m.get_scope("u1") is None


class TestExclusaoNaSala:
    """M12: a exclusão do autor não estava afirmada em lado nenhum."""

    @pytest.fixture
    def manager_espiao(self):
        from services import websocket_manager

        espiao = MagicMock()
        espiao.send_personal_message = AsyncMock()
        espiao.get_room_members = MagicMock(return_value=["autor", "colega"])
        with patch.object(websocket_manager, "manager", espiao):
            yield espiao

    async def test_o_autor_nao_recebe_a_sua_propria_mensagem(self, manager_espiao):
        """Quem escreveu já tem a mensagem no ecrã; devolvê-la duplica-a."""
        from services.redis_pubsub import build_event_envelope
        from services.websocket_manager import route_system_event

        env = build_event_envelope(
            "portal_message", {"content": "olá"},
            room="process_p1", exclude_user_id="autor",
        )
        assert await route_system_event(env) is True

        destinatarios = [
            c.args[1] for c in manager_espiao.send_personal_message.await_args_list
        ]
        assert destinatarios == ["colega"]

    async def test_sem_exclusao_todos_os_membros_recebem(self, manager_espiao):
        """Contraprova: a exclusão só acontece quando é pedida."""
        from services.redis_pubsub import build_event_envelope
        from services.websocket_manager import route_system_event

        env = build_event_envelope("portal_message", {}, room="process_p1")
        await route_system_event(env)

        destinatarios = [
            c.args[1] for c in manager_espiao.send_personal_message.await_args_list
        ]
        assert destinatarios == ["autor", "colega"]
