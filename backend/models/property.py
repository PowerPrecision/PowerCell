"""
Modelo de dados para Imóveis Angariados
Representa imóveis listados directamente pela agência (não leads externos)
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime


class PropertyStatus(str, Enum):
    """Estados possíveis de um imóvel angariado"""
    DISPONIVEL = "disponivel"
    RESERVADO = "reservado"
    VENDIDO = "vendido"
    SUSPENSO = "suspenso"
    EM_ANALISE = "em_analise"


class PropertyType(str, Enum):
    """Tipos de imóvel"""
    APARTAMENTO = "apartamento"
    MORADIA = "moradia"
    TERRENO = "terreno"
    LOJA = "loja"
    ESCRITORIO = "escritorio"
    ARMAZEM = "armazem"
    GARAGEM = "garagem"
    OUTRO = "outro"


class PropertyCondition(str, Enum):
    """Estado de conservação"""
    NOVO = "novo"
    COMO_NOVO = "como_novo"
    BOM = "bom"
    PARA_RECUPERAR = "para_recuperar"
    EM_CONSTRUCAO = "em_construcao"


class OwnerInfo(BaseModel):
    """Informações do proprietário"""
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    nif: Optional[str] = None
    notes: Optional[str] = None


class PropertyAddress(BaseModel):
    """Endereço completo do imóvel"""
    street: Optional[str] = None
    number: Optional[str] = None
    floor: Optional[str] = None
    postal_code: Optional[str] = None
    locality: Optional[str] = None
    parish: Optional[str] = None  # Freguesia
    municipality: str  # Concelho
    district: str  # Distrito
    coordinates: Optional[Dict[str, float]] = None  # lat, lng


class PropertyFeatures(BaseModel):
    """Características do imóvel"""
    bedrooms: Optional[int] = None  # T0, T1, T2...
    bathrooms: Optional[int] = None
    gross_area: Optional[float] = None  # Área bruta
    useful_area: Optional[float] = None  # Área útil
    land_area: Optional[float] = None  # Área terreno
    construction_year: Optional[int] = None
    energy_certificate: Optional[str] = None  # A, B, C, D, E, F, G
    garage_spaces: Optional[int] = None
    has_elevator: Optional[bool] = None
    has_balcony: Optional[bool] = None
    has_terrace: Optional[bool] = None
    has_garden: Optional[bool] = None
    has_pool: Optional[bool] = None
    has_storage: Optional[bool] = None
    solar_orientation: Optional[str] = None  # Norte, Sul, Este, Oeste
    floor_number: Optional[int] = None
    total_floors: Optional[int] = None
    extra_features: List[str] = []  # Ar condicionado, lareira, etc.


class PropertyFinancials(BaseModel):
    """Dados financeiros do imóvel"""
    asking_price: float  # Preço pedido
    minimum_price: Optional[float] = None  # Preço mínimo aceitável
    commission_percentage: Optional[float] = None  # % comissão
    commission_fixed: Optional[float] = None  # Valor fixo comissão
    condominium_fee: Optional[float] = None  # Valor condomínio mensal
    imt_value: Optional[float] = None  # Valor IMT estimado
    stamp_duty: Optional[float] = None  # Imposto selo
    annual_property_tax: Optional[float] = None  # IMI anual


class PropertyHistory(BaseModel):
    """Histórico de eventos do imóvel"""
    timestamp: str
    event: str
    user: Optional[str] = None
    details: Optional[str] = None


class PropertyCreate(BaseModel):
    """Dados para criar um novo imóvel"""
    # Identificação
    internal_reference: Optional[str] = None  # Referência interna
    property_type: PropertyType = PropertyType.APARTAMENTO
    title: str  # Título para listagem
    description: Optional[str] = None
    
    # Localização
    address: PropertyAddress
    
    # Características
    features: Optional[PropertyFeatures] = None
    condition: PropertyCondition = PropertyCondition.BOM
    
    # Financeiro
    financials: PropertyFinancials
    
    # Proprietário
    owner: OwnerInfo
    
    # Medias
    photos: List[str] = []  # URLs das fotos
    video_url: Optional[str] = None
    virtual_tour_url: Optional[str] = None
    
    # Documentos
    documents: List[str] = []  # URLs/refs dos documentos
    
    # Estado
    status: PropertyStatus = PropertyStatus.EM_ANALISE
    
    # Associações
    assigned_agent_id: Optional[str] = None  # Consultor responsável
    
    # Notas
    notes: Optional[str] = None
    private_notes: Optional[str] = None  # Notas internas (não visíveis ao cliente)


class PropertyUpdate(BaseModel):
    """Dados para actualizar um imóvel"""
    internal_reference: Optional[str] = None
    property_type: Optional[PropertyType] = None
    title: Optional[str] = None
    description: Optional[str] = None
    address: Optional[PropertyAddress] = None
    features: Optional[PropertyFeatures] = None
    condition: Optional[PropertyCondition] = None
    financials: Optional[PropertyFinancials] = None
    owner: Optional[OwnerInfo] = None
    photos: Optional[List[str]] = None
    video_url: Optional[str] = None
    virtual_tour_url: Optional[str] = None
    documents: Optional[List[str]] = None
    status: Optional[PropertyStatus] = None
    assigned_agent_id: Optional[str] = None
    notes: Optional[str] = None
    private_notes: Optional[str] = None


class Property(BaseModel):
    """Imóvel angariado completo"""
    id: str
    internal_reference: Optional[str] = None
    property_type: PropertyType
    title: str
    description: Optional[str] = None
    
    address: PropertyAddress
    features: Optional[PropertyFeatures] = None
    condition: PropertyCondition
    financials: PropertyFinancials
    owner: OwnerInfo
    
    photos: List[str] = []
    video_url: Optional[str] = None
    virtual_tour_url: Optional[str] = None
    documents: List[str] = []
    
    status: PropertyStatus
    assigned_agent_id: Optional[str] = None
    assigned_agent_name: Optional[str] = None  # Preenchido ao buscar
    
    notes: Optional[str] = None
    private_notes: Optional[str] = None
    
    # Estatísticas
    view_count: int = 0
    inquiry_count: int = 0
    visit_count: int = 0
    
    # Histórico
    history: List[PropertyHistory] = []
    
    # Timestamps
    created_at: str
    updated_at: str
    created_by: Optional[str] = None
    
    # Clientes interessados
    interested_clients: List[str] = []  # IDs de processos/clientes


class PropertyListItem(BaseModel):
    """Versão resumida para listagem"""
    id: str
    internal_reference: Optional[str] = None
    title: str
    property_type: PropertyType
    status: PropertyStatus
    asking_price: float
    municipality: str
    district: str
    bedrooms: Optional[int] = None
    useful_area: Optional[float] = None
    photo_url: Optional[str] = None
    assigned_agent_name: Optional[str] = None
    created_at: str
