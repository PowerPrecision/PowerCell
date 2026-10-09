from enum import Enum

from pydantic import BaseModel, Field, field_validator
from typing import List, Literal, Optional

#: Papéis que a automação de fase sabe atribuir (os que têm lista e carimbos
#: canónicos em `process_staff_assignment`). A Indexação tem carimbo próprio e
#: nunca é atribuída por regra de fase.
PapelAtribuivel = Literal["consultor", "intermediario"]
PrioridadeDeTarefa = Literal["Alta", "Média", "Baixa"]
ResponsavelDaTarefa = Literal["consultor", "intermediario", "todos"]

#: Tecto de modelos por fase: uma fase com dezenas de tarefas automáticas é um
#: erro de configuração, não um fluxo de trabalho.
MAXIMO_DE_MODELOS_POR_FASE = 20


class TarefaModelo(BaseModel):
    """Uma tarefa que o sistema cria quando um processo ENTRA numa fase.

    Configurada só por Admin/CEO (as rotas do workflow já o exigem). O `id`
    é o que torna a criação idempotente: o editor devolve-o intacto, e uma
    tarefa nova recebe um id gerado no servidor.
    """

    id: Optional[str] = None
    title: str = Field(min_length=1, max_length=120)
    priority: PrioridadeDeTarefa = "Média"
    due_in_days: Optional[int] = Field(default=None, ge=0, le=365)
    # «todos» = quem tiver consultor OU intermediário no processo nesse momento.
    assigned_role: ResponsavelDaTarefa = "todos"

    @field_validator("title")
    @classmethod
    def _titulo_nao_pode_ser_so_espacos(cls, valor: str) -> str:
        limpo = " ".join(valor.split())
        if not limpo:
            raise ValueError("O título da tarefa não pode ficar vazio.")
        return limpo


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
    # Bloco 3 (ponto 12) — o que acontece quando um processo ENTRA nesta fase.
    # `None` = não configurado (herda o comportamento por omissão, que só
    # existe para a saída da Index); `[]` = configurado como «nada».
    auto_assign_roles: Optional[List[PapelAtribuivel]] = None
    task_templates: Optional[List[TarefaModelo]] = Field(
        default=None, max_length=MAXIMO_DE_MODELOS_POR_FASE
    )


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
    auto_assign_roles: Optional[List[PapelAtribuivel]] = None
    task_templates: Optional[List[TarefaModelo]] = Field(
        default=None, max_length=MAXIMO_DE_MODELOS_POR_FASE
    )


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
    auto_assign_roles: Optional[List[PapelAtribuivel]] = None
    task_templates: Optional[List[TarefaModelo]] = None
