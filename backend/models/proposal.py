"""
Modelo de Proposta Bancária
============================

Representa uma proposta de financiamento enviada por um banco para um
processo de crédito. Cada proposta é analisada pela IA para extrair
resumos (chave e detalhado) que podem ser publicados no Portal do Cliente.

Colecção MongoDB: proposals

Ciclo de vida:
  1. Consultor faz upload do PDF → cria-se registo com status='draft'
  2. Backend chama IA para gerar key_summary e detailed_summary
  3. Consultor revê/edita os resumos no CRM
  4. Consultor clica 'Publicar no Portal' → status='published'
  5. Cliente vê a proposta no seu portal
  6. Sempre que uma nova proposta é publicada, o resumo comparativo
     é regenerado pela IA e guardado no campo comparison_summary do
     processo (poupando tokens em leituras futuras)

Segurança:
  - Propostas 'draft' NÃO são visíveis no Portal do Cliente
  - Apenas propostas 'published' são devolvidas ao portal
  - O resumo comparativo é gerado no backend e cacheado na DB
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List
from datetime import datetime, timezone
from enum import Enum


# ====================================================================
# ENUMS
# ====================================================================

class ProposalStatus(str, Enum):
    """
    Status da proposta bancária.
    - draft:     Ainda em preparação, resumos IA podem estar pendentes
    - published: Visível no Portal do Cliente
    """
    DRAFT = "draft"
    PUBLISHED = "published"

    @classmethod
    def all_values(cls) -> List[str]:
        return [s.value for s in cls]


# ====================================================================
# MODELO PRINCIPAL — Proposta Bancária
# ====================================================================

class BankProposal(BaseModel):
    """
    Modelo de Proposta Bancária — entidade de negócio.

    Ligada a um Processo via process_id (foreign key obrigatória).
    Contém os resumos gerados pela IA e o URL do ficheiro PDF no S3.
    """
    id: str
    process_id: str = Field(
        ...,
        description="ID do processo ao qual esta proposta pertence"
    )

    # Dados do banco
    bank_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Nome do banco que emitiu a proposta (ex: 'BPI', 'Santander')"
    )

    # Ficheiro PDF da proposta
    file_url: str = Field(
        ...,
        description="URL (S3 pre-signed ou caminho) do PDF da proposta"
    )
    file_name: Optional[str] = Field(
        None,
        description="Nome original do ficheiro enviado"
    )
    file_size: Optional[int] = Field(
        None,
        description="Tamanho do ficheiro em bytes"
    )

    # Resumos gerados pela IA
    key_summary: Optional[str] = Field(
        None,
        description=(
            "Resumo chave da proposta — bullet points com as condições "
            "principais (spread, TAEG, prestação mensal, etc.)"
        )
    )
    detailed_summary: Optional[str] = Field(
        None,
        description=(
            "Resumo detalhado da proposta — análise completa com todas "
            "as condições, encargos, comissões e cláusulas relevantes"
        )
    )

    # Estado da proposta
    status: ProposalStatus = Field(
        default=ProposalStatus.DRAFT,
        description="'draft' (em preparação) ou 'published' (visível no portal)"
    )

    # Controlo de análise IA
    ai_analysis_pending: bool = Field(
        default=False,
        description="True enquanto a análise IA estiver em curso"
    )
    ai_analysis_error: Optional[str] = Field(
        None,
        description="Mensagem de erro se a análise IA falhou"
    )
    ai_analyzed_at: Optional[str] = Field(
        None,
        description="Timestamp da última análise IA bem-sucedida"
    )

    # Controlo de edição manual
    key_summary_edited: bool = Field(
        default=False,
        description="True se o consultor editou manualmente o resumo chave"
    )
    detailed_summary_edited: bool = Field(
        default=False,
        description="True se o consultor editou manualmente o resumo detalhado"
    )

    # Metadados
    created_by: Optional[str] = Field(
        None,
        description="ID do utilizador que fez upload da proposta"
    )
    published_by: Optional[str] = Field(
        None,
        description="ID do utilizador que publicou a proposta no portal"
    )
    published_at: Optional[str] = Field(
        None,
        description="Timestamp de publicação no portal (ISO 8601)"
    )

    # Timestamps
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ====================================================================
# SCHEMAS DE ENTRADA (Request DTOs)
# ====================================================================

class ProposalCreate(BaseModel):
    """Schema para criar uma nova proposta bancária (upload de PDF)."""
    bank_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Nome do banco"
    )
    file_url: str = Field(
        ...,
        description="URL do PDF no S3 (obtido via pre-signed URL)"
    )
    file_name: Optional[str] = Field(
        None,
        max_length=500,
        description="Nome original do ficheiro"
    )
    file_size: Optional[int] = Field(
        None,
        ge=0,
        description="Tamanho do ficheiro em bytes"
    )


class ProposalUpdate(BaseModel):
    """Schema para actualizar uma proposta (editar resumos, publicar, etc.)."""
    bank_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=200
    )
    key_summary: Optional[str] = Field(
        None,
        description="Resumo chave editado pelo consultor"
    )
    detailed_summary: Optional[str] = Field(
        None,
        description="Resumo detalhado editado pelo consultor"
    )
    status: Optional[ProposalStatus] = None


class ProposalPublishToggle(BaseModel):
    """Schema para alternar o estado de publicação da proposta."""
    published: bool = Field(
        ...,
        description="True para publicar no portal, False para voltar a draft"
    )


class ForceAIAnalysisRequest(BaseModel):
    """Schema para forçar uma nova análise IA (apaga resumos existentes)."""
    confirm: bool = Field(
        default=False,
        description="Confirmação explícita — os resumos actuais serão apagados"
    )


# ====================================================================
# SCHEMAS DE RESPOSTA (Response DTOs)
# ====================================================================

class ProposalResponse(BaseModel):
    """Modelo de resposta para propostas bancárias (CRM — staff)."""
    model_config = ConfigDict(extra="ignore")

    id: str
    process_id: str
    bank_name: str
    file_url: str
    file_name: Optional[str] = None
    file_size: Optional[int] = None

    key_summary: Optional[str] = None
    detailed_summary: Optional[str] = None

    status: ProposalStatus = ProposalStatus.DRAFT

    ai_analysis_pending: bool = False
    ai_analysis_error: Optional[str] = None
    ai_analyzed_at: Optional[str] = None

    key_summary_edited: bool = False
    detailed_summary_edited: bool = False

    created_by: Optional[str] = None
    published_by: Optional[str] = None
    published_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ProposalPortalResponse(BaseModel):
    """
    Modelo de resposta para propostas no Portal do Cliente.
    Apenas devolve propostas publicadas e dados seguros (sem metadados internos).
    """
    model_config = ConfigDict(extra="ignore")

    id: str
    bank_name: str
    key_summary: Optional[str] = None
    detailed_summary: Optional[str] = None
    published_at: Optional[str] = None


class ComparisonSummaryResponse(BaseModel):
    """Resposta com o resumo comparativo de propostas de um processo."""
    process_id: str
    comparison_summary: Optional[str] = None
    proposals_count: int = 0
    compared_at: Optional[str] = None


# ====================================================================
# MODELO COMPARATIVO — Embebido no Processo
# ====================================================================

class ProposalComparisonData(BaseModel):
    """
    Dados de comparação de propostas — embebidos no documento do Processo.

    Este sub-modelo é guardado dentro do processo para evitar uma colecção
    separada e permitir cache eficiente. Sempre que uma proposta é
    publicada/despublicada, o backend regenera este campo via IA.

    Guardar na DB poupa tokens em leituras futuras — o comparativo é
    gerado uma vez e servido directamente da cache.
    """
    comparison_summary: Optional[str] = Field(
        None,
        description=(
            "Texto comparativo gerado pela IA que analisa todas as "
            "propostas publicadas do processo, destacando diferenças "
            "de spread, TAEG, comissões, prestações e condições especiais"
        )
    )
    compared_proposal_ids: List[str] = Field(
        default_factory=list,
        description="IDs das propostas que foram incluídas na última comparação"
    )
    compared_at: Optional[str] = Field(
        None,
        description="Timestamp da última comparação gerada (ISO 8601)"
    )
    compared_count: int = Field(
        default=0,
        description="Número de propostas incluídas na comparação"
    )
