"""User custom branches CRUD handlers.

Extraído de `routes/user_branches.py`.
"""
from __future__ import annotations

from datetime import datetime, timezone

from bson import ObjectId
from fastapi import HTTPException

from database import db
from models.system_config import UserCustomBranchCreate, UserCustomBranchResponse

COLLECTION = "user_custom_branches"


async def run_create_user_branch(body: UserCustomBranchCreate, current_user: dict):
    user_id = current_user["id"]

    existing = await db[COLLECTION].find_one({
        "user_id": user_id,
        "name": body.name.strip(),
        "email": body.email.strip().lower(),
    })
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Já existe um balcão '{body.name}' com esse email na sua lista.",
        )

    doc = {
        "user_id": user_id,
        "name": body.name.strip(),
        "email": body.email.strip().lower(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    result = await db[COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id

    return UserCustomBranchResponse(
        id=str(doc["_id"]),
        user_id=str(doc["user_id"]),
        name=doc["name"],
        email=doc["email"],
        is_custom=True,
        created_at=doc["created_at"],
    )


async def run_list_user_branches(current_user: dict):
    user_id = current_user["id"]
    cursor = db[COLLECTION].find({"user_id": user_id}).sort("name", 1)
    branches = await cursor.to_list(100)

    return [
        UserCustomBranchResponse(
            id=str(b["_id"]),
            user_id=str(b["user_id"]),
            name=b["name"],
            email=b["email"],
            is_custom=True,
            created_at=b.get("created_at"),
        )
        for b in branches
    ]


async def run_delete_user_branch(branch_id: str, current_user: dict):
    user_id = current_user["id"]

    if not ObjectId.is_valid(branch_id):
        raise HTTPException(status_code=400, detail="ID de balcão inválido.")

    result = await db[COLLECTION].delete_one({
        "_id": ObjectId(branch_id),
        "user_id": user_id,
    })

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Balcão não encontrado.")
