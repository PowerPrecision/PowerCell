"""
====================================================================
ROTAS DE UTILIZADORES - CREDITOIMO
====================================================================
Endpoints de leitura para utilizadores do sistema.
CRUD de admin está em admin.py
====================================================================
"""
from typing import List
from fastapi import APIRouter, Depends

from database import db
from models.auth import UserRole, UserResponse
from services.auth import require_staff


router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=List[UserResponse])
async def get_users(role: str = None, user: dict = Depends(require_staff())):
    """
    Listar utilizadores do sistema.
    Filtro opcional por papel (role).
    """
    query = {}
    if role:
        query["role"] = role
    
    users = await db.users.find(query, {"_id": 0, "password": 0}).to_list(500)
    return users


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, user: dict = Depends(require_staff())):
    """Obter utilizador por ID."""
    found_user = await db.users.find_one({"id": user_id}, {"_id": 0, "password": 0})
    if not found_user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")
    return found_user
