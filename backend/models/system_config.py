"""
Modelo de dados para Configurações do Sistema
Permite configurar o sistema via interface de admin
"""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from enum import Enum


class StorageProvider(str, Enum):
    """Provedores de armazenamento suportados"""
    AWS_S3 = "aws_s3"
    ONEDRIVE = "onedrive"
    GOOGLE_DRIVE = "google_drive"
    DROPBOX = "dropbox"
    LOCAL = "local"
    NONE = "none"


class EmailProvider(str, Enum):
    """Provedores de email suportados"""
    SMTP = "smtp"
    SENDGRID = "sendgrid"
    NONE = "none"


class AIProvider(str, Enum):
    """Provedores de IA suportados"""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    EMERGENT = "emergent"


class IntegrationConfig(BaseModel):
    """Configuração de uma integração"""
    enabled: bool = False
    provider: Optional[str] = None
    credentials: Dict[str, Any] = {}
    settings: Dict[str, Any] = {}


class StorageConfig(BaseModel):
    """Configuração do serviço de armazenamento"""
    provider: StorageProvider = StorageProvider.NONE
    # AWS S3
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_bucket_name: Optional[str] = None
    aws_region: Optional[str] = None
    # OneDrive
    onedrive_client_id: Optional[str] = None
    onedrive_client_secret: Optional[str] = None
    onedrive_tenant_id: Optional[str] = None
    onedrive_redirect_uri: Optional[str] = None
    onedrive_shared_url: Optional[str] = None
    # Google Drive
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    google_redirect_uri: Optional[str] = None
    google_folder_id: Optional[str] = None
    # Dropbox
    dropbox_app_key: Optional[str] = None
    dropbox_app_secret: Optional[str] = None
    dropbox_access_token: Optional[str] = None


class EmailConfig(BaseModel):
    """Configuração do serviço de email - Suporta duas contas"""
    provider: EmailProvider = EmailProvider.NONE
    
    # Conta Principal (Power Real Estate)
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = 465
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_ssl: bool = True
    imap_server: Optional[str] = None
    imap_port: Optional[int] = 993
    imap_user: Optional[str] = None
    imap_password: Optional[str] = None
    
    # Conta Secundária (Precision Crédito)
    smtp_server_2: Optional[str] = None
    smtp_port_2: Optional[int] = 465
    smtp_user_2: Optional[str] = None
    smtp_password_2: Optional[str] = None
    smtp_use_ssl_2: bool = True
    imap_server_2: Optional[str] = None
    imap_port_2: Optional[int] = 993
    imap_user_2: Optional[str] = None
    imap_password_2: Optional[str] = None


class AIConfig(BaseModel):
    """Configuração do serviço de IA"""
    provider: AIProvider = AIProvider.OPENAI
    api_key: Optional[str] = None
    model: Optional[str] = "gpt-4o-mini"
    max_tokens: int = 4000


class TrelloConfig(BaseModel):
    """Configuração do Trello"""
    enabled: bool = False
    api_key: Optional[str] = None
    api_token: Optional[str] = None
    board_id: Optional[str] = None
    webhook_base_url: Optional[str] = None


class ReportFrequency(str, Enum):
    """Frequência de envio do relatório de IA"""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    DISABLED = "disabled"


class AIReportConfig(BaseModel):
    """Configuração do relatório automático de IA"""
    enabled: bool = True
    frequency: ReportFrequency = ReportFrequency.WEEKLY
    send_day: int = 0  # 0=Segunda, 1=Terça, ... 6=Domingo (para semanal)
    send_hour: int = 9  # Hora do envio (0-23)
    recipients_type: str = "admins"  # "admins", "all_staff", "custom"
    custom_recipients: List[str] = []  # Lista de user IDs se recipients_type="custom"
    include_insights: bool = True
    include_charts: bool = True


class CreditServicesConfig(BaseModel):
    """Configuração dos serviços de crédito"""
    primary_provider: str = "hcpro"  # "hcpro", "decisoes_e_solucoes", "doutorfinancas", etc.
    enabled_providers: List[str] = ["hcpro", "bcp"]
    auto_assign_mediator: bool = True
    default_interest_rate: Optional[float] = None
    max_loan_to_value: float = 90.0
    min_income_ratio: float = 35.0
    default_term_years: int = 30
    simulation_validity_days: int = 30
    
    # HCPro
    hcpro_url: Optional[str] = None
    hcpro_user: Optional[str] = None
    hcpro_password: Optional[str] = None
    
    # Decisões e Soluções
    decisoes_url: Optional[str] = None
    decisoes_user: Optional[str] = None
    decisoes_password: Optional[str] = None
    
    # Doutor Finanças
    doutorfinancas_url: Optional[str] = None
    doutorfinancas_user: Optional[str] = None
    doutorfinancas_password: Optional[str] = None
    
    # Portal Personalizado
    custom_portal_name: Optional[str] = None
    custom_portal_url: Optional[str] = None
    custom_portal_user: Optional[str] = None
    custom_portal_password: Optional[str] = None
    
    # Serviço secundário
    secondary_provider: Optional[str] = None


class SystemSettings(BaseModel):
    """Configurações gerais do sistema"""
    company_name: str = "Power Real Estate"
    company_subtitle: str = "& Precision Crédito"
    logo_url: Optional[str] = None
    primary_color: str = "#0F766E"
    secondary_color: str = "#FCD34D"
    timezone: str = "Europe/Lisbon"
    language: str = "pt-PT"
    currency: str = "EUR"
    date_format: str = "dd/MM/yyyy"


class SystemConfig(BaseModel):
    """Configuração completa do sistema"""
    storage: StorageConfig = StorageConfig()
    email: EmailConfig = EmailConfig()
    ai: AIConfig = AIConfig()
    trello: TrelloConfig = TrelloConfig()
    settings: SystemSettings = SystemSettings()
    credit_services: CreditServicesConfig = CreditServicesConfig()
    setup_completed: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class ConfigUpdateRequest(BaseModel):
    """Request para actualizar configuração"""
    section: str  # "storage", "email", "ai", "trello", "settings"
    data: Dict[str, Any]


class ConfigField(BaseModel):
    """Definição de um campo de configuração para o frontend"""
    key: str
    label: str
    type: str  # "text", "password", "number", "select", "boolean"
    required: bool = False
    placeholder: Optional[str] = None
    options: Optional[List[Dict[str, str]]] = None  # Para select
    help_text: Optional[str] = None
    depends_on: Optional[Dict[str, Any]] = None  # Mostrar apenas se outra opção tiver valor X
