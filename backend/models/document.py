from pydantic import BaseModel
from typing import Optional


class DocumentExpiry(BaseModel):
    """Document expiry date tracking for a client."""
    process_id: str
    document_type: str  # 'cc', 'carta_conducao', 'passaporte', 'contrato_trabalho', etc.
    document_name: str
    expiry_date: str  # YYYY-MM-DD
    data_emissao: Optional[str] = None  # Data de emissão do documento (YYYY-MM-DD)
    notes: Optional[str] = None


class DocumentExpiryCreate(BaseModel):
    process_id: str
    document_type: str
    document_name: str
    expiry_date: str
    data_emissao: Optional[str] = None
    notes: Optional[str] = None


class DocumentExpiryUpdate(BaseModel):
    document_name: Optional[str] = None
    expiry_date: Optional[str] = None
    data_emissao: Optional[str] = None
    notes: Optional[str] = None


class DocumentExpiryResponse(BaseModel):
    id: str
    process_id: str
    document_type: str
    document_name: str
    expiry_date: str
    data_emissao: Optional[str] = None
    notes: Optional[str] = None
    created_at: str
    created_by: str


class DocumentValidityCheck(BaseModel):
    """Resultado da verificação de validade de documento."""
    document_type: str
    has_expiry: bool
    is_valid: bool
    warning: Optional[str] = None
    error: Optional[str] = None
    days_remaining: Optional[int] = None
    expiry_date: Optional[str] = None


# ====================================================================
# NOVOS MODELOS PARA CATEGORIZAÇÃO IA
# ====================================================================
from pydantic import Field
from typing import List


class DocumentMetadata(BaseModel):
    """
    Metadados de documento com categorização IA.
    Guardado na colecção `document_metadata`.
    """
    id: str
    process_id: str
    client_name: str
    
    # Scope do documento: 'global' (pertence ao cliente, ex: CC) ou 'process' (pertence ao processo, ex: Caderneta Predial)
    doc_scope: Optional[str] = None  # 'global' | 'process'
    # client_id do cliente (diferente de process_id quando o doc é partilhado entre processos)
    client_id: Optional[str] = None
    
    # Localização do ficheiro
    s3_path: str
    filename: str
    original_filename: Optional[str] = None
    
    # Categorização IA
    ai_category: Optional[str] = None  # Categoria atribuída pela IA
    ai_subcategory: Optional[str] = None  # Subcategoria mais específica
    ai_confidence: Optional[float] = None  # Confiança da categorização (0-1)
    ai_tags: Optional[List[str]] = None  # Tags adicionais extraídas
    ai_summary: Optional[str] = None  # Resumo do conteúdo do documento
    
    # Data de validade extraída pela IA
    expiry_date: Optional[str] = None  # Data de expiração no formato YYYY-MM-DD
    expiry_alert_sent: bool = False  # Flag para evitar alertas duplicados
    
    # Conteúdo extraído para pesquisa
    extracted_text: Optional[str] = None  # Texto extraído do documento
    
    # Metadados do ficheiro
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    
    # Timestamps
    created_at: str
    updated_at: Optional[str] = None
    categorized_at: Optional[str] = None
    
    # Flags
    is_categorized: bool = False
    categorization_failed: bool = False
    categorization_error: Optional[str] = None
    # Análise IA (extração de dados / Analisar com IA) — distinto de is_categorized
    ai_analyzed: bool = False
    ai_analyzed_at: Optional[str] = None

    # PACOTE DJ — Human-in-the-Loop review (IA sugere, consultor aprova)
    # ai_review_status: 'pending' (IA gerou sugestões) | 'approved' (consultor aprovou tal qual)
    #                  | 'edited' (consultor aprovou com edições) | 'rejected' (consultor rejeitou)
    ai_review_status: Optional[str] = None  # 'pending' | 'approved' | 'rejected' | 'edited'
    ai_reviewed_at: Optional[str] = None  # ISO datetime da decisão do consultor
    ai_reviewed_by: Optional[str] = None  # ID do utilizador que decidiu
    ai_applied_fields: Optional[List[str]] = None  # campos aplicados (ex: ['categoria','validade','nome','filename'])
    # Sugestões da IA (paralelo a ai_* aplicado — só passam para ai_* quando aprovadas)
    suggested_category: Optional[str] = None
    suggested_subcategory: Optional[str] = None
    suggested_confidence: Optional[float] = None
    suggested_expiry_date: Optional[str] = None
    suggested_filename: Optional[str] = None
    suggested_nome: Optional[str] = None  # nome extraído pela IA


class DocumentMetadataCreate(BaseModel):
    """Dados para criar metadados de documento."""
    process_id: str
    client_name: str
    s3_path: str
    filename: str
    original_filename: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None


class DocumentMetadataResponse(BaseModel):
    """Resposta com metadados de documento."""
    id: str
    process_id: str
    client_name: str
    s3_path: str
    filename: str
    original_filename: Optional[str] = None
    ai_category: Optional[str] = None
    ai_subcategory: Optional[str] = None
    ai_confidence: Optional[float] = None
    ai_tags: Optional[List[str]] = None
    ai_summary: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None
    is_categorized: bool = False
    ai_analyzed: bool = False
    ai_analyzed_at: Optional[str] = None
    # PACOTE DJ — Human-in-the-Loop review
    ai_review_status: Optional[str] = None
    ai_reviewed_at: Optional[str] = None
    ai_reviewed_by: Optional[str] = None
    ai_applied_fields: Optional[List[str]] = None
    suggested_category: Optional[str] = None
    suggested_subcategory: Optional[str] = None
    suggested_confidence: Optional[float] = None
    suggested_expiry_date: Optional[str] = None
    suggested_filename: Optional[str] = None
    suggested_nome: Optional[str] = None
    expiry_date: Optional[str] = None


class DocumentSearchRequest(BaseModel):
    """Request para pesquisa de documentos."""
    query: str = Field(..., min_length=2, max_length=500)
    process_id: Optional[str] = None  # Filtrar por processo/cliente específico
    categories: Optional[List[str]] = None  # Filtrar por categorias
    limit: int = Field(default=20, ge=1, le=100)


class DocumentSearchResult(BaseModel):
    """Resultado de pesquisa de documento."""
    id: str
    process_id: str
    client_name: str
    s3_path: str
    filename: str
    ai_category: Optional[str] = None
    ai_summary: Optional[str] = None
    relevance_score: float = 0.0
    matched_text: Optional[str] = None  # Trecho do texto que corresponde à pesquisa
