from pydantic import BaseModel
from typing import Optional


class WorkflowStatusCreate(BaseModel):
    name: str
    label: str
    order: int
    color: str = "blue"
    description: Optional[str] = None
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
    portal_label: Optional[str] = None
    visible_in_portal: bool = True
    # PACOTE BS — Dynamic Workflow Purpose Flags (None = fallback ativo)
    is_active: Optional[bool] = None
    trigger_finance: Optional[bool] = None
    trigger_countdown: Optional[bool] = None
    trigger_property_check: Optional[bool] = None
    trigger_deed_reminder: Optional[bool] = None
