"""Restore route helpers.

Extraído de `routes/restore.py`.
Do **not** overwrite services/backup_restore.py.
"""
from __future__ import annotations

# Estados considerados terminais — um processo restaurado com um destes
# status fica is_active=False; qualquer outro status fica is_active=True.
TERMINAL_STATUSES = ("concluido", "desistencia", "desistencias", "arquivo", "perdido")
