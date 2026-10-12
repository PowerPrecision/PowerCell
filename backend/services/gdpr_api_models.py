"""GDPR route Pydantic models.

Extraído de `routes/gdpr.py`.
Do **not** overwrite services/gdpr.py.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


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
    #: Password ACTUAL de quem executa. Obrigatória quando `dry_run` é falso (a anonimização não
    #: se desfaz); o ensaio não altera nada e não a pede. `repr=False`: nunca num log.
    password: Optional[str] = Field(None, max_length=256, repr=False)
