"""
====================================================================
MODELOS DE ANOTAÇÕES DE DOCUMENTOS - CREDITOIMO
====================================================================
Modelos Pydantic para o sistema de anotações contextuais em documentos.

Anotações podem ser do tipo: note, question, warning, financial, approval.
Cada anotação está associada a uma posição específica num documento
(page, x%, y%) e a um processo.
====================================================================
"""
from pydantic import BaseModel, Field
from typing import Optional


# ====================================================================
# CONSTANTES - Tipos de Anotação
# ====================================================================

ANNOTATION_TYPES = {
    "note": {
        "label": "Nota",
        "color": "#3B82F6",
    },
    "question": {
        "label": "Questão",
        "color": "#F59E0B",
    },
    "warning": {
        "label": "Aviso",
        "color": "#EF4444",
    },
    "financial": {
        "label": "Financeiro",
        "color": "#22C55E",
    },
    "approval": {
        "label": "Aprovação",
        "color": "#8B5CF6",
    },
}

VALID_ANNOTATION_TYPES = list(ANNOTATION_TYPES.keys())


# ====================================================================
# MODELO COMPLETO - DocumentAnnotation
# ====================================================================

class DocumentAnnotation(BaseModel):
    """Modelo completo de uma anotação de documento."""
    id: str
    process_id: str
    document_path: str
    document_name: str
    page: int = Field(..., ge=1, description="Número da página (1-indexed)")
    x: float = Field(..., ge=0, le=100, description="Posição X em percentagem da largura da página (0-100)")
    y: float = Field(..., ge=0, le=100, description="Posição Y em percentagem da altura da página (0-100)")
    comment: str
    annotation_type: str = Field(..., description=f"Tipo de anotação: {', '.join(VALID_ANNOTATION_TYPES)}")
    color: Optional[str] = None
    author_id: str
    author_name: str
    created_at: str
    updated_at: Optional[str] = None
    resolved: bool = False
    resolved_by: Optional[str] = None
    resolved_at: Optional[str] = None


# ====================================================================
# SCHEMA DE CRIAÇÃO - AnnotationCreate
# ====================================================================

class AnnotationCreate(BaseModel):
    """Schema para criação de uma nova anotação."""
    process_id: str
    document_path: str
    document_name: str
    page: int = Field(..., ge=1, description="Número da página (1-indexed)")
    x: float = Field(..., ge=0, le=100, description="Posição X em percentagem (0-100)")
    y: float = Field(..., ge=0, le=100, description="Posição Y em percentagem (0-100)")
    comment: str = Field(..., min_length=1, max_length=2000, description="Conteúdo da anotação")
    annotation_type: str = Field(..., description=f"Tipo: {', '.join(VALID_ANNOTATION_TYPES)}")
    color: Optional[str] = Field(None, description="Cor personalizada (hex). Se omitida, usa a cor padrão do tipo.")


# ====================================================================
# SCHEMA DE ATUALIZAÇÃO - AnnotationUpdate
# ====================================================================

class AnnotationUpdate(BaseModel):
    """Schema para atualização de uma anotação existente."""
    comment: Optional[str] = Field(None, min_length=1, max_length=2000, description="Novo conteúdo da anotação")
    annotation_type: Optional[str] = Field(None, description=f"Novo tipo: {', '.join(VALID_ANNOTATION_TYPES)}")
    color: Optional[str] = Field(None, description="Nova cor personalizada (hex)")
    resolved: Optional[bool] = Field(None, description="Marcar como resolvida ou pendente")


# ====================================================================
# SCHEMA DE RESPOSTA - AnnotationResponse
# ====================================================================

class AnnotationResponse(BaseModel):
    """Schema de resposta para uma anotação."""
    id: str
    process_id: str
    document_path: str
    document_name: str
    page: int
    x: float
    y: float
    comment: str
    annotation_type: str
    color: Optional[str] = None
    author_id: str
    author_name: str
    created_at: str
    updated_at: Optional[str] = None
    resolved: bool = False
    resolved_by: Optional[str] = None
    resolved_at: Optional[str] = None
