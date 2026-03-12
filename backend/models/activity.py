from pydantic import BaseModel
from typing import Optional, Any


class ActivityCreate(BaseModel):
    process_id: str
    comment: str


class ActivityResponse(BaseModel):
    id: str
    process_id: str
    user_id: str
    user_name: str
    user_role: str
    comment: str
    created_at: str


class HistoryResponse(BaseModel):
    id: str
    process_id: str
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    action: str
    field: Optional[str] = None
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    created_at: str
