"""Restore document handler.

Extraído de `routes/restore.py`.
Do **not** overwrite services/backup_restore.py.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from database import db


async def run_restore_document(document_id: str, user: dict):
    """Restaura um documento que foi eliminado (main collection or trash)."""
    # Verificar se o documento existe na coleção principal
    document = await db.documents.find_one({"id": document_id})

    if document:
        if not document.get("deleted", False):
            raise HTTPException(
                status_code=400,
                detail="Documento não está eliminado"
            )

        # Restaurar documento
        await db.documents.update_one(
            {"id": document_id},
            {"$set": {
                "deleted": False,
                "deleted_at": None,
                "restored_at": datetime.now(timezone.utc).isoformat(),
                "restored_by": user["id"]
            }}
        )

        # Log
        await db.history.insert_one({
            "id": str(__import__('uuid').uuid4()),
            "process_id": document.get("process_id"),
            "user_id": user["id"],
            "user_name": user.get("name"),
            "action": f"Documento restaurado: {document.get('filename', document_id)}",
            "created_at": datetime.now(timezone.utc).isoformat()
        })

        updated = await db.documents.find_one({"id": document_id}, {"_id": 0})

        return {
            "success": True,
            "message": "Documento restaurado com sucesso",
            "document": updated
        }

    # Verificar na coleção de lixo
    deleted_doc = await db.deleted_documents.find_one({"id": document_id})

    if deleted_doc:
        # Restaurar da coleção de lixo
        restored_doc = deleted_doc.copy()
        restored_doc["deleted"] = False
        restored_doc["restored_at"] = datetime.now(timezone.utc).isoformat()
        restored_doc["restored_by"] = user["id"]

        # Inserir de volta na coleção principal
        await db.documents.insert_one(restored_doc)

        # Remover da coleção de lixo
        await db.deleted_documents.delete_one({"id": document_id})

        # Log
        await db.history.insert_one({
            "id": str(__import__('uuid').uuid4()),
            "process_id": deleted_doc.get("process_id"),
            "user_id": user["id"],
            "user_name": user.get("name"),
            "action": f"Documento restaurado do lixo: {deleted_doc.get('filename', document_id)}",
            "created_at": datetime.now(timezone.utc).isoformat()
        })

        if "_id" in restored_doc:
            del restored_doc["_id"]

        return {
            "success": True,
            "message": "Documento restaurado com sucesso",
            "document": restored_doc
        }

    raise HTTPException(status_code=404, detail="Documento não encontrado")
