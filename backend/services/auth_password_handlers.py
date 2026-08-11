"""Auth password orchestration — extracted from `routes/auth.py`.

Change-password + public validate-password strength endpoint.
Do **not** overwrite existing `services/auth.py`.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import HTTPException

from database import db
from services.auth import (
    hash_password,
    verify_password,
    validate_password_strength,
)


async def run_change_password(data: dict, user: dict):
    """
    Permite ao utilizador alterar a sua própria password.
    """
    current_password = data.get("current_password")
    new_password = data.get("new_password")

    if not current_password or not new_password:
        raise HTTPException(status_code=400, detail="Password atual e nova password são obrigatórias")

    # Validar força da nova password
    is_valid, error_msg = validate_password_strength(new_password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    # Buscar utilizador com password
    user_data = await db.users.find_one({"id": user["id"]})
    if not user_data:
        raise HTTPException(status_code=404, detail="Utilizador não encontrado")

    # Verificar password atual
    password_field = user_data.get("password") or user_data.get("hashed_password", "")
    if not verify_password(current_password, password_field):
        raise HTTPException(status_code=400, detail="Password atual incorreta")

    # Actualizar password
    new_hashed = hash_password(new_password)
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {
            "password": new_hashed,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }}
    )

    return {"success": True, "message": "Password alterada com sucesso"}


async def run_validate_password(data: dict):
    """
    Endpoint público para validar a força de uma password.
    Usado pelo frontend para feedback em tempo real.
    """
    password = data.get("password", "")

    is_valid, error_msg = validate_password_strength(password)

    # Calcular pontuação de força
    score = 0
    feedback = []

    if len(password) >= 8:
        score += 20
    else:
        feedback.append("Pelo menos 8 caracteres")

    if len(password) >= 12:
        score += 10

    if re.search(r'[a-z]', password):
        score += 15
    else:
        feedback.append("Pelo menos uma letra minúscula")

    if re.search(r'[A-Z]', password):
        score += 15
    else:
        feedback.append("Pelo menos uma letra maiúscula")

    if re.search(r'\d', password):
        score += 15
    else:
        feedback.append("Pelo menos um dígito")

    if re.search(r'[@$!%*?&#^()\-_=+\[\]{}|;:,.<>~`]', password):
        score += 25
    else:
        feedback.append("Pelo menos um carácter especial")

    # Determinar nível de força
    if score < 40:
        strength = "muito_fraca"
    elif score < 60:
        strength = "fraca"
    elif score < 80:
        strength = "media"
    elif score < 95:
        strength = "forte"
    else:
        strength = "muito_forte"

    return {
        "valid": is_valid,
        "error": error_msg if not is_valid else None,
        "score": min(score, 100),
        "strength": strength,
        "feedback": feedback
    }
