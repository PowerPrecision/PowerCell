from pydantic import BaseModel, field_validator
from typing import Optional, List, Literal


# PACOTE DH — Opções válidas para reminder_time (multi-select de lembretes).
REMINDER_TIME_OPTIONS = {"1h", "3h", "1d", "3d", "7d"}

# PACOTE DQ — Agenda: prazos, marcações e ausências/férias.
DEADLINE_TYPES = ("deadline", "event", "absence")
DEADLINE_TYPE_ALIASES = {
    "ferias": "absence",
    "férias": "absence",
    "ausencia": "absence",
    "ausência": "absence",
    "ausencias": "absence",
    "ausências": "absence",
}


def normalize_deadline_type(value, *, default="deadline", allow_none=False):
    """Normaliza o tipo de entrada da agenda (inclui aliases PT)."""
    if value is None:
        return None if allow_none else default
    if isinstance(value, str):
        v_lower = value.strip().lower()
        v_lower = DEADLINE_TYPE_ALIASES.get(v_lower, v_lower)
        if v_lower not in DEADLINE_TYPES:
            raise ValueError(
                f"type inválido: {value!r}. "
                f"Valores válidos: {', '.join(DEADLINE_TYPES)}"
            )
        return v_lower
    return value


class DeadlineCreate(BaseModel):
    process_id: Optional[str] = None  # Optional - can create general deadline
    title: str
    description: Optional[str] = None
    due_date: str
    priority: str = "medium"
    assigned_user_ids: Optional[List[str]] = None  # Lista de utilizadores atribuídos
    # Campos legacy para compatibilidade
    assigned_consultor_id: Optional[str] = None
    assigned_mediador_id: Optional[str] = None

    # PACOTE DH/DQ — Agenda: tipo, visibilidade no portal, lembretes, dia inteiro.
    type: Literal["deadline", "event", "absence"] = "deadline"
    visible_to_client: bool = False
    reminder_time: Optional[List[str]] = None  # Valores: "1h", "3h", "1d", "3d", "7d"
    all_day: bool = False
    end_date: Optional[str] = None

    @field_validator("reminder_time", mode="before")
    @classmethod
    def _validate_reminder_time(cls, v):
        """PACOTE DH — Validar e deduplicar reminder_time."""
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError("reminder_time deve ser uma lista")
        invalid = [x for x in v if x not in REMINDER_TIME_OPTIONS]
        if invalid:
            raise ValueError(
                f"reminder_time inválido: {invalid}. "
                f"Valores válidos: {sorted(REMINDER_TIME_OPTIONS)}"
            )
        # Deduplicar preservando a ordem de inserção.
        seen = set()
        deduped = []
        for x in v:
            if x not in seen:
                seen.add(x)
                deduped.append(x)
        return deduped

    @field_validator("type", mode="before")
    @classmethod
    def _validate_type(cls, v):
        """PACOTE DH/DQ — Normalizar type (deadline|event|absence + aliases PT)."""
        return normalize_deadline_type(v)


class DeadlineUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: Optional[str] = None
    priority: Optional[str] = None
    completed: Optional[bool] = None
    assigned_user_ids: Optional[List[str]] = None
    assigned_consultor_id: Optional[str] = None
    assigned_mediador_id: Optional[str] = None
    process_id: Optional[str] = None

    # PACOTE DH/DQ — Agenda: campos opcionais para update parcial.
    type: Optional[Literal["deadline", "event", "absence"]] = None
    visible_to_client: Optional[bool] = None
    reminder_time: Optional[List[str]] = None
    all_day: Optional[bool] = None
    end_date: Optional[str] = None

    @field_validator("reminder_time", mode="before")
    @classmethod
    def _validate_reminder_time(cls, v):
        """PACOTE DH — Validar e deduplicar reminder_time no update."""
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError("reminder_time deve ser uma lista")
        invalid = [x for x in v if x not in REMINDER_TIME_OPTIONS]
        if invalid:
            raise ValueError(
                f"reminder_time inválido: {invalid}. "
                f"Valores válidos: {sorted(REMINDER_TIME_OPTIONS)}"
            )
        seen = set()
        deduped = []
        for x in v:
            if x not in seen:
                seen.add(x)
                deduped.append(x)
        return deduped

    @field_validator("type", mode="before")
    @classmethod
    def _validate_type(cls, v):
        """PACOTE DH/DQ — Normalizar type no update (None mantém-se None)."""
        return normalize_deadline_type(v, allow_none=True)


class DeadlineResponse(BaseModel):
    id: str
    process_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    due_date: str
    priority: str
    completed: Optional[bool] = None
    created_by: Optional[str] = None
    created_at: str
    assigned_user_ids: Optional[List[str]] = None  # Lista de utilizadores atribuídos
    assigned_consultor_id: Optional[str] = None
    assigned_mediador_id: Optional[str] = None
    # Legacy fields from database
    status: Optional[str] = None
    assigned_user_id: Optional[str] = None
    assigned_user_name: Optional[str] = None

    # PACOTE DH/DQ — Agenda: novos campos na resposta (defaults para retrocompatibilidade).
    type: Literal["deadline", "event", "absence"] = "deadline"
    visible_to_client: bool = False
    reminder_time: Optional[List[str]] = None
    all_day: bool = False
    end_date: Optional[str] = None
    company_id: Optional[str] = None

    @field_validator("type", mode="before")
    @classmethod
    def _validate_type(cls, v):
        return normalize_deadline_type(v)
