"""
System config API ops — get/update/fields/companies + CONFIG_FIELDS.

Extraído de `routes/system_config.py`.
Do NOT confuse with `services/system_config.py` (core load/save/cache).
"""
from __future__ import annotations

import logging
import traceback
from typing import Any, Dict, Optional

from fastapi import HTTPException

from models.system_config import ConfigField
from services.system_config import (
    get_system_config,
    update_config_section,
    list_available_companies,
)

logger = logging.getLogger(__name__)

CONFIG_FIELDS = {
    "storage": {
        "title": "Armazenamento de Ficheiros",
        "description": "Configurar o serviço para guardar documentos dos clientes",
        "fields": [
            ConfigField(
                key="provider",
                label="Serviço de Armazenamento",
                type="select",
                required=True,
                options=[
                    {"value": "none", "label": "Nenhum (Desactivado)"},
                    {"value": "aws_s3", "label": "Amazon S3 (Recomendado)"},
                    {"value": "onedrive", "label": "Microsoft OneDrive"},
                    {"value": "google_drive", "label": "Google Drive"},
                    {"value": "dropbox", "label": "Dropbox"},
                ],
                help_text="Escolha onde guardar os documentos dos clientes"
            ),
            # AWS S3
            ConfigField(
                key="aws_access_key_id",
                label="AWS Access Key ID",
                type="text",
                placeholder="AKIA...",
                depends_on={"provider": "aws_s3"},
                help_text="ID da chave de acesso AWS"
            ),
            ConfigField(
                key="aws_secret_access_key",
                label="AWS Secret Access Key",
                type="password",
                depends_on={"provider": "aws_s3"},
                help_text="Chave secreta AWS"
            ),
            ConfigField(
                key="aws_bucket_name",
                label="Nome do Bucket S3",
                type="text",
                placeholder="meu-bucket-documentos",
                depends_on={"provider": "aws_s3"},
                help_text="Nome do bucket S3 para documentos"
            ),
            ConfigField(
                key="aws_region",
                label="Região AWS",
                type="text",
                placeholder="eu-west-1",
                depends_on={"provider": "aws_s3"},
                help_text="Região do bucket S3 (ex: eu-west-1, us-east-1)"
            ),
            # OneDrive
            ConfigField(
                key="onedrive_client_id",
                label="Client ID (OneDrive)",
                type="text",
                placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
                depends_on={"provider": "onedrive"},
                help_text="ID da aplicação Azure AD"
            ),
            ConfigField(
                key="onedrive_client_secret",
                label="Client Secret (OneDrive)",
                type="password",
                depends_on={"provider": "onedrive"},
                help_text="Segredo da aplicação Azure AD"
            ),
            ConfigField(
                key="onedrive_shared_url",
                label="URL da Pasta Partilhada (OneDrive)",
                type="text",
                placeholder="https://onedrive.live.com/?...",
                depends_on={"provider": "onedrive"},
                help_text="URL de partilha da pasta raiz dos clientes"
            ),
            # Google Drive
            ConfigField(
                key="google_client_id",
                label="Client ID (Google)",
                type="text",
                depends_on={"provider": "google_drive"},
                help_text="ID do cliente OAuth do Google Cloud"
            ),
            ConfigField(
                key="google_client_secret",
                label="Client Secret (Google)",
                type="password",
                depends_on={"provider": "google_drive"},
                help_text="Segredo do cliente OAuth"
            ),
            ConfigField(
                key="google_folder_id",
                label="ID da Pasta Raiz (Google Drive)",
                type="text",
                depends_on={"provider": "google_drive"},
                help_text="ID da pasta no Google Drive onde estão os clientes"
            ),
        ]
    },
    "email": {
        "title": "Configuração de Email",
        "description": "Configurar servidores de email para envio e recepção (2 contas suportadas)",
        "fields": [
            ConfigField(
                key="provider",
                label="Tipo de Servidor",
                type="select",
                options=[
                    {"value": "none", "label": "Desactivado"},
                    {"value": "smtp", "label": "SMTP/IMAP Tradicional"},
                ],
            ),
            # === CONTA 1: POWER REAL ESTATE ===
            ConfigField(
                key="_divider_power",
                label="Conta 1: Power Real Estate (geral@powerealestate.pt)",
                type="divider",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="smtp_server",
                label="Servidor SMTP",
                type="text",
                placeholder="webmail2.hcpro.pt",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="smtp_port",
                label="Porta SMTP",
                type="number",
                placeholder="465",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="smtp_user",
                label="Email/Utilizador SMTP",
                type="text",
                placeholder="geral@powerealestate.pt",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="smtp_password",
                label="Password SMTP",
                type="password",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="imap_server",
                label="Servidor IMAP",
                type="text",
                placeholder="webmail2.hcpro.pt",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="imap_port",
                label="Porta IMAP",
                type="number",
                placeholder="993",
                depends_on={"provider": "smtp"},
            ),
            # === CONTA 2: PRECISION CRÉDITO ===
            ConfigField(
                key="_divider_precision",
                label="Conta 2: Precision Crédito (geral@precisioncredito.pt)",
                type="divider",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="smtp_server_2",
                label="Servidor SMTP (Precision)",
                type="text",
                placeholder="mail.precisioncredito.pt",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="smtp_port_2",
                label="Porta SMTP (Precision)",
                type="number",
                placeholder="465",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="smtp_user_2",
                label="Email/Utilizador SMTP (Precision)",
                type="text",
                placeholder="geral@precisioncredito.pt",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="smtp_password_2",
                label="Password SMTP (Precision)",
                type="password",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="imap_server_2",
                label="Servidor IMAP (Precision)",
                type="text",
                placeholder="mail.precisioncredito.pt",
                depends_on={"provider": "smtp"},
            ),
            ConfigField(
                key="imap_port_2",
                label="Porta IMAP (Precision)",
                type="number",
                placeholder="993",
                depends_on={"provider": "smtp"},
            ),
        ]
    },
    "ai": {
        "title": "Inteligência Artificial",
        "description": "Configurar o serviço de IA para análise de documentos",
        "fields": [
            ConfigField(
                key="provider",
                label="Fornecedor de IA",
                type="select",
                options=[
                    {"value": "openai", "label": "OpenAI"},
                    {"value": "emergent", "label": "Emergent"},
                ],
            ),
            ConfigField(
                key="api_key",
                label="Chave API",
                type="password",
                help_text="Chave da API do fornecedor escolhido",
            ),
            ConfigField(
                key="model",
                label="Modelo",
                type="select",
                options=[
                    {"value": "gpt-4o-mini", "label": "GPT-4o Mini (Rápido e económico)"},
                    {"value": "gpt-4o", "label": "GPT-4o (Mais preciso)"},
                ],
            ),
        ]
    },
    "credit_services": {
        "title": "Serviços de Crédito Imobiliário",
        "description": "Configurar serviços parceiros para envio de simulações",
        "fields": [
            ConfigField(
                key="primary_provider",
                label="Serviço Principal",
                type="select",
                required=True,
                options=[
                    {"value": "hcpro", "label": "HCPro (Webmail2)"},
                    {"value": "decisoes_e_solucoes", "label": "Decisões e Soluções"},
                    {"value": "doutorfinancas", "label": "Doutor Finanças"},
                    {"value": "maxfinance", "label": "MaxFinance"},
                    {"value": "multiplo", "label": "Múltiplo / UCI"},
                    {"value": "credibom", "label": "Credibom"},
                    {"value": "custom", "label": "Personalizado"},
                ],
                help_text="Escolha o serviço principal para simulações de crédito"
            ),
            ConfigField(
                key="hcpro_url",
                label="URL HCPro",
                type="text",
                placeholder="https://webmail2.hcpro.pt/Mondo/lang/sys/login.aspx",
                depends_on={"primary_provider": "hcpro"},
            ),
            ConfigField(
                key="hcpro_user",
                label="Utilizador HCPro",
                type="text",
                depends_on={"primary_provider": "hcpro"},
            ),
            ConfigField(
                key="hcpro_password",
                label="Password HCPro",
                type="password",
                depends_on={"primary_provider": "hcpro"},
            ),
            ConfigField(
                key="decisoes_url",
                label="URL Portal Decisões e Soluções",
                type="text",
                placeholder="https://portal.decisoes-e-solucoes.pt",
                depends_on={"primary_provider": "decisoes_e_solucoes"},
            ),
            ConfigField(
                key="decisoes_user",
                label="Utilizador D&S",
                type="text",
                depends_on={"primary_provider": "decisoes_e_solucoes"},
            ),
            ConfigField(
                key="decisoes_password",
                label="Password D&S",
                type="password",
                depends_on={"primary_provider": "decisoes_e_solucoes"},
            ),
            ConfigField(
                key="doutorfinancas_url",
                label="URL Doutor Finanças",
                type="text",
                placeholder="https://backoffice.dfredes.com",
                depends_on={"primary_provider": "doutorfinancas"},
            ),
            ConfigField(
                key="doutorfinancas_user",
                label="Utilizador DF",
                type="text",
                depends_on={"primary_provider": "doutorfinancas"},
            ),
            ConfigField(
                key="doutorfinancas_password",
                label="Password DF",
                type="password",
                depends_on={"primary_provider": "doutorfinancas"},
            ),
            ConfigField(
                key="custom_portal_name",
                label="Nome do Portal",
                type="text",
                placeholder="Nome do serviço personalizado",
                depends_on={"primary_provider": "custom"},
            ),
            ConfigField(
                key="custom_portal_url",
                label="URL do Portal",
                type="text",
                placeholder="https://...",
                depends_on={"primary_provider": "custom"},
            ),
            ConfigField(
                key="custom_portal_user",
                label="Utilizador",
                type="text",
                depends_on={"primary_provider": "custom"},
            ),
            ConfigField(
                key="custom_portal_password",
                label="Password",
                type="password",
                depends_on={"primary_provider": "custom"},
            ),
            ConfigField(
                key="secondary_provider",
                label="Serviço Secundário (Opcional)",
                type="select",
                options=[
                    {"value": "none", "label": "Nenhum"},
                    {"value": "hcpro", "label": "HCPro"},
                    {"value": "decisoes_e_solucoes", "label": "Decisões e Soluções"},
                    {"value": "doutorfinancas", "label": "Doutor Finanças"},
                    {"value": "maxfinance", "label": "MaxFinance"},
                ],
                help_text="Serviço alternativo para comparação de propostas"
            ),
        ]
    },
    "settings": {
        "title": "Definições Gerais",
        "description": "Personalizar a aparência e comportamento do sistema",
        "fields": [
            ConfigField(
                key="company_name",
                label="Nome da Empresa",
                type="text",
                required=True,
            ),
            ConfigField(
                key="company_subtitle",
                label="Subtítulo",
                type="text",
            ),
            ConfigField(
                key="company_address",
                label="Morada da Empresa",
                type="text",
                help_text="Usada no template RGPD como {{MORADA_EMPRESA}}",
            ),
            ConfigField(
                key="company_phone",
                label="Telefone/Email da Empresa",
                type="text",
                help_text="Usada no template RGPD como {{CONTACTO_EMPRESA}}",
            ),
            ConfigField(
                key="primary_color",
                label="Cor Principal",
                type="text",
                placeholder="#0F766E",
                help_text="Código hexadecimal da cor"
            ),
            ConfigField(
                key="timezone",
                label="Fuso Horário",
                type="select",
                options=[
                    {"value": "Europe/Lisbon", "label": "Lisboa (Portugal)"},
                    {"value": "Europe/London", "label": "Londres (UK)"},
                    {"value": "Atlantic/Azores", "label": "Açores"},
                ],
            ),
            ConfigField(
                key="language",
                label="Idioma",
                type="select",
                options=[
                    {"value": "pt-PT", "label": "Português (Portugal)"},
                    {"value": "en-GB", "label": "English (UK)"},
                ],
            ),
            ConfigField(
                key="_divider_security",
                label="Segurança e Permissões",
                type="divider",
            ),
            ConfigField(
                key="allow_excel_export",
                label="Permitir Exportação para Excel (Global)",
                type="boolean",
                help_text="Quando desativado, os botões de exportação para Excel ficam ocultos para todos os utilizadores excepto Admin e CEO",
            ),
        ]
    },
    "document_recipients": {
        "title": "Destinatários de Documentação",
        "description": "Configurar balcões/bancos para envio de documentação de clientes",
        "fields": [
            ConfigField(
                key="enabled",
                label="Activar Envio de Documentação",
                type="boolean",
                help_text="Permitir envio de documentação para balcões"
            ),
            ConfigField(
                key="recipients",
                label="Lista de Destinatários (JSON)",
                type="textarea",
                placeholder='[{"name": "Millennium BCP", "email": "millennium@exemplo.pt", "active": true}, ...]',
                help_text="Lista de balcões/bancos em formato JSON. Cada entrada deve ter: name, email, active (true/false)"
            ),
            ConfigField(
                key="email_template",
                label="Template de Email",
                type="textarea",
                placeholder="Prezados,\n\nSegue em anexo a documentação do cliente {client_name}...",
                help_text="Template do email. Variáveis disponíveis: {client_name}, {client_nif}, {process_number}, {documents_list}"
            ),
            ConfigField(
                key="default_to",
                label="Destinatário TO (Email Principal)",
                type="text",
                placeholder="geral@powerealestate.pt",
                help_text="Email principal que aparecerá no campo TO"
            ),
            ConfigField(
                key="default_to_name",
                label="Nome do Destinatário TO",
                type="text",
                placeholder="Power Real Estate",
                help_text="Nome do destinatário principal"
            ),
            ConfigField(
                key="default_to_emails",
                label="Emails TO Múltiplos (JSON)",
                type="textarea",
                placeholder='["geral@powerealestate.pt", "geral@precisioncredito.pt"]',
                help_text="Lista de emails TO em formato JSON. Gerido automaticamente pelo formulário de Destinatários."
            ),
        ]
    },
    "dsti_analysis": {
        "title": "Análise DSTI Automática",
        "description": "Cálculo automático da taxa de esforço (DSTI) a partir dos dados extraídos pela IA. Sinaliza instantaneamente processos de alto risco.",
        "fields": [
            ConfigField(
                key="enabled",
                label="Activar Análise DSTI Automática",
                type="boolean",
                help_text="Calcula automaticamente o DSTI e mostra alertas de risco nos processos"
            ),
            ConfigField(
                key="high_risk_threshold",
                label="Limiar de Risco Elevado (%)",
                type="number",
                placeholder="40",
                help_text="DSTI acima deste valor é considerado de alto risco (default: 40%)"
            ),
            ConfigField(
                key="critical_risk_threshold",
                label="Limiar de Risco Crítico (%)",
                type="number",
                placeholder="50",
                help_text="DSTI acima deste valor ultrapassa o limite do Banco de Portugal (default: 50%)"
            ),
        ]
    },
    "auto_draft": {
        "title": "Rascunhos Automáticos de E-mails",
        "description": "Gerar automaticamente rascunhos de e-mails solicitando documentos em falta",
        "fields": [
            ConfigField(
                key="enabled",
                label="Activar Rascunhos Automáticos",
                type="boolean",
                help_text="Gera automaticamente rascunhos de e-mail quando documentos em falta são detetados pela IA"
            ),
            ConfigField(
                key="base_prompt",
                label="Prompt Base para IA",
                type="textarea",
                placeholder="Escreve um e-mail profissional em português...",
                help_text="Prompt utilizado pela IA para gerar o conteúdo do e-mail. Variáveis: {client_name}, {document_type}, {process_number}, {company_name}",
                depends_on={"enabled": True},
            ),
            ConfigField(
                key="eligible_doc_types",
                label="Tipos de Documento Elegíveis",
                type="text",
                placeholder="irs, recibo_vencimento, extrato_bancario, cc",
                help_text="Tipos de documento separados por vírgula que geram rascunhos automáticos quando em falta",
                depends_on={"enabled": True},
            ),
        ]
    },
    "audit_trail": {
        "title": "Auditoria (Audit Trail)",
        "description": "Configurar o sistema de registo de auditoria que rastreia todas as alterações aos dados",
        "fields": [
            ConfigField(
                key="enabled",
                label="Activar Audit Trail",
                type="boolean",
                help_text="Regista todas as alterações aos processos com detalhes (IP, origem, justificação)"
            ),
            ConfigField(
                key="log_ip_address",
                label="Registar Endereço IP",
                type="boolean",
                help_text="Inclui o endereço IP do utilizador nos registos de auditoria",
                depends_on={"enabled": True},
            ),
            ConfigField(
                key="log_ai_approvals",
                label="Registar Aprovações de IA",
                type="boolean",
                help_text="Regista quando um utilizador aprova ou rejeita sugestões de IA",
                depends_on={"enabled": True},
            ),
            ConfigField(
                key="require_reason_for_critical_fields",
                label="Exigir Justificação em Campos Críticos",
                type="boolean",
                help_text="Quando activo, alterações a campos críticos devem incluir justificação",
                depends_on={"enabled": True},
            ),
            ConfigField(
                key="critical_fields",
                label="Campos Críticos (JSON)",
                type="textarea",
                placeholder='["financial_data", "credit_data", "status"]',
                help_text="Lista JSON de campos que exigem justificação quando alterados",
                depends_on={"enabled": True},
            ),
            ConfigField(
                key="retention_days",
                label="Dias de Retenção",
                type="number",
                placeholder="365",
                help_text="Número de dias para manter os registos de auditoria (default: 365)",
                depends_on={"enabled": True},
            ),
        ]
    },
}


SENSITIVE_FIELDS = [
    "aws_secret_access_key", "onedrive_client_secret", "google_client_secret",
    "dropbox_app_secret", "smtp_password", "imap_password",
    "smtp_password_2", "imap_password_2",
    "api_key", "api_token", "dropbox_access_token",
    "hcpro_password", "decisoes_password", "doutorfinancas_password", "custom_portal_password",
    "resend_api_key", "app_password",  # system_smtp + system_webmail
]

EXTRA_SECTIONS = {"system_smtp", "system_webmail", "mandatory_documents"}


def mask_sensitive(obj, parent_key=""):
    """Mascara campos sensíveis de um dicionário de configuração.

    Substitui valores de campos sensíveis (API keys, tokens, passwords)
    por "••••••••" antes de devolver ao frontend, para evitar
    exposição de credenciais em respostas HTTP.

    A recursão permite mascarar campos em dicionários aninhados.

    Args:
        obj: Dicionário a mascarar (modificado in-place).
        parent_key: Chave do pai (para logging, não usado na lógica).

    Returns:
        dict: Mesmo dicionário com valores sensíveis mascarados.
    """
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in SENSITIVE_FIELDS and value:
                obj[key] = "••••••••" if value else None
            elif isinstance(value, dict):
                mask_sensitive(value, key)
    return obj


async def run_get_config(company_id: Optional[str] = "default") -> dict:
    """Obter todas as configurações do sistema (mascaradas) + fields."""
    config = await get_system_config(company_id)
    config_dict = config.model_dump()
    masked_config = mask_sensitive(config_dict)
    return {
        "config": masked_config,
        "fields": CONFIG_FIELDS,
    }


async def run_get_excel_export_permission(company_id: Optional[str] = "default") -> dict:
    """Verificar se a exportação para Excel está permitida."""
    config = await get_system_config(company_id)
    return {"allow_excel_export": config.settings.allow_excel_export}


async def run_get_config_fields() -> dict:
    """Obter definição dos campos de configuração."""
    return CONFIG_FIELDS


async def run_get_available_companies() -> dict:
    """Listar empresas com configuração própria no sistema."""
    companies = await list_available_companies()
    return {"companies": companies, "total": len(companies)}


async def run_update_config(
    section: str,
    data: Dict[str, Any],
    company_id: Optional[str] = "default",
    user: Optional[dict] = None,
) -> dict:
    """Actualizar uma secção da configuração."""
    if section not in CONFIG_FIELDS and section not in EXTRA_SECTIONS:
        raise HTTPException(status_code=400, detail=f"Secção inválida: {section}")

    try:
        await update_config_section(section, data, company_id)
        email = (user or {}).get("email")
        logger.info(f"Configuração '{section}' actualizada por {email} (company_id={company_id})")
        return {
            "success": True,
            "message": f"Configuração '{section}' actualizada com sucesso",
            "section": section,
        }
    except Exception as e:
        logger.error(f"Erro ao actualizar configuração '{section}': {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
