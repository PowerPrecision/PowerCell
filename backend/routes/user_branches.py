"""
====================================================================
ROTAS DE BALCÕES PERSONALIZADOS POR UTILIZADOR - POWERCELL
====================================================================
Endpoints para CRUD de balcões personalizados (UserCustomBranch).

Cada utilizador autenticado pode criar os seus próprios balcões que
ficam visíveis apenas para si no modal de envio de documentação.

COLLECTION: user_custom_branches (MongoDB)
DOCUMENTO: { _id, user_id, name, email, created_at }

ROTAS:
  POST /api/user-branches          — Criar balcão personalizado
  GET  /api/user-branches          — Listar balcões do utilizador
  DELETE /api/user-branches/{id}   — Apagar balcão personalizado
"""
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
from bson import ObjectId

from database import db
from services.auth import get_current_user
from models.system_config import UserCustomBranchCreate, UserCustomBranchResponse

router = APIRouter(prefix="/user-branches", tags=["User Custom Branches"])

COLLECTION = "user_custom_branches"


@router.post("", response_model=UserCustomBranchResponse, status_code=201)
async def create_user_branch(
    body: UserCustomBranchCreate,
    current_user: dict = Depends(get_current_user),
):
    """
    Criar um novo balcão personalizado associado ao utilizador autenticado.

    Validações:
    - name e email são obrigatórios
    - não permite duplicado (mesmo name+email para o mesmo user)
    """
    user_id = current_user["id"]

    # Verificar duplicado (mesmo nome + email para o mesmo utilizador)
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


@router.get("", response_model=list[UserCustomBranchResponse])
async def list_user_branches(
    current_user: dict = Depends(get_current_user),
):
    """
    Listar todos os balcões personalizados do utilizador autenticado.
    """
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


@router.delete("/{branch_id}", status_code=204)
async def delete_user_branch(
    branch_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Apagar um balcão personalizado.
    Só o próprio utilizador pode apagar os seus balcões.
    """
    user_id = current_user["id"]

    if not ObjectId.is_valid(branch_id):
        raise HTTPException(status_code=400, detail="ID de balcão inválido.")

    result = await db[COLLECTION].delete_one({
        "_id": ObjectId(branch_id),
        "user_id": user_id,  # Garantir que só o dono pode apagar
    })

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Balcão não encontrado.")
