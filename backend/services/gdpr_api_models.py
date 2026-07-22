"""GDPR route Pydantic models.

Extraído de `routes/gdpr.py`.
Do **not** overwrite services/gdpr.py.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class AnonymizeRequest(BaseModel):
    """Request para anonimização."""
    process_id: Optional[str] = None
    user_id: Optional[str] = None
    dry_run: bool = False


class BatchAnonymizeRequest(BaseModel):
    """Request para anonimização em lote."""
    retention_days: Optional[int] = None
    batch_size: int = 100
    dry_run: bool = True  # Default: dry run por segurança
