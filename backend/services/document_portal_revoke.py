"""
====================================================================
Apagar no CRM retira o documento do Portal (Missão de Limpeza, ponto 6)
====================================================================
É a operação INVERSA de `document_portal_fulfill`: se carregar um
ficheiro faz REQUESTED→RECEIVED, apagá-lo tem de fazer o caminho de
volta.

O DEFEITO QUE ISTO FECHA
------------------------
`document_delete` apagava o objecto no S3 e o registo em
`document_metadata` — e nunca tocava em `db.documents`, que é onde o
Portal guarda o pedido com `status: RECEIVED`, `s3_path` e
`attached_files`. O cliente continuava a ver um documento que já não
existia, e um pedido apagado por estar ERRADO continuava a contar como
satisfeito: o processo avançava com base num ficheiro inexistente.

NUNCA BLOQUEIA
--------------
Quando isto corre, o ficheiro JÁ saiu do S3. Uma falha aqui não pode
propagar-se: o utilizador veria um erro sobre uma operação que foi bem
sucedida, e tentaria repeti-la. Falhas são registadas e devolvidas no
resultado.
====================================================================
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from database import db
from services.document_portal_counts import parse_expected_count

logger = logging.getLogger(__name__)

# Status que significam "o pedido está satisfeito".
_SATISFEITO = ("RECEIVED", "received")

# Status para onde um pedido volta quando deixa de estar satisfeito. É o
# mesmo que a geração da checklist usa, para o Portal o mostrar como
# pendente sem casos especiais.
_PENDENTE = "REQUESTED"


def _caminho_de(entrada: Any) -> str:
    if isinstance(entrada, dict):
        return str(entrada.get("s3_path") or "").strip()
    return str(entrada or "").strip()


def rebuild_after_removal(
    pedido: dict,
    *,
    removidos: list[str],
) -> Optional[dict]:
    """Estado de um pedido do Portal depois de apagar ficheiros dele.

    Args:
        pedido: documento de `db.documents` (o pedido do Portal).
        removidos: caminhos S3 que deixaram de existir.

    Returns:
        Os campos a gravar, ou ``None`` quando o pedido não referencia
        nenhum dos caminhos — nesse caso não há nada a escrever, e escrever
        à mesma sujaria o `updated_at` de pedidos que ninguém tocou.
    """
    alvos = {c.strip() for c in (removidos or []) if c and c.strip()}
    if not alvos or not pedido:
        return None

    anexos = list(pedido.get("attached_files") or [])
    sobreviventes = [a for a in anexos if _caminho_de(a) not in alvos]
    topo_afectado = str(pedido.get("s3_path") or "").strip() in alvos

    if len(sobreviventes) == len(anexos) and not topo_afectado:
        return None

    # O Portal mostra os campos de topo por omissão. Deixá-los a apontar
    # para o ficheiro apagado era metade do defeito: o pedido voltava a
    # pendente mas a ligação continuava lá.
    mais_recente = sobreviventes[-1] if sobreviventes else None

    estado: dict[str, Any] = {
        "attached_files": sobreviventes,
        "uploaded_count": len(sobreviventes),
        "s3_path": _caminho_de(mais_recente),
        "filename": (
            str((mais_recente or {}).get("filename") or "")
            if isinstance(mais_recente, dict)
            else ""
        ),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    # A mesma regra de contagem do upload (`document_portal_counts`): o
    # pedido só está satisfeito com ficheiros suficientes.
    esperados = parse_expected_count(pedido)
    estava_satisfeito = str(pedido.get("status") or "") in _SATISFEITO
    if estava_satisfeito and len(sobreviventes) < esperados:
        estado["status"] = _PENDENTE
    else:
        estado["status"] = pedido.get("status") or _PENDENTE

    return estado


async def revoke_portal_files_on_delete(
    process_id: Optional[str],
    caminhos: list[str],
) -> dict[str, Any]:
    """Retira do Portal os ficheiros apagados no CRM.

    Args:
        process_id: processo a que os ficheiros pertenciam.
        caminhos: caminhos S3 eliminados.

    Returns:
        `{revoked: int, reopened: int, erro: str | None}` — nunca levanta.
    """
    alvos = [c.strip() for c in (caminhos or []) if c and c.strip()]
    if not alvos:
        return {"revoked": 0, "reopened": 0, "erro": None}

    revogados = 0
    reabertos = 0
    try:
        consulta: dict[str, Any] = {
            "$or": [
                {"s3_path": {"$in": alvos}},
                {"attached_files.s3_path": {"$in": alvos}},
            ]
        }
        if process_id:
            consulta["process_id"] = process_id

        pedidos = []
        async for doc in db.documents.find(consulta, {"_id": 0}):
            pedidos.append(doc)

        for pedido in pedidos:
            estado = rebuild_after_removal(pedido, removidos=alvos)
            if not estado:
                continue
            await db.documents.update_one(
                {"id": pedido.get("id")}, {"$set": estado}
            )
            revogados += 1
            if estado.get("status") == _PENDENTE and str(
                pedido.get("status") or ""
            ) in _SATISFEITO:
                reabertos += 1

        if revogados:
            logger.info(
                "[PORTAL-REVOKE] %d pedido(s) actualizado(s), %d reaberto(s) "
                "após eliminação de %d ficheiro(s) no processo %s",
                revogados, reabertos, len(alvos), process_id,
            )
    except Exception as e:  # noqa: BLE001 - nunca bloqueia a eliminação
        logger.error(
            "[PORTAL-REVOKE] Falha a sincronizar o Portal após eliminar "
            "%s no processo %s: %s: %s",
            alvos, process_id, type(e).__name__, e,
        )
        return {"revoked": revogados, "reopened": reabertos, "erro": str(e)}

    return {"revoked": revogados, "reopened": reabertos, "erro": None}
