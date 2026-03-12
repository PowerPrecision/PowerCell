from pydantic import BaseModel
from typing import Optional


class WorkflowStatusCreate(BaseModel):
    name: str
    label: str
    order: int
    color: str = "blue"
    description: Optional[str] = None


class WorkflowStatusUpdate(BaseModel):
    label: Optional[str] = None
    order: Optional[int] = None
    color: Optional[str] = None
    description: Optional[str] = None


class WorkflowStatusResponse(BaseModel):
    id: str
    name: str
    label: str
    order: int
    color: str
    description: Optional[str] = None
    is_default: bool = False
