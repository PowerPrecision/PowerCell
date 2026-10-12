"""
====================================================================
ALERTA AO MASTER — uma acção destrutiva de um perfil LOCAL
====================================================================
O Master é o único perfil global (`role_scope`). Quando um Admin ou CEO de uma
rede executa uma acção que não se desfaz (hoje: «Repor ao Modelo» do workflow e
do formulário), o Master tem de saber — QUEM a fez e EM QUE REDE — sem ir ler o
`audit_logs`. Isto COMPLEMENTA o rasto de auditoria, não o substitui.

AS REGRAS
  1. **Só o Master recebe.** Os destinatários saem do cargo da CONTA
     (`role` ∈ `PAPEIS_GLOBAIS`), activos. O Admin/CEO da própria rede, o
     autor e qualquer outro perfil nunca são destinatários — a mensagem diz
     quem mexeu em que rede e não é para a gestão local.
  2. **Só alerta quando o autor trabalha como perfil LOCAL.** Um Master a
     trabalhar como Master não se avisa a si próprio; se é um Master a vestir
     o chapéu de Admin, os OUTROS Master recebem (o autor fica de fora).
  3. **Um documento de notificação por destinatário** (a colecção filtra por
     `user_id`; um aviso sem destinatário é invisível a toda a gente) + email
     urgente em segundo plano (nunca bloqueia o pedido).
  4. **Nunca propaga:** o alerta observa a operação, não a condiciona. Uma
     falha regista-se com `warning` e a acção segue.
  5. **Nada sensível:** o texto leva o nome e o email do autor, o nome da rede
     e das empresas, e o que foi reposto — nunca a password nem a configuração
     descartada.
====================================================================
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from database import db
from services.background_tasks import spawn_background_task
from services.role_scope import PAPEIS_GLOBAIS, papel_concreto_do_utilizador, utilizador_e_global
from services.tenant_network import CAMPO_REDE

logger = logging.getLogger(__name__)

TIPO_DE_ALERTA = "destructive_action_alert"

ACCOES = {
    "workflow_reposto_ao_modelo": "repôs o WORKFLOW ao modelo",
    "formulario_reposto_ao_modelo": "repôs o FORMULÁRIO PÚBLICO ao modelo",
}


async def _master_destinatarios(excluir_id: Optional[str]) -> list[dict]:
    consulta: dict[str, Any] = {"role": {"$in": sorted(PAPEIS_GLOBAIS)}, "is_active": {"$ne": False}}
    if excluir_id:
        consulta["id"] = {"$ne": excluir_id}
    docs = await db.users.find(consulta, {"_id": 0, "id": 1, "email": 1, "name": 1}).to_list(50)
    return [d for d in docs if d.get("id")]


async def _empresas_da_rede(rede: str) -> list[str]:
    try:
        docs = await db.companies.find({CAMPO_REDE: rede}, {"_id": 0, "name": 1}).to_list(50)
    except Exception:  # noqa: BLE001 — o nome é conforto, não é condição
        return []
    return sorted(d["name"] for d in docs if d.get("name"))


def _texto_do_alerta(user: dict, acao: str, rede: str, empresas: list[str], detalhes: dict) -> tuple[str, str]:
    quem = user.get("name") or user.get("email") or user.get("id") or "Utilizador desconhecido"
    contacto = f" ({user['email']})" if user.get("email") and user.get("name") else ""
    papel = papel_concreto_do_utilizador(user) or "?"
    onde = f"{rede}" + (f" — {', '.join(empresas)}" if empresas else "")
    verbo = ACCOES.get(acao, acao)
    # O título é o que o sino mostra: tem de dizer QUEM e EM QUE REDE sem abrir mais nada.
    titulo = f"Acção destrutiva: {quem} {verbo} (rede «{rede}»)"
    corpo = (
        f"{quem}{contacto}, a trabalhar como {papel}, {verbo} da rede «{onde}».\n"
        + (f"Fases removidas: {detalhes['fases_removidas']}.\n" if "fases_removidas" in detalhes else "")
        + "A rede passa a usar o modelo global; a configuração própria foi descartada.\n"
        "O rasto completo está no registo de auditoria."
    )
    return titulo, corpo


async def _enviar_emails(destinatarios: list[dict], titulo: str, corpo: str) -> None:
    from services.notification_service import send_notification_with_preference_check

    for d in destinatarios:
        if not d.get("email"):
            continue
        try:
            await send_notification_with_preference_check(
                d["email"], titulo, corpo, notification_type="urgent", is_urgent=True,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[ALERTA_MASTER] Email para %s falhou: %s", d.get("id"), exc)


async def alertar_masters(user: dict, acao: str, rede: str, detalhes: Optional[dict] = None) -> int:
    """Avisa os Master de que um perfil LOCAL executou `acao` na `rede`. Devolve quantos avisou."""
    detalhes = detalhes or {}
    try:
        if utilizador_e_global(user):
            return 0
        destinatarios = await _master_destinatarios(user.get("id"))
        if not destinatarios:
            logger.warning(
                "[ALERTA_MASTER] %s na rede %s por %s: não há nenhum Master activo a avisar.",
                acao, rede, user.get("id"),
            )
            return 0
        empresas = await _empresas_da_rede(rede)
        titulo, corpo = _texto_do_alerta(user, acao, rede, empresas, detalhes)
        agora = datetime.now(timezone.utc).isoformat()
        await db.notifications.insert_many([
            {
                "id": str(uuid.uuid4()),
                "user_id": d["id"],
                "type": TIPO_DE_ALERTA,
                "message": titulo,
                "details": corpo,
                "action": acao,
                "network_id": rede,
                "actor_id": user.get("id"),
                "actor_name": user.get("name"),
                "actor_role": papel_concreto_do_utilizador(user),
                "read": False,
                "created_at": agora,
            }
            for d in destinatarios
        ])
        spawn_background_task(_enviar_emails(destinatarios, titulo, corpo), name="alerta_ao_master_emails")
        return len(destinatarios)
    except Exception as exc:  # noqa: BLE001 — observa, não condiciona
        logger.warning("[ALERTA_MASTER] Falha a alertar os Master (%s, rede %s): %s", acao, rede, exc)
        return 0


__all__ = ["ACCOES", "TIPO_DE_ALERTA", "alertar_masters"]
