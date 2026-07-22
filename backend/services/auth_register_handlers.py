"""Auth register orchestration — extracted from `routes/auth.py`.

Do **not** overwrite existing `services/auth.py` (hashing, tokens, get_current_user).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from models.auth import UserRole, UserRegister, UserResponse, TokenResponse
from services.auth import hash_password, create_token, validate_password_strength


async def run_register(request, response, data: UserRegister):
    """Regista um novo utilizador a partir do formulário público.

    Este endpoint é acessível sem autenticação e permite que novos
    utilizadores se registem no sistema. O role padrão é CLIENTE.

    Porquê sem autenticação: este é o ponto de entrada para novos
    utilizadores que ainda não têm conta. A validação é feita via
    campos obrigatórios (email, nome) e verificação de unicidade.

    Args:
        request: Objeto Request do FastAPI (para definir cookies).
        response: Objeto Response do FastAPI (para definir cookies).
        data: Dados de registo (UserRegister com email, name, phone, password).

    Returns:
        dict: Dados do utilizador registado com access_token.

    Raises:
        HTTPException(400): Se email em falta, já existe, ou dados inválidos.
    """
    # Normalizar inputs (sem validação de formato)
    clean_email = (data.email or "").strip().lower()
    if not clean_email:
        raise HTTPException(status_code=400, detail="Email é obrigatório")

    clean_name = (data.name or "").strip()
    clean_phone = (data.phone or "").strip() if data.phone else None

    existing = await db.users.find_one({"email": clean_email})
    if existing:
        raise HTTPException(status_code=400, detail="Email já registado")

    # Validar força da password
    is_valid, error_msg = validate_password_strength(data.password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    user_doc = {
        "id": user_id,
        "email": clean_email,
        "password": hash_password(data.password),
        "name": clean_name,
        "phone": clean_phone,
        "role": UserRole.CLIENTE,
        "is_active": True,
        "onedrive_folder": clean_name,
        "created_at": now
    }

    await db.users.insert_one(user_doc)
    token = create_token(user_id, clean_email, UserRole.CLIENTE)

    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user_id,
            email=clean_email,
            name=clean_name,
            phone=clean_phone,
            role=UserRole.CLIENTE,
            created_at=now,
            onedrive_folder=clean_name
        )
    )
