"""WebSocket do CLIENTE do Portal — `/ws/portal`.

PORQUE É UM ENDPOINT SEPARADO E NÃO UM RAMO DO `/ws/notifications`
==================================================================
O laço do staff trata `mark_notification_read`, `mark_all_read`,
`process_locked`, `process_unlocked`, `join_process_room` e
`leave_process_room`. Meter um cliente externo nesse laço obrigava a semear
`if é_cliente:` por cada ramo — e a segurança passava a depender de **nenhum
ramo novo se esquecer da guarda**.

Aqui o laço do cliente aceita **uma** mensagem: `ping`. Tudo o mais é
ignorado. Não há ramo que esquecer porque não há ramos.

AS QUATRO REGRAS DESTA LIGAÇÃO
==============================
1. **`type` autoritativo.** Só os três tipos do `portal_security` entram
   (`verify_portal_websocket_token`). Um token de staff é recusado aqui, e um
   token de Portal é recusado no `/ws/notifications` — a separação é afirmada
   dos DOIS lados, e deixou de ser a coincidência de o `sub` de um token de
   Portal ser um `process_id` que não existe em `db.users`.

2. **Nunca `register_scope`.** Um cliente não tem UCRs, e o
   `resolve_tenant_scope` daria a um utilizador sem empresa a **rede de
   omissão** — a do grupo incumbente. Todos os eventos encaminhados por
   audiência (`entregar_a_processo`, `entregar_as_redes`) casam por
   `network_id`: um socket de cliente com âmbito receberia os deltas de
   processo de toda a rede, com nomes de clientes e números de processo.
   Sem âmbito, o `_route_por_audiencia` salta-o (`if not registo: continue`) —
   a exclusão é estrutural, não uma verificação que alguém tenha de lembrar.

3. **A sala é DITADA pelo servidor.** O `sub` do token *é* o `process_id`; a
   sala é calculada aqui, na ligação. Uma mensagem `join_process_room` enviada
   pelo cliente é ignorada e registada — um cliente não pede salas, recebe a
   sua.

4. **Presença com namespace.** A identidade do socket é
   `cliente:<process_id>` (`ws_client_identity`), pelo que o ZSET de presença
   não mistura clientes com consultores no "quem está online" interno.

E O QUE CHEGA AO SOCKET É UMA LISTA DE PERMISSÃO
================================================
Estar na sala não é ter direito a tudo o que a sala transporta: a barreira
está na ENTREGA (`websocket_manager._route_por_sala` →
`ws_client_identity.pode_entregar`). Ver esse módulo para o porquê de ser na
entrega e não na emissão.
"""
from __future__ import annotations

import json
import logging

from fastapi import WebSocket, WebSocketDisconnect

from services.websocket_manager import manager, WSEventType, create_ws_message
from services.realtime_delivery import sala_do_processo
from services.websocket_api_helpers import (
    verify_portal_websocket_token,
    is_disconnect_error,
)
from services.ws_client_identity import identidade_de_socket_do_cliente

logger = logging.getLogger(__name__)


async def _processo_do_socket_ficou_inativo(process_id: str) -> bool:
    """Releitura barata do processo; um erro de leitura NÃO fecha o socket."""
    from database import db
    from services.portal_estado import processo_esta_inativo

    try:
        processo = await db.processes.find_one(
            {"id": process_id}, {"_id": 0, "id": 1, "status": 1, "is_deleted": 1},
        )
        if processo and processo.get("is_deleted"):
            return True
        return await processo_esta_inativo(processo)
    except Exception as e:
        logger.warning("[WS-PORTAL] Releitura do processo %s falhou: %s", process_id, e)
        return False


async def run_portal_websocket(websocket: WebSocket, token: str) -> None:
    """Liga um cliente do Portal à sala do SEU processo, e a mais nada."""
    verificado = await verify_portal_websocket_token(token)

    if verificado == "expired":
        # Aceitar primeiro para o browser receber o código de fecho em vez de
        # um 403 de handshake (que reconecta para sempre como 1006) — a mesma
        # razão do laço do staff.
        await websocket.accept()
        await websocket.close(code=4001, reason="Sessão expirada")
        return

    if not isinstance(verificado, tuple):
        await websocket.accept()
        await websocket.close(code=4002, reason="Acesso inválido")
        return

    process_id, tipo_de_token = verificado
    identidade = identidade_de_socket_do_cliente(process_id)
    sala = sala_do_processo(process_id)
    ligado = True

    try:
        await manager.connect(websocket, identidade)

        # REGRA 2 — nenhum `register_scope`. Não é esquecimento: é o que
        # mantém este socket fora de todo o encaminhamento por audiência.

        from services.presenca import marcar_online

        await marcar_online(identidade)

        # REGRA 3 — a sala sai do token, no servidor.
        manager.join_room(sala, identidade)

        logger.info(
            "[WS-PORTAL] Cliente ligado ao processo %s (tipo de token: %s)",
            process_id, tipo_de_token,
        )

        await websocket.send_json(create_ws_message(
            WSEventType.CONNECTION_STATUS,
            {"status": "connected", "process_id": process_id},
        ))

        while ligado:
            try:
                mensagem = await websocket.receive()

                if mensagem.get("type") == "websocket.disconnect":
                    ligado = False
                    break

                if mensagem.get("type") != "websocket.receive":
                    continue

                texto = mensagem.get("text")
                if not texto:
                    continue

                try:
                    dados = json.loads(texto)
                except json.JSONDecodeError:
                    logger.debug("[WS-PORTAL] JSON inválido do processo %s", process_id)
                    continue

                tipo = dados.get("type")

                if tipo == "ping":
                    # Bloco 3 (ponto 14): o batimento é também o ponto onde um
                    # socket aberto descobre que o processo passou a inativo.
                    # Cobre QUALQUER escritor de fase (o gancho imediato cobre
                    # os principais; este não depende de nenhum deles).
                    if await _processo_do_socket_ficou_inativo(process_id):
                        await websocket.close(code=4002, reason="Processo inativo")
                        ligado = False
                        break

                    # O batimento renova a presença. É a ÚNICA mensagem aceite.
                    await marcar_online(identidade)
                    try:
                        await websocket.send_json(create_ws_message(
                            WSEventType.HEARTBEAT, {"status": "pong"},
                        ))
                    except Exception:
                        ligado = False
                        break
                    continue

                # Qualquer outra coisa é ignorada. Um pedido de sala é
                # registado porque, vindo de um cliente, é uma sondagem: ele
                # não tem interface que o envie.
                if tipo in ("join_process_room", "leave_process_room"):
                    logger.warning(
                        "[WS-PORTAL] Cliente do processo %s tentou '%s' "
                        "(pedido=%s) — ignorado: a sala é ditada pelo servidor.",
                        process_id, tipo, dados.get("process_id"),
                    )
                else:
                    logger.debug(
                        "[WS-PORTAL] Mensagem '%s' ignorada (processo %s)",
                        tipo, process_id,
                    )

            except WebSocketDisconnect:
                ligado = False
                break
            except Exception as e:
                if is_disconnect_error(e):
                    ligado = False
                    break
                logger.warning(
                    "[WS-PORTAL] Erro no socket do processo %s: %s: %s",
                    process_id, type(e).__name__, e,
                )
                ligado = False
                break

    except WebSocketDisconnect:
        logger.debug("[WS-PORTAL] Desligado (outer): processo %s", process_id)
    except Exception as e:
        if not is_disconnect_error(e):
            logger.error(
                "[WS-PORTAL] Erro (outer) no processo %s: %s: %s",
                process_id, type(e).__name__, e,
            )
    finally:
        # Nenhum `USER_ONLINE`/`USER_OFFLINE`: esses eventos de presença são
        # da equipa e vão para as redes do próprio — e um cliente não tem rede.
        manager.disconnect(websocket)
