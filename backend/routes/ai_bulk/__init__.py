"""
AI Bulk Import Module
=====================
Módulo para importação em massa de documentos com análise de IA.

Estrutura:
- Router principal (stubs): sibling ``routes/ai_bulk.py`` → ``services/ai_bulk_*``
- Package helpers (kept here):
  - background_jobs.py: Gestão de jobs em background (endpoints)
  - nif_cache.py / document_utils.py / import_errors.py: legacy helpers/endpoints
  - constants.py, cache.py, jobs.py, matching.py, utils.py: shared helpers

``from routes.ai_bulk import router`` loads the sibling stub file lazily via
importlib (package name shadows the .py module). Submodule imports such as
``from routes.ai_bulk.cache import ...`` must not eagerly load that stub, or
services that import package helpers circularly fail.
"""
from __future__ import annotations

import importlib.util
import os
from typing import Any

from .matching import normalize_text_for_matching

_router = None


def _load_router():
    """Load sibling ``routes/ai_bulk.py`` router once (avoids circular imports)."""
    global _router
    if _router is not None:
        return _router

    _current_dir = os.path.dirname(os.path.abspath(__file__))
    _parent_dir = os.path.dirname(_current_dir)
    _ai_bulk_file = os.path.join(_parent_dir, "ai_bulk.py")

    _spec = importlib.util.spec_from_file_location("_ai_bulk_original", _ai_bulk_file)
    _ai_bulk_module = importlib.util.module_from_spec(_spec)
    assert _spec.loader is not None
    _spec.loader.exec_module(_ai_bulk_module)
    _router = _ai_bulk_module.router
    return _router


def __getattr__(name: str) -> Any:
    if name == "router":
        return _load_router()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["router", "normalize_text_for_matching"]
