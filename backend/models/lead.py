"""
Modelo de dados para Leads de Imóveis (Gestão de Visitas)
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum
from datetime import datetime


class LeadStatus(str, Enum):
    """Estados possíveis de um lead de imóvel"""
    NOVO = "novo"
    CONTACTADO = "contactado"
    VISITA_AGENDADA = "visita_agendada"
    PROPOSTA = "proposta"
    RESERVADO = "reservado"
    DESCARTADO = "descartado"


class ConsultantInfo(BaseModel):
    """Informações do comercial/consultor do imóvel"""
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    agency_name: Optional[str] = None
    source_url: Optional[str] = None


class LeadHistory(BaseModel):
    """Histórico de eventos do lead"""
    timestamp: str
    event: str
    user: Optional[str] = None
    details: Optional[str] = None


class PropertyLeadCreate(BaseModel):
    """Dados para criar um novo lead"""
    url: str
    title: Optional[str] = None
    price: Optional[float] = None
    location: Optional[str] = None
    typology: Optional[str] = None
    area: Optional[float] = None
    photo_url: Optional[str] = None
    consultant: Optional[ConsultantInfo] = None
    client_id: Optional[str] = None  # Processo/cliente associado
    notes: Optional[str] = None


class PropertyLeadUpdate(BaseModel):
    """Dados para actualizar um lead"""
    title: Optional[str] = None
    price: Optional[float] = None
    location: Optional[str] = None
    typology: Optional[str] = None
    area: Optional[float] = None
    photo_url: Optional[str] = None
    consultant: Optional[ConsultantInfo] = None
    client_id: Optional[str] = None
    status: Optional[LeadStatus] = None
    notes: Optional[str] = None


class PropertyLead(BaseModel):
    """Lead de imóvel completo"""
    id: str
    url: str
    title: Optional[str] = None
    price: Optional[float] = None
    location: Optional[str] = None
    typology: Optional[str] = None
    area: Optional[float] = None
    photo_url: Optional[str] = None
    consultant: Optional[ConsultantInfo] = None
    status: LeadStatus = LeadStatus.NOVO
    client_id: Optional[str] = None
    client_name: Optional[str] = None  # Preenchido ao buscar
    notes: Optional[str] = None
    history: List[LeadHistory] = []
    created_at: str
    updated_at: str
    created_by: Optional[str] = None


class ScrapedData(BaseModel):
    """Dados extraídos de um URL"""
    url: str
    title: Optional[str] = None
    price: Optional[float] = None
    location: Optional[str] = None
    typology: Optional[str] = None
    area: Optional[float] = None
    photo_url: Optional[str] = None
    consultant: Optional[ConsultantInfo] = None
    source: str = "manual"  # "idealista", "imovirtual", "manual"
    raw_data: Optional[Dict[str, Any]] = None
