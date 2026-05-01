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


class WorkflowStatusUpdate(BaseModel):
    label: Optional[str] = None
    order: Optional[int] = None
    color: Optional[str] = None
    description: Optional[str] = None
    portal_label: Optional[str] = None
    visible_in_portal: Optional[bool] = None


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
