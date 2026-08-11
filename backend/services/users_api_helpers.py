"""Shared constants for users API routes.

Extraído de `routes/users.py`.
Do **not** overwrite `services/auth.py` or admin user CRUD.
"""
from __future__ import annotations

# Roles que usam exclusivamente config partilhada do departamento
FORCED_SHARED_ROLES = {"indexacao", "suporte"}
