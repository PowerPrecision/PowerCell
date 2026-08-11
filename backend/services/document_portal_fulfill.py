"""
Marca pedidos portal (REQUESTED/PENDING) como RECEIVED quando a equipa
carrega documentação no CRM.

O upload do cliente (portal/confirm-upload) já faz REQUESTED → RECEIVED.
O upload staff (S3FileManager / confirm-upload directo) só gravava no S3 —
o portal do cliente continuava a mostrar o documento como pendente.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from database import db

logger = logging.getLogger(__name__)

_PENDING = ("REQUESTED", "PENDING", "requested", "pending")

# Pastas S3 do CRM → categorias típicas dos pedidos portal / checklist
_CRM_FOLDER_TO_PORTAL = {
    "documentos pessoais": [
        "Cartao_Cidadao",
        "Certidao_Nascimento",
        "Atestado_Trabalho",
    ],
    "financeiros": [
        "IRS",
        "Financeiros",
        "Recibo_Vencimento",
        "Declaracao_Imposto_Renda",
        "Mapa_Creditos",
        "Comprovativo_IBAN",
    ],
    "imóvel": [
        "Certidao_Permanente",
        "Contrato_Promessa",
        "Plantas_Casa",
        "Certificado_Energetico",
    ],
    "imovel": [
        "Certidao_Permanente",
        "Contrato_Promessa",
        "Plantas_Casa",
        "Certificado_Energetico",
    ],
    "bancários": ["Comprovativo_IBAN", "Mapa_Creditos"],
    "bancarios": ["Comprovativo_IBAN", "Mapa_Creditos"],
}

# Aliases de categoria / label → chave canónica portal
_CATEGORY_ALIASES = {
    "cartao_cidadao": "Cartao_Cidadao",
    "cartão de cidadão": "Cartao_Cidadao",
    "cartao de cidadao": "Cartao_Cidadao",
    "cc": "Cartao_Cidadao",
    "irs": "IRS",
    "declaração de irs": "IRS",
    "declaracao de irs": "IRS",
    "recibo_vencimento": "Recibo_Vencimento",
    "recibo de vencimento": "Recibo_Vencimento",
    "comprovativo_iban": "Comprovativo_IBAN",
    "comprovativo de iban": "Comprovativo_IBAN",
    "iban": "Comprovativo_IBAN",
    "certidao_nascimento": "Certidao_Nascimento",
    "atestado_trabalho": "Atestado_Trabalho",
    "mapa_creditos": "Mapa_Creditos",
    "certidao_permanente": "Certidao_Permanente",
    "contrato_promessa": "Contrato_Promessa",
    "cpcv": "Contrato_Promessa",
    "plantas_casa": "Plantas_Casa",
    "certificado_energetico": "Certificado_Energetico",
    "financeiros": "Financeiros",
    "outros": "Outros",
}


def _norm(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = (
        text.replace("á", "a")
        .replace("à", "a")
        .replace("â", "a")
        .replace("ã", "a")
        .replace("é", "e")
        .replace("ê", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ô", "o")
        .replace("õ", "o")
        .replace("ú", "u")
        .replace("ç", "c")
    )
    text = re.sub(r"[_\s\-]+", " ", text)
    return text.strip()


def _category_variants(category: Optional[str]) -> set[str]:
    """Conjunto de chaves/labels normalizadas que podem casar com o upload."""
    variants: set[str] = set()
    raw = (category or "").strip()
    if not raw:
        return variants

    variants.add(_norm(raw))
    variants.add(_norm(raw.replace("_", " ")))

    alias = _CATEGORY_ALIASES.get(_norm(raw)) or _CATEGORY_ALIASES.get(
        _norm(raw.replace("_", " "))
    )
    if alias:
        variants.add(_norm(alias))
        variants.add(_norm(alias.replace("_", " ")))

    for portal_key in _CRM_FOLDER_TO_PORTAL.get(_norm(raw), []):
        variants.add(_norm(portal_key))
        variants.add(_norm(portal_key.replace("_", " ")))

    return variants


def _doc_category_raw(doc: dict) -> str:
    cat = doc.get("category")
    if isinstance(cat, dict):
        return str(cat.get("value") or cat.get("label") or "")
    return str(cat or "")


def _score_pending_doc(
    doc: dict,
    *,
    category_variants: set[str],
    filename: str,
) -> int:
    """Score de matching; 0 = sem match."""
    score = 0
    doc_cat = _doc_category_raw(doc)
    doc_variants = _category_variants(doc_cat)
    label = _norm(doc.get("custom_label") or doc.get("notes") or "")
    fname = _norm(filename)

    if category_variants and doc_variants and (category_variants & doc_variants):
        score += 10

    # Label do pedido aparece no nome do ficheiro (ou vice-versa)
    if label and fname:
        if label in fname or fname in label:
            score += 6
        else:
            # tokens significativos
            label_tokens = [t for t in label.split() if len(t) > 3]
            hits = sum(1 for t in label_tokens if t in fname)
            if hits >= 1:
                score += 3

    # Subcategoria IA / alias no filename
    for alias_key, portal_key in _CATEGORY_ALIASES.items():
        if alias_key in fname and (
            _norm(portal_key) in doc_variants or _norm(doc_cat) == _norm(portal_key)
        ):
            score += 4
            break

    return score


async def fulfill_portal_requests_on_staff_upload(
    process_id: str,
    *,
    category: Optional[str],
    filename: str,
    s3_path: Optional[str] = None,
    content_type: Optional[str] = None,
    file_size: Optional[int] = None,
    user: Optional[dict] = None,
    document_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    Satisfaz o melhor pedido portal pendente do processo.

    Returns:
        {fulfilled: int, document_ids: list[str]}
    """
    if not process_id:
        return {"fulfilled": 0, "document_ids": []}

    # Index = pasta cofre; sem categoria útil ainda — não marcar à sorte
    if _norm(category) in ("index",):
        return {"fulfilled": 0, "document_ids": [], "reason": "index_skip"}

    now = datetime.now(timezone.utc).isoformat()
    user_id = (user or {}).get("id") or "staff"
    user_name = (user or {}).get("name") or "Equipa"

    update_fields = {
        "status": "RECEIVED",
        "filename": filename,
        "original_filename": filename,
        "uploaded_at": now,
        "updated_at": now,
        "uploaded_by": user_id,
        "reviewed_by": user_id,
        "reviewed_at": now,
        "received_via": "staff_crm_upload",
        "received_by_name": user_name,
    }
    if s3_path:
        update_fields["s3_path"] = s3_path
    if content_type:
        update_fields["content_type"] = content_type
    if file_size is not None:
        update_fields["file_size"] = file_size

    # PACOTE DE — APPEND logic: cada upload da equipa é acrescentado ao array
    # `attached_files` do pedido REQUESTED (nunca substitui uploads anteriores).
    # Mantêm-se os campos top-level com $set para retrocompatibilidade —
    # serializadores lêem esses campos directamente (devem reflectir o
    # upload MAIS RECENTE). O array `attached_files` preserva o histórico.
    file_entry = {
        "file_id": str(uuid.uuid4()),
        "filename": filename,
        "original_filename": filename,
        "s3_path": s3_path or "",
        "file_size": file_size if file_size is not None else 0,
        "content_type": content_type or "",
        "uploaded_at": now,
        "uploaded_by": user_id,
        "uploaded_by_name": user_name,
        "source": "staff_crm_upload",
    }

    # Match directo por document_id (pedido específico)
    if document_id:
        result = await db.documents.update_one(
            {
                "id": document_id,
                "process_id": process_id,
                "status": {"$in": list(_PENDING)},
            },
            {
                "$set": update_fields,
                # PACOTE DE — adiciona entrada ao histórico de ficheiros anexados
                "$push": {"attached_files": file_entry},
            },
        )
        if result.modified_count:
            logger.info(
                f"[PORTAL-FULFILL] REQUESTED→RECEIVED (by id) {document_id} "
                f"process={process_id}"
            )
            return {"fulfilled": 1, "document_ids": [document_id]}

    pending = await db.documents.find(
        {
            "process_id": process_id,
            "status": {"$in": list(_PENDING)},
        },
        {"_id": 0},
    ).to_list(100)

    if not pending:
        return {"fulfilled": 0, "document_ids": []}

    category_variants = _category_variants(category)
    scored: list[tuple[int, dict]] = []
    for doc in pending:
        sc = _score_pending_doc(
            doc, category_variants=category_variants, filename=filename or ""
        )
        if sc > 0:
            scored.append((sc, doc))

    if not scored:
        return {"fulfilled": 0, "document_ids": [], "reason": "no_match"}

    scored.sort(key=lambda x: (-x[0], x[1].get("created_at") or ""))
    best_score, best = scored[0]
    # Exigir match mínimo razoável (categoria ou label)
    if best_score < 3:
        return {"fulfilled": 0, "document_ids": [], "reason": "weak_match"}

    doc_id = best.get("id")
    if not doc_id:
        return {"fulfilled": 0, "document_ids": []}

    result = await db.documents.update_one(
        {"id": doc_id, "process_id": process_id, "status": {"$in": list(_PENDING)}},
        {
            "$set": update_fields,
            # PACOTE DE — adiciona entrada ao histórico de ficheiros anexados
            "$push": {"attached_files": file_entry},
        },
    )
    if result.modified_count:
        logger.info(
            f"[PORTAL-FULFILL] REQUESTED→RECEIVED {doc_id} "
            f"cat={category!r} file={filename!r} score={best_score} "
            f"process={process_id}"
        )
        try:
            from services.portal_documents_notify import check_and_notify_documents_complete

            process = await db.processes.find_one({"id": process_id}, {"_id": 0, "company": 1, "company_id": 1})
            company_id = (process or {}).get("company") or (process or {}).get("company_id")
            await check_and_notify_documents_complete(process_id, company_id)
        except Exception as e:
            logger.warning(f"[PORTAL-FULFILL] notify complete failed: {e}")
        return {"fulfilled": 1, "document_ids": [doc_id]}

    return {"fulfilled": 0, "document_ids": []}
