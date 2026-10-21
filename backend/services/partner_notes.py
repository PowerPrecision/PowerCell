"""PORTAL DO PARCEIRO — o parceiro escreve notas no seu processo (Out 2026).

O parceiro é um interveniente activo: lê as notas da equipa (`partner_visibility.notas_da_equipa`) e
escreve as suas. A nota entra no MESMO feed `observation_notes` do cartão «Observações» do CRM, para a
equipa a ler onde já lê tudo, marcada com a origem (`origem: "parceiro"`) e o parceiro que a escreveu.

PORQUE NÃO É `POST /processes/{id}/notes`
  Os planos de identidade são separados de propósito (JWT próprio, segredo próprio): o
  `get_current_user` do staff recusa um token de parceiro e o inverso. Abrir a rota do staff ao parceiro
  seria misturar os dois planos. O pedido entra pelo plano do parceiro (`POST /partner/cases/{id}/notes`)
  e chega ao processo pelo ÚNICO caminho de leitura dele (`resolver_caso`: relação ∧ rede activa, 404
  igual para alheio e inexistente).

REGRAS
  * Só num PROCESSO: uma lead ainda não tem equipa a ler (as observações da lead vão na submissão).
  * Um processo FECHADO não aceita notas (a mesma regra do resto do sistema: reabre-se primeiro).
  * O carimbo vem sempre do servidor: autor, origem e data. O corpo é `extra="forbid"`.
  * Texto simples: sem HTML, sem caracteres de controlo; o ecrã mostra-o como texto.
  * Não mexe nos escalares `observations`/`notes` (que são "a nota do consultor" na listagem).
  * Nunca é lido o `user_id` do parceiro como se fosse de um utilizador: a nota leva `user_id: None`.
  * Os efeitos (histórico, aviso à equipa) nunca fazem falhar a nota, que já está gravada.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from database import db
from services.partner_portal_read import resolver_caso
from services.partner_visibility import MAX_CARACTERES_DA_NOTA
from services.process_closed_guard import processo_esta_fechado
from services.process_observation_notes import append_observation_note

logger = logging.getLogger(__name__)

ORIGEM_PARCEIRO = "parceiro"
#: Tecto do feed (todas as origens): o parceiro não pode encher o processo de notas.
MAX_NOTAS_NO_PROCESSO = 500
TENTATIVAS_DA_ESCRITA = 3

ERRO_SO_NUM_PROCESSO = (
    "Só pode escrever notas num processo. Enquanto o caso for uma lead, use as observações da submissão."
)
ERRO_PROCESSO_FECHADO = "Este processo está fechado — já não aceita notas."
ERRO_NOTA_VAZIA = "Escreva a nota."
ERRO_FEED_CHEIO = "Este processo já tem o número máximo de notas."
ERRO_CONCORRENCIA = "A nota não foi gravada porque o processo mudou entretanto. Tente de novo."

_CONTROLO = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HTML = re.compile(r"<[^>]*>")


class PartnerNoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(..., min_length=1, max_length=MAX_CARACTERES_DA_NOTA)


def limpar_texto_da_nota(texto: Any) -> str:
    """Texto simples: sem etiquetas HTML, sem controlo; mantém quebras de linha (no máximo 2 seguidas)."""
    if not isinstance(texto, str):
        return ""
    limpo = _CONTROLO.sub("", texto.replace("\r\n", "\n").replace("\r", "\n"))
    limpo = _HTML.sub("", limpo)
    limpo = re.sub(r"\n{3,}", "\n\n", limpo)
    return limpo.strip()


def construir_nota_do_parceiro(texto: str, partner: dict, *, agora: Optional[str] = None) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "text": texto,
        "created_at": agora or datetime.now(timezone.utc).isoformat(),
        # O parceiro NÃO é um utilizador: nunca se escreve o id dele onde o CRM espera um `users.id`.
        "user_id": None,
        "user_name": str(partner.get("name") or "Parceiro").strip() or "Parceiro",
        "origem": ORIGEM_PARCEIRO,
        "partner_id": partner["id"],
    }


def dto_da_nota(nota: dict, partner_id: str) -> dict:
    return {
        "id": nota["id"],
        "text": nota["text"],
        "created_at": nota["created_at"],
        "author_name": nota["user_name"],
        "do_parceiro": True,
        "e_minha": nota.get("partner_id") == partner_id,
    }


async def _gravar(process_id: str, processo: dict, nota: dict) -> bool:
    """Acrescenta a nota ao feed com escrita OPTIMISTA: só grava se o feed não mudou desde a leitura."""
    anterior = processo.get("observation_notes")
    novo_feed = append_observation_note(processo, nota)
    filtro: dict[str, Any] = {"id": process_id}
    filtro["observation_notes"] = anterior if isinstance(anterior, list) else {"$in": [None]}
    resultado = await db.processes.update_one(
        filtro, {"$set": {"observation_notes": novo_feed, "updated_at": nota["created_at"]}},
    )
    return bool(getattr(resultado, "matched_count", 0))


async def run_partner_add_note(partner: dict, case_id: str, data: PartnerNoteIn) -> dict:
    caso = await resolver_caso(partner, case_id)
    if not caso.e_processo:
        raise HTTPException(status_code=409, detail=ERRO_SO_NUM_PROCESSO)
    if await processo_esta_fechado(caso.process):
        raise HTTPException(status_code=409, detail=ERRO_PROCESSO_FECHADO)

    texto = limpar_texto_da_nota(data.text)
    if not texto:
        raise HTTPException(status_code=400, detail=ERRO_NOTA_VAZIA)

    nota = construir_nota_do_parceiro(texto, partner)
    processo = caso.process
    for _ in range(TENTATIVAS_DA_ESCRITA):
        feed = processo.get("observation_notes")
        if isinstance(feed, list) and len(feed) >= MAX_NOTAS_NO_PROCESSO:
            raise HTTPException(status_code=409, detail=ERRO_FEED_CHEIO)
        if await _gravar(caso.id, processo, nota):
            break
        # O feed mudou entre a leitura e a escrita (a equipa escreveu ao mesmo tempo): reler e repetir.
        # Sem o `observation_notes` de volta a nota perderia a outra — por isso não se escreve às cegas.
        recarregado = await db.processes.find_one(
            {"id": caso.id}, {"_id": 0, "id": 1, "observation_notes": 1, "observations": 1, "notes": 1,
                              "created_at": 1},
        )
        if not recarregado:
            raise HTTPException(status_code=404, detail="Caso não encontrado.")
        processo = recarregado
    else:
        raise HTTPException(status_code=409, detail=ERRO_CONCORRENCIA)

    await _efeitos_sem_falhar(caso.id, caso.process, partner, texto)
    return {"success": True, "nota": dto_da_nota(nota, partner["id"])}


async def _efeitos_sem_falhar(process_id: str, processo: dict, partner: dict, texto: str) -> None:
    """Histórico e aviso à equipa atribuída. A nota já está gravada: nada aqui a pode fazer falhar."""
    nome = str(partner.get("name") or "Parceiro")
    try:
        from services.history import log_history

        await log_history(
            process_id,
            {"id": f"partner:{partner['id']}", "name": f"{nome} (Parceiro)", "role": "parceiro"},
            "Parceiro adicionou nota",
            "observation_notes",
            None,
            texto[:500],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[PARCEIRO-NOTA] histórico não gravado (%s): %s", process_id, exc)

    try:
        from services.portal_assigned_users import get_all_assigned_user_ids
        from services.realtime_notifications import send_realtime_notification

        completo = await db.processes.find_one({"id": process_id}, {"_id": 0}) or processo
        referencia = f"#{completo.get('process_number')}" if completo.get("process_number") else process_id[:8]
        # `get_all_assigned_user_ids` inclui o parceiro atribuído (`assigned_parceiro_id`), que NÃO é um
        # utilizador: avisá-lo pelo canal da equipa é escrever para um id que não existe.
        fora = {partner["id"], completo.get("assigned_parceiro_id")}
        for uid in [u for u in get_all_assigned_user_ids(completo) if u and u not in fora]:
            await send_realtime_notification(
                user_id=uid,
                title="Nova nota do parceiro",
                message=f"{nome} escreveu uma nota no processo {referencia}.",
                notification_type="partner_note",
                link=f"/processes/{process_id}",
                process_id=process_id,
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[PARCEIRO-NOTA] aviso à equipa não enviado (%s): %s", process_id, exc)


__all__ = [
    "ERRO_FEED_CHEIO",
    "ERRO_PROCESSO_FECHADO",
    "ERRO_SO_NUM_PROCESSO",
    "MAX_NOTAS_NO_PROCESSO",
    "ORIGEM_PARCEIRO",
    "PartnerNoteIn",
    "construir_nota_do_parceiro",
    "dto_da_nota",
    "limpar_texto_da_nota",
    "run_partner_add_note",
]
