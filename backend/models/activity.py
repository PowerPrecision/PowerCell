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
    # Proveniência da nota: `None` para um comentário escrito à mão,
    # "voice_note" para o resumo gerado a partir de uma nota de voz
    # (Épico 7). O frontend usa-o para distinguir as duas na timeline.
    origin: Optional[str] = None


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
    # PACOTE DS — campos derivados para a tab Histórico (quem / o quê / detalhes)
    description: Optional[str] = None
    event_type: Optional[str] = None
