"""
====================================================================
ROTAS WEBSOCKET - CREDITOIMO
====================================================================
Endpoints WebSocket para comunicação em tempo real.
====================================================================
"""

import json
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
import jwt  # CORREÇÃO: Usar PyJWT

from config import JWT_SECRET, JWT_ALGORITHM
from database import db
from services.websocket_manager import manager, WSEventType, create_ws_message

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


async def verify_websocket_token(token: str) -> dict:
    """Verificar token JWT para ligação WebSocket."""
    try:
        # CORREÇÃO: Usar a função decode do PyJWT
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        
        if not user_id:
            return None
        
        user = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
        
        if not user or user.get("is_active") == False:
            return None
        
        return user
    except jwt.ExpiredSignatureError:
        # Token expirado — comportamento esperado, usar warning em vez de error
        logger.warning(f"JWT WebSocket: Token expirado (Signature has expired)")
        return "expired"
    except jwt.PyJWTError as e:
        # Outros erros JWT (token malformado, assinatura inválida, etc.)
        logger.error(f"JWT WebSocket: Token inválido — {e}")
        return "invalid"
    except Exception as e:
        logger.error(f"JWT WebSocket: Erro inesperado — {type(e).__name__}: {e}")
        return None


def is_disconnect_error(error: Exception) -> bool:
    """Verifica se o erro indica desconexão do cliente."""
    error_str = str(error).lower()
    error_type = type(error).__name__
    
    disconnect_indicators = [
        "disconnect",
        "closed",
        "connection reset",
        "broken pipe",
        "cannot call receive",
    ]
    
    # Verificar por string
    for indicator in disconnect_indicators:
        if indicator in error_str:
            return True
    
    # Verificar por tipo de erro
    if error_type in ["WebSocketDisconnect", "ConnectionClosed", "RuntimeError"]:
        return True
    
    return False


@router.websocket("/ws/notifications")
async def websocket_notifications(
    websocket: WebSocket,
    token: str = Query(...)
):
    """Endpoint WebSocket para receber notificações em tempo real.

    Este endpoint estabelece uma ligação WebSocket persistente que
    envia notificações ao utilizador conforme eventos ocorrem:
    - Novos processos, alterações de status, atribuições.
    - Atualizações de tarefas e comentários.

    O token JWT é validado no handshake. Se expirado, fecha com
    código 4001 para o frontend fazer refresh do token.

    Args:
        websocket: Instância WebSocket do FastAPI.
        token: Token JWT para autenticação.

    Returns:
        None (stream contínuo de mensagens JSON via WebSocket).
    """
    user = await verify_websocket_token(token)
    
    # Token expirado — código 4001 para o frontend saber que deve fazer refresh
    if user == "expired":
        await websocket.close(code=4001, reason="Token expirado")
        return
    
    # Token inválido — código 4002, sem possibilidade de refresh
    if user == "invalid" or user is None:
        await websocket.close(code=4002, reason="Token inválido")
        return
    
    user_id = user["id"]
    connected = True  # Flag para controlar o loop
    
    try:
        await manager.connect(websocket, user_id)
        
        await websocket.send_json(create_ws_message(
            WSEventType.CONNECTION_STATUS,
            {
                "status": "connected",
                "user_id": user_id,
                "user_name": user.get("name", ""),
                "connected_users": len(manager.get_connected_users())
            }
        ))
        
        if user.get("role") in ["admin", "ceo"]:
            await manager.broadcast(
                create_ws_message(
                    WSEventType.USER_ONLINE,
                    {"user_id": user_id, "user_name": user.get("name", "")}
                ),
                exclude_user=user_id
            )
        
        while connected:
            try:
                # Usar receive() para podermos verificar o tipo de mensagem
                message = await websocket.receive()
                
                # Verificar se é uma mensagem de desconexão
                if message.get("type") == "websocket.disconnect":
                    logger.debug(f"Cliente {user_id} desconectou normalmente")
                    connected = False
                    break
                
                # Verificar se é uma mensagem de texto
                if message.get("type") == "websocket.receive":
                    text = message.get("text")
                    if text:
                        try:
                            data = json.loads(text)
                        except json.JSONDecodeError:
                            logger.warning(f"JSON inválido de {user_id}")
                            continue
                    else:
                        continue
                else:
                    # Outro tipo de mensagem (bytes, etc.)
                    continue
                
                msg_type = data.get("type")
                
                if msg_type == "ping":
                    try:
                        await websocket.send_json(create_ws_message(
                            WSEventType.HEARTBEAT,
                            {"status": "pong"}
                        ))
                    except Exception:
                        connected = False
                        break
                
                elif msg_type == "mark_notification_read":
                    notification_id = data.get("notification_id")
                    if notification_id:
                        await db.notifications.update_one(
                            {"id": notification_id, "user_id": user_id},
                            {"$set": {"read": True}}
                        )
                        try:
                            await websocket.send_json(create_ws_message(
                                WSEventType.NOTIFICATION_READ,
                                {"notification_id": notification_id}
                            ))
                        except Exception:
                            connected = False
                            break
                
                elif msg_type == "mark_all_read":
                    await db.notifications.update_many(
                        {"user_id": user_id, "read": False},
                        {"$set": {"read": True}}
                    )
                    try:
                        await websocket.send_json(create_ws_message(
                            WSEventType.ALL_NOTIFICATIONS_READ,
                            {"status": "success"}
                        ))
                    except Exception:
                        connected = False
                        break
                
                elif data.get("type") == "process_locked":
                    # Broadcast lock event to other users
                    lock_message = create_ws_message(
                        WSEventType.PROCESS_LOCKED,
                        {
                            "process_id": data.get("process_id"),
                            "user_id": str(user.get("id", "")),
                            "user_name": user.get("name", "Unknown"),
                        }
                    )
                    await manager.broadcast(lock_message, exclude_user=str(user.get("id", "")))

                elif data.get("type") == "process_unlocked":
                    # Broadcast unlock event to other users
                    unlock_message = create_ws_message(
                        WSEventType.PROCESS_UNLOCKED,
                        {
                            "process_id": data.get("process_id"),
                            "user_id": str(user.get("id", "")),
                            "user_name": user.get("name", "Unknown"),
                        }
                    )
                    await manager.broadcast(unlock_message, exclude_user=str(user.get("id", "")))
                
            except WebSocketDisconnect:
                logger.debug(f"WebSocketDisconnect: {user_id}")
                connected = False
                break
            
            except RuntimeError as e:
                # Erro específico: "Cannot call receive once a disconnect message has been received"
                if is_disconnect_error(e):
                    logger.debug(f"Conexão fechada (RuntimeError): {user_id}")
                    connected = False
                    break
                # Outros RuntimeErrors - registar e continuar
                logger.warning(f"RuntimeError inesperado WebSocket {user_id}: {e}")
                connected = False
                break
            
            except Exception as e:
                if is_disconnect_error(e):
                    logger.debug(f"Conexão fechada: {user_id}")
                    connected = False
                    break
                # Logar outros erros mas NÃO continuar o loop para evitar spam
                logger.warning(f"Erro WebSocket {user_id}: {type(e).__name__}: {e}")
                connected = False
                break
    
    except WebSocketDisconnect:
        logger.debug(f"WebSocket desconectado (outer): {user_id}")
    
    except Exception as e:
        # Só registar se não for erro de desconexão
        if not is_disconnect_error(e):
            logger.error(f"Erro WebSocket (outer) {user_id}: {type(e).__name__}: {e}")
    
    finally:
        # Sempre limpar a ligação
        manager.disconnect(websocket)
        
        # Notificar outros utilizadores se for admin/ceo
        if user.get("role") in ["admin", "ceo"]:
            try:
                await manager.broadcast(
                    create_ws_message(
                        WSEventType.USER_OFFLINE,
                        {"user_id": user_id, "user_name": user.get("name", "")}
                    ),
                    exclude_user=user_id
                )
            except Exception:
                pass  # Ignorar erros ao notificar


@router.get("/ws/status")
async def websocket_status():
    """Retorna o estado atual das ligações WebSocket ativas.

    Usado pelo frontend para verificar se o servidor de WebSocket
    está a funcionar e quantos utilizadores estão ligados.

    Returns:
        dict: total_connections, connected_users, user_ids.
    """
    return {
        "total_connections": manager.get_total_connections(),
        "connected_users": len(manager.get_connected_users()),
        "user_ids": manager.get_connected_users()
    }
