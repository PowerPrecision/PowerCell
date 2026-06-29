"""
Modelos Pydantic para System Changelog (Mural de Atualizações gerado por IA)

Coleção MongoDB: system_changelogs
Permite que a IA gere notas de lançamento amigáveis a partir de logs técnicos.
"""
from typing import Optional, List
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from bson import ObjectId


class ChangelogEntry(BaseModel):
    """Representa uma entrada de changelog gerada por IA."""
    id: Optional[str] = None
    version: str = Field(..., description="Versão ou identificador da atualização (ex: '2026-06-25')")
    content_markdown: str = Field(..., description="Conteúdo em Markdown da nota de atualização")
    published_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    generated_by: str = Field(default="ai", description="Quem gerou: 'ai' ou 'manual'")
    source_summary: Optional[str] = Field(None, description="Resumo do texto técnico usado como fonte")

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


class ChangelogResponse(BaseModel):
    """Resposta de uma entrada de changelog para o frontend."""
    id: str
    version: str
    content_markdown: str
    published_at: datetime
    generated_by: str
    source_summary: Optional[str] = None

    model_config = {"populate_by_name": True, "arbitrary_types_allowed": True}


class ChangelogGenerateRequest(BaseModel):
    """Pedido de geração de changelog por IA (opcionalmente com fonte personalizada).

    CORREÇÃO (Pacote AE-fix): default mudado de 'git' para 'worklog' porque
    no Render a pasta .git não está disponível no container de deploy.
    'worklog' lê o ficheiro físico worklog.md que está sempre presente.
    """
    source_type: str = Field(default="worklog", description="Fonte dos dados: 'worklog', 'changelog_file', 'git' (git pode falhar no Render)")
    max_source_lines: int = Field(default=50, description="Número máximo de linhas a ler da fonte")
    custom_prompt_suffix: Optional[str] = Field(None, description="Sufixo opcional a adicionar ao prompt da IA")


class ChangelogGenerateResponse(BaseModel):
    """Resposta após geração de changelog por IA."""
    changelog: ChangelogResponse
    tokens_used: Optional[int] = None
