from enum import Enum

from pydantic import BaseModel
from typing import Optional


class MacroFase(str, Enum):
    """Agrupamento da fase no funil de negócio (Épico 10, Parte 2).

    ENUM FECHADO, de propósito. Texto livre criaria um grupo novo com uma
    gralha — `aprovdo` — e o funil partia-se em silêncio: os processos
    dessa fase desapareciam do grupo certo e apareciam num grupo de um
    só, com ar de categoria legítima. É a mesma armadilha do Campo de
    Rede (Lote 5, ponto 2), e aqui o Pydantic recusa antes de gravar.

    Uma fase SEM macro-fase é válida: cai em "Outras fases" no funil, com
    o nome à vista, até o administrador decidir. Nunca desaparece.
    """

    NOVO = "novo"
    ANALISE = "analise"
    APROVADO = "aprovado"
    CONCLUIDO = "concluido"
    PERDIDO = "perdido"


class WorkflowStatusCreate(BaseModel):
    name: str
    label: str
    order: int
    color: str = "blue"
    description: Optional[str] = None
    # Épico 10, Parte 2 — agrupamento no funil de negócio.
    macro_fase: Optional[MacroFase] = None
    portal_label: Optional[str] = None
    visible_in_portal: bool = True
    # PACOTE BS — Dynamic Workflow Purpose Flags
    # Flags de comportamento lidas pelo move_process_kanban (Pacote BR).
    # Se None, o backend usa fallback retrocompatível (hardcoded status strings).
    is_active: Optional[bool] = None
    trigger_finance: Optional[bool] = None
    trigger_countdown: Optional[bool] = None
    trigger_property_check: Optional[bool] = None
    trigger_deed_reminder: Optional[bool] = None


class WorkflowStatusUpdate(BaseModel):
    label: Optional[str] = None
    order: Optional[int] = None
    color: Optional[str] = None
    description: Optional[str] = None
    macro_fase: Optional[MacroFase] = None
    portal_label: Optional[str] = None
    visible_in_portal: Optional[bool] = None
    # PACOTE BS — Dynamic Workflow Purpose Flags
    is_active: Optional[bool] = None
    trigger_finance: Optional[bool] = None
    trigger_countdown: Optional[bool] = None
    trigger_property_check: Optional[bool] = None
    trigger_deed_reminder: Optional[bool] = None


class WorkflowStatusResponse(BaseModel):
    id: str
    name: str
    label: str
    order: int
    color: str
    description: Optional[str] = None
    is_default: bool = False
    internal_code: Optional[str] = None
    # `None` = ainda não classificada; cai em "Outras fases" no funil.
    macro_fase: Optional[MacroFase] = None
    portal_label: Optional[str] = None
    visible_in_portal: bool = True
    # PACOTE BS — Dynamic Workflow Purpose Flags (None = fallback ativo)
    is_active: Optional[bool] = None
    trigger_finance: Optional[bool] = None
    trigger_countdown: Optional[bool] = None
    trigger_property_check: Optional[bool] = None
    trigger_deed_reminder: Optional[bool] = None
