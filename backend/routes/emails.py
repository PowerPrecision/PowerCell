"""
====================================================================
ROTAS DE EMAILS - POWERCELL
====================================================================
Endpoints para gestão de histórico de emails.

FEATURES:
- Visualização de anexos (preview, download)
- Filtros avançados (por data, por conta, por tipo)
- Marcação de emails (importante, lido, etc.)
- Templates de resposta rápida
- Timeline de emails no processo
- Notificações de novos emails
====================================================================
"""

import logging
import asyncio
from typing import Optional, List
from datetime import datetime, timezone, timedelta
import uuid
import base64

from fastapi import APIRouter, Depends, HTTPException, Query, Body, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import Response
import re

from database import db
from models.email import (
    EmailCreate, EmailUpdate, EmailResponse, EmailDirection, EmailStatus,
    EmailMarkType, EmailTemplateCreate, EmailTemplateResponse, EmailFilter, EmailSendRequest,
    LabelCreateRequest, LabelUpdateRequest,
    FolderCreateRequest, FolderUpdateRequest
)
from services.auth import get_current_user
from services.email_service import sync_emails_for_process, send_email, test_email_connection, get_email_accounts, get_email_accounts_async, sync_webmail_emails
from services.email_draft_service import (
    get_pending_drafts,
    get_draft_stats,
    update_draft,
    send_draft,
    discard_draft,
    create_missing_doc_draft,
    batch_create_missing_doc_drafts,
)
from utils.input_sanitization import sanitize_string, sanitize_name, sanitize_email, sanitize_html, sanitize_url, log_sanitization_rejection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emails", tags=["Emails"])

# NOTA: doc_router foi removido. Os endpoints send-documentation e document-recipients
# estão agora registados no router principal ANTES das rotas com /{email_id}.
# Isto resolve o bug 404 que ocorria quando a ordem de montagem dos routers
# no server.py causava conflitos com o catch-all /{email_id}.
doc_router = None  # Mantido como None para compatibilidade com server.py

# Armazenar status de sincronizações em progresso
_sync_status = {}


def _extract_email_variables(process: dict, user: dict, documents_list: str) -> dict:
    """
    Extrai todas as variáveis disponíveis para uso em templates de email,
    agregando dados de múltiplas secções do processo num dicionário plano.

    Porquê centralizar a extração: o mesmo conjunto de variáveis é usado
    pelo preview, pelo envio, e por templates personalizados. Centralizar
    evita duplicação de lógica e garante consistência entre preview e envio.

    Inclui formatação automática de moeda (pt-PT), datas (DD/MM/AAAA),
    mapeamento de vínculos laborais e estado civil/regime de casamento.

    Args:
        process: Documento do processo da MongoDB contendo personal_data,
            titular2_data, financial_data e real_estate_data.
        user: Dicionário do utilizador autenticado (para dados do remetente).
        documents_list: String com lista de documentos (\n separados).

    Returns:
        dict: Variáveis para substituição em templates, incluindo:
            - Dados básicos (client_name, process_number, documents_list).
            - 1º proponente (p1_nome, p1_nif, p1_salario, etc.).
            - 2º proponente (p2_nome, p2_email, etc.).
            - Crédito (banco_atual, montante_divida, etc.).
            - Remetente (sender_name, sender_email, sender_phone).
    """
    personal_data = process.get("personal_data", {}) or {}
    titular2_data = process.get("titular2_data", {}) or {}
    financial_data = process.get("financial_data", {}) or {}
    real_estate_data = process.get("real_estate_data", {}) or {}

    # Helper para formatação segura
    def safe_val(value, default="N/A"):
        """Retorna uma representação segura de um valor para templates.

        Converte o valor para string; se for None ou vazio, retorna
        o valor padrão. Evita erros de template ao aceder a campos
        opcionais do processo que podem não existir.

        Args:
            value: Valor a formatar (qualquer tipo).
            default: Texto alternativo quando valor é nulo/vazio.

        Returns:
            str: Valor formatado ou default.
        """
        if value is None or value == "":
            return default
        return str(value)

    def format_currency(value):
        """Formata um valor numérico como moeda europeia (pt-PT).

        Exemplo: 150000.50 → "150.000,50 €".

        Args:
            value: Valor numérico (int, float, str conversível).

        Returns:
            str: Valor formatado como moeda, ou "N/A" se inválido.
        """
        if value is None or value == "":
            return "N/A"
        try:
            return f"{float(value):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
        except (ValueError, TypeError):
            return str(value)

    def format_date(date_str):
        """Converte uma data ISO (AAAA-MM-DD) para formato pt-PT (DD/MM/AAAA).

        Também aceita datas com componente de tempo (T) e as
        trunca antes de converter.

        Args:
            date_str: String de data em formato ISO ou parcial.

        Returns:
            str: Data em formato DD/MM/AAAA, ou valor original se
                não for possível converter.
        """
        if not date_str:
            return "N/A"
        try:
            if "T" in date_str:
                date_str = date_str.split("T")[0]
            parts = date_str.split("-")
            if len(parts) == 3:
                return f"{parts[2]}/{parts[1]}/{parts[0]}"
            return date_str
        except:
            return date_str
    
    # 1º Proponente
    p1_nome = safe_val(personal_data.get("nome_completo") or personal_data.get("nome") or process.get("client_name"))
    p1_email = safe_val(personal_data.get("email") or process.get("client_email"))
    p1_telefone = safe_val(personal_data.get("telefone") or personal_data.get("phone") or process.get("client_phone"))
    p1_data_nascimento = format_date(personal_data.get("birth_date") or personal_data.get("data_nascimento"))
    p1_tipo_doc = safe_val(personal_data.get("documento_id"))
    p1_nif = safe_val(personal_data.get("nif") or process.get("client_nif"))
    
    # Estado civil e regime
    estado_civil_raw = personal_data.get("estado_civil", "")
    regime_casamento = ""
    if estado_civil_raw:
        if "_" in estado_civil_raw:
            parts = estado_civil_raw.split("_", 1)
            p1_estado_civil = parts[0].capitalize()
            if len(parts) > 1:
                regime_map = {
                    "adquiridos": "Comunhão de Adquiridos",
                    "geral": "Comunhão Geral de Bens",
                    "separacao": "Separação de Bens"
                }
                regime_casamento = regime_map.get(parts[1], parts[1].replace("_", " ").title())
        else:
            p1_estado_civil = estado_civil_raw.capitalize()
    else:
        p1_estado_civil = "N/A"
    p1_regime_casamento = regime_casamento if regime_casamento else "N/A"
    
    p1_profissao = safe_val(personal_data.get("profissao"))
    
    # Vínculo laboral
    vinculo_raw = personal_data.get("tipo_contrato") or financial_data.get("employment_type") or personal_data.get("vinculo_laboral")
    vinculo_map = {
        "efetivo": "Contrato Efetivo",
        "termo_certo": "Contrato a Termo Certo",
        "termo_incerto": "Contrato a Termo Incerto",
        "verde": "Recibos Verdes",
        "autonomo": "Trabalhador Independente",
        "empresario": "Empresário",
        "reformado": "Reformado",
        "desempregado": "Desempregado"
    }
    p1_vinculo = vinculo_map.get(vinculo_raw, safe_val(vinculo_raw, "N/A"))
    
    p1_salario = format_currency(personal_data.get("salario_liquido") or financial_data.get("monthly_income"))
    p1_dependentes = safe_val(personal_data.get("dependentes") or personal_data.get("num_dependentes"))
    p1_despesas = format_currency(personal_data.get("despesas_mensais") or financial_data.get("despesas_mensais"))
    
    # Situação bancária
    situacao_bancaria = []
    if financial_data.get("tem_creditos_activos"):
        situacao_bancaria.append("Tem créditos ativos")
    if personal_data.get("insolvencia") or financial_data.get("insolvencia"):
        situacao_bancaria.append("Insolvência")
    if personal_data.get("incumprimento") or financial_data.get("incumprimento"):
        situacao_bancaria.append("Incumprimento")
    p1_situacao_bancaria = ", ".join(situacao_bancaria) if situacao_bancaria else "Sem situações registadas"
    
    # 2º Proponente
    p2_nome = safe_val(titular2_data.get("name") or titular2_data.get("nome"), "Não aplicável")
    p2_email = safe_val(titular2_data.get("email"), "Não aplicável")
    p2_telefone = safe_val(titular2_data.get("phone") or titular2_data.get("telefone"), "Não aplicável")
    
    has_second_proponent = bool(titular2_data.get("name") or titular2_data.get("nome"))
    
    # Dados do Crédito Atual
    banco_atual = safe_val(financial_data.get("banco_atual") or financial_data.get("banco_credito"))
    num_titulares = 2 if has_second_proponent else 1
    
    contrato_mais_2_anos = safe_val(financial_data.get("contrato_mais_2_anos"), "N/A")
    if contrato_mais_2_anos == True or contrato_mais_2_anos == "true" or contrato_mais_2_anos == "sim":
        contrato_mais_2_anos = "Sim"
    elif contrato_mais_2_anos == False or contrato_mais_2_anos == "false" or contrato_mais_2_anos == "nao":
        contrato_mais_2_anos = "Não"
    
    valor_aquisicao = format_currency(financial_data.get("valor_aquisicao") or real_estate_data.get("valor_imovel"))
    montante_divida = format_currency(financial_data.get("montante_divida") or financial_data.get("valor_em_divida"))
    
    # Dados da Transferência Pretendida
    valor_extra = format_currency(financial_data.get("valor_extra") or financial_data.get("valor_multiopcoes"))
    localidade_imovel = safe_val(real_estate_data.get("localizacao") or real_estate_data.get("localidade"))
    
    possibilidade_fiador = safe_val(financial_data.get("fiador") or financial_data.get("tem_fiador"), "N/A")
    if possibilidade_fiador == True or possibilidade_fiador == "true" or possibilidade_fiador == "sim":
        possibilidade_fiador = "Sim"
    elif possibilidade_fiador == False or possibilidade_fiador == "false" or possibilidade_fiador == "nao":
        possibilidade_fiador = "Não"
    
    # Retornar todas as variáveis
    return {
        # Dados básicos
        "client_name": process.get("client_name", "N/A"),
        "client_nif": p1_nif,
        "process_number": process.get("process_number", "N/A"),
        "documents_list": documents_list,
        
        # 1º Proponente
        "p1_nome": p1_nome,
        "p1_email": p1_email,
        "p1_telefone": p1_telefone,
        "p1_data_nascimento": p1_data_nascimento,
        "p1_tipo_doc": p1_tipo_doc,
        "p1_nif": p1_nif,
        "p1_estado_civil": p1_estado_civil,
        "p1_regime_casamento": p1_regime_casamento,
        "p1_profissao": p1_profissao,
        "p1_vinculo": p1_vinculo,
        "p1_salario": p1_salario,
        "p1_dependentes": p1_dependentes,
        "p1_despesas": p1_despesas,
        "p1_situacao_bancaria": p1_situacao_bancaria,
        
        # 2º Proponente
        "p2_nome": p2_nome,
        "p2_email": p2_email,
        "p2_telefone": p2_telefone,
        
        # Crédito Atual
        "banco_atual": banco_atual,
        "num_titulares": num_titulares,
        "contrato_mais_2_anos": contrato_mais_2_anos,
        "valor_aquisicao": valor_aquisicao,
        "montante_divida": montante_divida,
        
        # Transferência Pretendida
        "valor_extra": valor_extra,
        "localidade_imovel": localidade_imovel,
        "possibilidade_fiador": possibilidade_fiador,
        
        # Remetente
        "sender_name": user.get("name", ""),
        "sender_email": user.get("email", ""),
        "sender_phone": user.get("phone", ""),
    }


def _build_professional_email_html(process: dict, user: dict, documents_list: str) -> str:
    """
    Constrói o corpo do email em HTML profissional para envio de
    documentação B2B a balcões bancários e parceiros de crédito.

    Porquê HTML formatado: os parceiros bancários esperam dados
    estruturados em tabelas, não texto corrido. O HTML profissional
    transmite credibilidade e facilita a leitura dos dados do crédito
    pelo destinatário (nome, NIF, vínculo, salário, situação bancária).

    Extraí dados do 1º e 2º proponente, dados financeiros do crédito
    atual e da transferência pretendida, e assinatura do consultor.

    Args:
        process: Documento do processo com personal_data, titular2_data,
            financial_data e real_estate_data.
        user: Dicionário do utilizador autenticado (nome, email, telefone).
        documents_list: String com lista de documentos anexados.

    Returns:
        str: Corpo HTML formatado pronto para envio.
    """
    personal_data = process.get("personal_data", {}) or {}
    titular2_data = process.get("titular2_data", {}) or {}
    financial_data = process.get("financial_data", {}) or {}
    real_estate_data = process.get("real_estate_data", {}) or {}

    # Helper para formatação segura (mesma lógica de _extract_email_variables)
    def safe_val(value, default="N/A"):
        """Retorna uma representação segura de um valor para templates.

        Ver documentação em ``_extract_email_variables`` para detalhes.
        """
        if value is None or value == "":
            return default
        return str(value)

    def format_currency(value):
        """Formata um valor numérico como moeda europeia (pt-PT).

        Ver documentação em ``_extract_email_variables`` para detalhes.
        """
        if value is None or value == "":
            return "N/A"
        try:
            return f"{float(value):,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")
        except (ValueError, TypeError):
            return str(value)

    def format_date(date_str):
        """Converte uma data ISO (AAAA-MM-DD) para formato pt-PT (DD/MM/AAAA).

        Ver documentação em ``_extract_email_variables`` para detalhes.
        """
        if not date_str:
            return "N/A"
        try:
            # Tentar formato ISO
            if "T" in date_str:
                date_str = date_str.split("T")[0]
            parts = date_str.split("-")
            if len(parts) == 3:
                return f"{parts[2]}/{parts[1]}/{parts[0]}"
            return date_str
        except:
            return date_str
    
    # ==== 1º PROPONENTE ====
    p1_nome = safe_val(personal_data.get("nome_completo") or personal_data.get("nome") or process.get("client_name"))
    p1_email = safe_val(personal_data.get("email") or process.get("client_email"))
    p1_telefone = safe_val(personal_data.get("telefone") or personal_data.get("phone") or process.get("client_phone"))
    p1_data_nascimento = format_date(personal_data.get("birth_date") or personal_data.get("data_nascimento"))
    p1_tipo_doc = safe_val(personal_data.get("documento_id"), "N/A")
    p1_nif = safe_val(personal_data.get("nif") or process.get("client_nif"))
    
    # Estado civil e regime
    estado_civil_raw = personal_data.get("estado_civil", "")
    regime_casamento = ""
    if estado_civil_raw:
        if "_" in estado_civil_raw:
            parts = estado_civil_raw.split("_", 1)
            p1_estado_civil = parts[0].capitalize()
            if len(parts) > 1:
                regime_map = {
                    "adquiridos": "Comunhão de Adquiridos",
                    "geral": "Comunhão Geral de Bens",
                    "separacao": "Separação de Bens"
                }
                regime_casamento = regime_map.get(parts[1], parts[1].replace("_", " ").title())
        else:
            p1_estado_civil = estado_civil_raw.capitalize()
    else:
        p1_estado_civil = "N/A"
    p1_regime_casamento = regime_casamento if regime_casamento else "N/A"
    
    p1_profissao = safe_val(personal_data.get("profissao"))
    
    # Vínculo laboral
    vinculo_raw = personal_data.get("tipo_contrato") or financial_data.get("employment_type") or personal_data.get("vinculo_laboral")
    vinculo_map = {
        "efetivo": "Contrato Efetivo",
        "termo_certo": "Contrato a Termo Certo",
        "termo_incerto": "Contrato a Termo Incerto",
        "verde": "Recibos Verdes",
        "autonomo": "Trabalhador Independente",
        "empresario": "Empresário",
        "reformado": "Reformado",
        "desempregado": "Desempregado"
    }
    p1_vinculo = vinculo_map.get(vinculo_raw, safe_val(vinculo_raw, "N/A"))
    
    p1_salario = format_currency(personal_data.get("salario_liquido") or financial_data.get("monthly_income"))
    p1_dependentes = safe_val(personal_data.get("dependentes") or personal_data.get("num_dependentes"))
    p1_despesas = format_currency(personal_data.get("despesas_mensais") or financial_data.get("despesas_mensais"))
    
    # Situação bancária
    situacao_bancaria = []
    if financial_data.get("tem_creditos_activos"):
        situacao_bancaria.append("Tem créditos ativos")
    if personal_data.get("insolvencia") or financial_data.get("insolvencia"):
        situacao_bancaria.append("Insolvência")
    if personal_data.get("incumprimento") or financial_data.get("incumprimento"):
        situacao_bancaria.append("Incumprimento")
    p1_situacao_bancaria = ", ".join(situacao_bancaria) if situacao_bancaria else "Sem situações registadas"
    
    # ==== 2º PROPONENTE ====
    p2_nome = safe_val(titular2_data.get("name") or titular2_data.get("nome"), "")
    p2_email = safe_val(titular2_data.get("email"), "")
    p2_telefone = safe_val(titular2_data.get("phone") or titular2_data.get("telefone"), "")
    p2_data_nascimento = format_date(titular2_data.get("birth_date"))
    p2_tipo_doc = safe_val(titular2_data.get("documento_id"), "")
    p2_nif = safe_val(titular2_data.get("nif"), "")
    p2_estado_civil = safe_val(titular2_data.get("estado_civil"), "")
    if p2_estado_civil and "_" in p2_estado_civil:
        p2_estado_civil = p2_estado_civil.split("_")[0].capitalize()
    
    # Se não houver 2º proponente
    has_second_proponent = bool(p2_nome)
    
    # ==== DADOS DO CRÉDITO ATUAL ====
    banco_atual = safe_val(financial_data.get("banco_atual") or financial_data.get("banco_credito"))
    
    # Número de titulares
    num_titulares = 1
    if has_second_proponent:
        num_titulares = 2
    
    contrato_mais_2_anos = safe_val(financial_data.get("contrato_mais_2_anos"), "N/A")
    if contrato_mais_2_anos == True or contrato_mais_2_anos == "true" or contrato_mais_2_anos == "sim":
        contrato_mais_2_anos = "Sim"
    elif contrato_mais_2_anos == False or contrato_mais_2_anos == "false" or contrato_mais_2_anos == "nao":
        contrato_mais_2_anos = "Não"
    
    valor_aquisicao = format_currency(financial_data.get("valor_aquisicao") or real_estate_data.get("valor_imovel"))
    montante_divida = format_currency(financial_data.get("montante_divida") or financial_data.get("valor_em_divida"))
    
    # ==== DADOS DA TRANSFERÊNCIA PRETENDIDA ====
    valor_extra = format_currency(financial_data.get("valor_extra") or financial_data.get("valor_multiopcoes"))
    localidade_imovel = safe_val(real_estate_data.get("localizacao") or real_estate_data.get("localidade"))
    
    possibilidade_fiador = safe_val(financial_data.get("fiador") or financial_data.get("tem_fiador"), "N/A")
    if possibilidade_fiador == True or possibilidade_fiador == "true" or possibilidade_fiador == "sim":
        possibilidade_fiador = "Sim"
    elif possibilidade_fiador == False or possibilidade_fiador == "false" or possibilidade_fiador == "nao":
        possibilidade_fiador = "Não"
    
    # ==== ASSINATURA ====
    user_nome = safe_val(user.get("name"))
    user_telefone = safe_val(user.get("phone"))
    user_email = safe_val(user.get("email"))
    
    # ==== CONSTRUIR HTML ====
    # Secção do 2º proponente (sempre visível, mas com dados ou "Não aplicável")
    if has_second_proponent:
        segundo_proponente_html = f'''
    <h3 style="color: #1e3a8a; border-bottom: 2px solid #e5e7eb; padding-bottom: 5px; margin-top: 30px;">2º Proponente</h3>
    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
        <tr><td style="padding: 4px 0; width: 40%;"><strong>Nome:</strong></td><td>{p2_nome}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>E-mail:</strong></td><td>{p2_email}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Contacto:</strong></td><td>{p2_telefone}</td></tr>
    </table>'''
    else:
        segundo_proponente_html = '''
    <h3 style="color: #1e3a8a; border-bottom: 2px solid #e5e7eb; padding-bottom: 5px; margin-top: 30px;">2º Proponente</h3>
    <p style="color: #6b7280; font-style: italic;">Não aplicável</p>'''
    
    html = f'''<div style="font-family: 'Segoe UI', Arial, sans-serif; color: #333333; line-height: 1.6; max-width: 800px; margin: 0 auto;">
    <p>Estimado(a) Parceiro(a),</p>
    <p>Venho por este meio submeter o pedido de análise para <strong>Transferência de Crédito Habitação</strong>, relativamente ao(s) proponente(s) abaixo identificado(s).</p>

    <h3 style="color: #1e3a8a; border-bottom: 2px solid #e5e7eb; padding-bottom: 5px; margin-top: 30px;">1º Proponente</h3>
    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
        <tr><td style="padding: 4px 0; width: 40%;"><strong>Nome:</strong></td><td>{p1_nome}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>E-mail:</strong></td><td>{p1_email}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Contacto:</strong></td><td>{p1_telefone}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Data de Nascimento:</strong></td><td>{p1_data_nascimento}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Documento de Identificação:</strong></td><td>{p1_tipo_doc}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Contribuinte (NIF):</strong></td><td>{p1_nif}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Estado Civil:</strong></td><td>{p1_estado_civil}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Regime de Casamento:</strong></td><td>{p1_regime_casamento}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Profissão:</strong></td><td>{p1_profissao}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Vínculo Laboral:</strong></td><td>{p1_vinculo}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Salário Líquido:</strong></td><td>{p1_salario}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Dependentes:</strong></td><td>{p1_dependentes}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Despesas Mensais:</strong></td><td>{p1_despesas}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Situação bancária (Insolvência/Incumprimento):</strong></td><td>{p1_situacao_bancaria}</td></tr>
    </table>

    {segundo_proponente_html}

    <h3 style="color: #1e3a8a; border-bottom: 2px solid #e5e7eb; padding-bottom: 5px; margin-top: 30px;">Dados do Crédito Atual</h3>
    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
        <tr><td style="padding: 4px 0; width: 50%;"><strong>Banco atual:</strong></td><td>{banco_atual}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Nº de titulares do empréstimo:</strong></td><td>{num_titulares}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Contrato celebrado há mais de 2 anos:</strong></td><td>{contrato_mais_2_anos}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Valor de aquisição do imóvel:</strong></td><td>{valor_aquisicao}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Montante em dívida:</strong></td><td>{montante_divida}</td></tr>
    </table>

    <h3 style="color: #1e3a8a; border-bottom: 2px solid #e5e7eb; padding-bottom: 5px; margin-top: 30px;">Dados da Transferência Pretendida</h3>
    <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
        <tr><td style="padding: 4px 0; width: 50%;"><strong>Valor de multiopções/extra pretendido:</strong></td><td>{valor_extra}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Localidade do imóvel:</strong></td><td>{localidade_imovel}</td></tr>
        <tr><td style="padding: 4px 0;"><strong>Existe possibilidade de fiador?:</strong></td><td>{possibilidade_fiador}</td></tr>
    </table>
    
    <p style="margin-top: 30px; margin-bottom: 30px;">Estou ao dispor para qualquer esclarecimento.</p>

    <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">
    <div style="font-size: 14px; color: #4b5563;">
        <p style="margin: 2px 0;"><strong>{user_nome}</strong></p>
        <p style="margin: 2px 0;">Tlm: {user_telefone}</p>
        <p style="margin: 2px 0;">Email: {user_email}</p>
        <br>
        <p style="margin: 2px 0;"><strong>PrecisionCrédito</strong></p>
        <p style="margin: 2px 0;">Licença de Intermediação de Crédito nº 0005798AM</p>
    </div>
</div>'''
    
    return html


async def enrich_email(email: dict) -> dict:
    """Enriquece um registo de email com nomes de processo e criador.

    Adiciona ``client_name`` (nome do cliente do processo associado)
    e ``created_by_name`` (nome do utilizador que criou o email).

    Porquê este enriquecimento: a lista de emails no frontend precisa
    de mostrar nomes legíveis em vez de apenas IDs.

    Args:
        email: Dicionário do documento de email da MongoDB.

    Returns:
        dict: Mesmo dicionário com campos client_name e
            created_by_name adicionados (se encontrado).
    """
    # Nome do processo/cliente
    if email.get("process_id"):
        process = await db.processes.find_one(
            {"id": email["process_id"]},
            {"_id": 0, "client_name": 1}
        )
        if process:
            email["client_name"] = process.get("client_name", "")
    
    # Nome de quem criou
    if email.get("created_by"):
        user = await db.users.find_one(
            {"id": email["created_by"]},
            {"_id": 0, "name": 1}
        )
        if user:
            email["created_by_name"] = user.get("name", "")
    
    return email


# ==== DOCUMENT RECIPIENTS & SEND DOCUMENTATION (antes de /{email_id} para evitar conflito) ====

@router.get("/document-recipients")
async def get_document_recipients(
    current_user: dict = Depends(get_current_user)
):
    """
    Obter lista de destinatários disponíveis para envio de documentação.
    Apenas Admin e CEO podem editar as configurações.
    """
    from services.system_config import get_system_config
    
    config = await get_system_config()
    doc_config = config.document_recipients
    
    if not doc_config.enabled:
        return {
            "enabled": False,
            "recipients": [],
            "email_template": None,
            "default_to": None,
            "default_to_name": None,
            "default_to_emails": []
        }
    
    import json
    
    # Parse recipients JSON
    recipients = []
    if doc_config.recipients:
        try:
            recipients = json.loads(doc_config.recipients)
        except (json.JSONDecodeError, TypeError):
            recipients = []
    
    # Parse default_to_emails (múltiplos emails TO)
    default_to_emails = []
    if doc_config.default_to_emails:
        try:
            parsed = json.loads(doc_config.default_to_emails)
            if isinstance(parsed, list):
                default_to_emails = [e for e in parsed if e and "@" in str(e)]
        except (json.JSONDecodeError, TypeError):
            default_to_emails = []
    
    # Fallback: se default_to_emails está vazio mas default_to tem valor, usá-lo
    if not default_to_emails and doc_config.default_to and "@" in str(doc_config.default_to):
        default_to_emails = [doc_config.default_to]
    
    return {
        "enabled": True,
        "recipients": recipients,
        "email_template": doc_config.email_template,
        "default_to": doc_config.default_to,
        "default_to_name": doc_config.default_to_name,
        "default_to_emails": default_to_emails,
        "can_edit": current_user["role"] in ["admin", "ceo"]
    }


# ==== PREVIEW DOCUMENTATION (gera HTML sem enviar) ====

@router.get("/preview-documentation/{process_id}")
async def preview_documentation_email(
    process_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Gera e devolve o HTML final do email de documentação sem o enviar.

    Porquê um preview separado: permite ao consultor/admin visualizar
    exatamente o que o destinatário receberá, incluindo a renderização
    de variáveis com dados reais do cliente. Isto evita erros
    embaraçosos (dados errados, formatação quebrada) antes do envio.

    Suporta tanto o template personalizado da configuração como o
    template HTML profissional por defeito.

    Args:
        process_id: ID do processo cuja documentação será enviada.
        current_user: Utilizador autenticado (injetado pelo Depends).

    Returns:
        dict: Contém html (string), subject, template_vars, e
            available_variables (lista de chaves para documentação do template).

    Raises:
        HTTPException: 404 se processo não encontrado, 400 se envio
            de documentação não está ativado na configuração.
    """
    from services.system_config import get_system_config
    
    # Obter processo
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # Obter configuração
    config = await get_system_config()
    doc_config = config.document_recipients
    
    if not doc_config.enabled:
        raise HTTPException(status_code=400, detail="Envio de documentação não está activado")
    
    # Obter documentos do processo para incluir na lista
    documents = await db.document_metadata.find(
        {"process_id": process_id},
        {"_id": 0}
    ).to_list(100)
    
    # Preparar lista de documentos para o email
    documents_list = "\n".join([
        f"- {doc.get('original_name', doc.get('filename', 'Documento'))}" 
        for doc in documents
    ]) if documents else "Nenhum documento anexado"
    
    # Extrair dados para o email
    client_name = process.get("client_name", "N/A")
    personal_data = process.get("personal_data", {}) or {}
    client_nif = personal_data.get("nif", process.get("client_nif", "N/A"))
    process_number = process.get("process_number", "N/A")
    
    # Verificar se existe template personalizado na configuração
    email_template = doc_config.email_template
    
    # Extrair todas as variáveis disponíveis para templates
    template_vars = _extract_email_variables(process, current_user, documents_list)
    
    # Gerar HTML do email
    if email_template:
        # Usar template personalizado da configuração com todas as variáveis
        try:
            email_body = email_template.format(**template_vars)
        except KeyError as e:
            logger.warning(f"Variável não encontrada no template: {e}")
            # Fallback com variáveis básicas
            email_body = email_template.format(
                client_name=client_name,
                client_nif=client_nif,
                process_number=process_number,
                documents_list=documents_list,
                sender_name=current_user.get("name", ""),
                sender_email=current_user.get("email", "")
            )
    else:
        # Usar template HTML profissional por defeito
        email_body = _build_professional_email_html(process, current_user, documents_list)
    
    # Retornar o HTML gerado e as variáveis disponíveis
    return {
        "success": True,
        "html": email_body,
        "subject": f"Documentação - {client_name} (Processo #{process_number})",
        "template_vars": template_vars,
        "available_variables": list(template_vars.keys()),
        "documents_count": len(documents) if documents else 0
    }


# ==== SEND DOCUMENTATION (antes de /{email_id} para evitar conflito de rota) ====
# Estes endpoints devem estar ANTES das rotas com /{email_id} para que
# o FastAPI faça match correcto e não trate "send-documentation" como um email_id.

@router.post("/send-documentation/{process_id}")
async def send_documentation_email(
    process_id: str,
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Envia documentação do processo para balcões/bancos com anexos
    descarregados do S3 e validação de destinatários contra conflitos.

    Porquê a validação de destinatários: impede o envio acidental de
    documentação a bancos onde o cliente já tem conta ativa ou simulação
    em curso (conflito de interesse regulado por legislação bancária).

    A construção do corpo do email segue uma prioridade decrescente:
    1. custom_html_body (Rich Text Editor do admin/CEO).
    2. custom_message (texto com variáveis).
    3. email_template (template da configuração).
    4. Template HTML profissional por defeito.

    Args:
        process_id: ID do processo.
        data: Body com document_ids, s3_paths, bcc_recipients, cc_emails,
            custom_message, custom_html_body, to_emails.
        current_user: Utilizador autenticado (injetado pelo Depends).

    Returns:
        dict: Resultado do envio incluindo success, message, e warnings.

    Raises:
        HTTPException: 404 se processo não encontrado, 400 se parâmetros
            inválidos, 500 se falha no envio de email.
    """
    from services.system_config import get_system_config
    
    # Obter processo
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # Obter configuração
    config = await get_system_config()
    doc_config = config.document_recipients
    
    if not doc_config.enabled:
        raise HTTPException(status_code=400, detail="Envio de documentação não está activado")
    
    # Dados do request - aceitar document_ids E/OU s3_paths
    document_ids = data.get("document_ids", [])
    s3_paths = data.get("s3_paths", [])
    # Sanitize email addresses from user input
    bcc_recipients = [e for e in (sanitize_email(e) for e in data.get("bcc_recipients", [])) if e]
    cc_emails = [e for e in (sanitize_email(e) for e in data.get("cc_emails", [])) if e]
    custom_message = data.get("custom_message")
    
    # NOVO: custom_html_body - HTML já formatado pelo Rich Text Editor
    # Este campo tem PRIORIDADE MÁXIMA - é usado diretamente sem processamento
    custom_html_body = data.get("custom_html_body")
    
    # TO emails: usar os selecionados pelo utilizador, ou fallback para config
    request_to_emails = [e for e in (sanitize_email(e) for e in data.get("to_emails", [])) if e]
    
    if not document_ids and not s3_paths:
        raise HTTPException(status_code=400, detail="Selecione pelo menos um documento")
    
    if not bcc_recipients:
        raise HTTPException(status_code=400, detail="Selecione pelo menos um destinatário")
    
    # Validar destinatários contra contas ativas e simulações
    financial_data = process.get("financial_data", {}) or {}
    bancos_creditos = financial_data.get("bancos_creditos", []) or []
    bancos_simulacoes = financial_data.get("bancos_simulacoes", []) or []
    
    def normalize_bank_name(name):
        """Normaliza o nome de um banco para comparação case-insensitive.

        Remove espaços e converte para minúsculas para permitir
        comparação fiável entre nomes de bancos dos destinatários
        e a lista de bancos com crédito/simulação do cliente.

        Args:
            name: Nome do banco (str ou None).

        Returns:
            str: Nome normalizado em minúsculas sem espaços nas
                extremidades, ou string vazia se name for falsy.
        """
        return name.lower().strip() if name else ""
    
    blocked_banks = [normalize_bank_name(b) for b in bancos_creditos + bancos_simulacoes]
    
    # Parse recipients para validar
    recipients_list = []
    if doc_config.recipients:
        try:
            import json
            recipients_list = json.loads(doc_config.recipients)
        except (json.JSONDecodeError, TypeError):
            pass
    
    # Validar cada BCC recipient
    validated_bcc = []
    warnings = []
    
    for bcc_email in bcc_recipients:
        recipient_info = next(
            (r for r in recipients_list if r.get("email", "").lower() == bcc_email.lower()),
            {"name": bcc_email, "email": bcc_email}
        )
        
        recipient_name = normalize_bank_name(recipient_info.get("name", ""))
        is_blocked = any(blocked in recipient_name or recipient_name in blocked for blocked in blocked_banks)
        
        if is_blocked:
            warnings.append(f"⚠️ {recipient_info.get('name', bcc_email)}: Cliente tem conta ativa ou simulação neste banco")
        else:
            validated_bcc.append(bcc_email)
    
    if warnings:
        logger.warning(f"Destinatários bloqueados para processo {process_id}: {warnings}")
    
    if not validated_bcc:
        raise HTTPException(
            status_code=400, 
            detail="Nenhum destinatário válido. O cliente tem contas ativas ou simulações em todos os bancos selecionados."
        )
    
    # Obter documentos da coleção document_metadata (onde são guardados)
    documents = []
    if document_ids:
        metadata_docs = await db.document_metadata.find(
            {"id": {"$in": document_ids}},
            {"_id": 0}
        ).to_list(100)
        documents.extend(metadata_docs)
    
    # Complementar com documentos por s3_path (fallback para docs S3-only)
    if s3_paths:
        existing_paths = {d.get("s3_path") for d in documents if d.get("s3_path")}
        paths_to_lookup = [p for p in s3_paths if p not in existing_paths]
        if paths_to_lookup:
            s3_docs = await db.document_metadata.find(
                {"s3_path": {"$in": paths_to_lookup}},
                {"_id": 0}
            ).to_list(100)
            documents.extend(s3_docs)
            # Marcar paths que NÃO estão em document_metadata
            found_paths = {d.get("s3_path") for d in s3_docs}
            for path in paths_to_lookup:
                if path not in found_paths:
                    # Documento existe no S3 mas não em metadados — criar entrada mínima
                    filename = path.rsplit("/", 1)[-1] if "/" in path else path
                    documents.append({
                        "id": str(uuid.uuid4()),
                        "filename": filename,
                        "original_name": filename,
                        "s3_path": path,
                        "content_type": None
                    })
    
    if not documents:
        raise HTTPException(status_code=404, detail="Nenhum documento encontrado")
    
    # Preparar lista de documentos para o email
    documents_list = "\n".join([
        f"- {doc.get('original_name', doc.get('filename', 'Documento'))}" 
        for doc in documents
    ])
    
    # Extrair dados para o email
    client_name = process.get("client_name", "N/A")
    personal_data = process.get("personal_data", {}) or {}
    client_nif = personal_data.get("nif", process.get("client_nif", "N/A"))
    process_number = process.get("process_number", "N/A")
    
    # Verificar se existe template personalizado na configuração
    email_template = doc_config.email_template
    
    # Extrair todas as variáveis disponíveis para templates
    template_vars = _extract_email_variables(process, current_user, documents_list)
    
    # ============================================================
    # CONSTRUÇÃO DO CORPO DO EMAIL (prioridade decrescente)
    # ============================================================
    # 1. custom_html_body: HTML já formatado pelo Rich Text Editor
    #    (PRIORIDADE MÁXIMA - usado diretamente, sem sanitização de variáveis)
    # 2. custom_message: mensagem de texto do admin/CEO (com substituição de variáveis)
    # 3. email_template: template personalizado da configuração
    # 4. template HTML profissional por defeito
    # ============================================================
    
    if custom_html_body and current_user["role"] in ["admin", "ceo"]:
        # USAR HTML CUSTOMIZADO DO EDITOR WYSIWYG
        # Sanitizar para segurança (remover scripts perigosos)
        email_body = sanitize_html(custom_html_body)
        logger.info(f"Usando custom_html_body do Rich Text Editor para processo {process_id}")
    
    elif custom_message and current_user["role"] in ["admin", "ceo"]:
        custom_message = sanitize_string(custom_message, max_length=10000)
        try:
            email_body = custom_message.format(**template_vars)
        except KeyError as e:
            logger.warning(f"Variável não encontrada no custom_message: {e}")
            email_body = custom_message.format(
                client_name=client_name,
                client_nif=client_nif,
                process_number=process_number,
                documents_list=documents_list,
                sender_name=current_user.get("name", ""),
                sender_email=current_user.get("email", "")
            )
    elif email_template:
        # Usar template personalizado da configuração com todas as variáveis
        try:
            email_body = email_template.format(**template_vars)
        except KeyError as e:
            logger.warning(f"Variável não encontrada no template: {e}")
            # Fallback com variáveis básicas
            email_body = email_template.format(
                client_name=client_name,
                client_nif=client_nif,
                process_number=process_number,
                documents_list=documents_list,
                sender_name=current_user.get("name", ""),
                sender_email=current_user.get("email", "")
            )
    else:
        # Usar template HTML profissional por defeito
        email_body = _build_professional_email_html(process, current_user, documents_list)
    
    # Preparar destinatários TO (suporta múltiplos emails)
    # Prioridade: emails selecionados pelo utilizador > config > fallback
    to_emails = []
    if request_to_emails:
        to_emails = request_to_emails
    elif doc_config.default_to_emails:
        try:
            import json
            parsed_to = json.loads(doc_config.default_to_emails)
            if isinstance(parsed_to, list):
                to_emails = [e for e in parsed_to if e and "@" in str(e)]
        except (json.JSONDecodeError, TypeError):
            pass
    # Fallback para default_to singular (compatibilidade)
    if not to_emails and doc_config.default_to and "@" in str(doc_config.default_to):
        to_emails = [doc_config.default_to]
    # Último fallback: email do utilizador actual
    if not to_emails:
        to_emails = [current_user["email"]]
    subject = f"Documentação - {client_name} (Processo #{process_number})"
    
    # ==== PREPARAR ANEXOS (download do S3) ====
    email_attachments = []
    failed_attachments = []
    for doc in documents:
        filename = doc.get("original_name", doc.get("filename", "documento"))
        s3_path = doc.get("s3_path") or doc.get("path")
        
        if s3_path:
            try:
                from services.s3_storage import s3_service
                loop = asyncio.get_event_loop()
                content_bytes = await loop.run_in_executor(
                    None, lambda p=s3_path: s3_service.get_file_content(p)
                )
                if content_bytes:
                    email_attachments.append({
                        "filename": filename,
                        "content_bytes": content_bytes,
                        "content_type": doc.get("content_type") or doc.get("mime_type")
                    })
                    logger.info(f"Anexo preparado: {filename} ({len(content_bytes)} bytes)")
                else:
                    failed_attachments.append(filename)
                    logger.warning(f"Falha ao descarregar anexo do S3: {s3_path}")
            except Exception as e:
                failed_attachments.append(filename)
                logger.error(f"Erro ao descarregar anexo {filename} do S3: {e}")
        else:
            failed_attachments.append(filename)
            logger.warning(f"Documento sem s3_path: {filename}")
    
    if failed_attachments:
        warnings.append(f"⚠️ {len(failed_attachments)} documento(s) não puderam ser anexados: {', '.join(failed_attachments)}")
    
    # ==== ENVIAR EMAIL COM ANEXOS ====
    # Gerar versão plain-text a partir do HTML (strip tags) como fallback
    import re
    plain_text_body = re.sub(r'<[^>]+>', '', email_body).strip()
    plain_text_body = re.sub(r'\n{3,}', '\n\n', plain_text_body)
    
    result = await send_email(
        account_name="power",
        to_emails=to_emails,
        subject=subject,
        body=plain_text_body,
        body_html=email_body,
        cc_emails=cc_emails if cc_emails else None,
        bcc_emails=validated_bcc,
        process_id=process_id,
        created_by=current_user["id"],
        attachments=email_attachments if email_attachments else None
    )
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Erro ao enviar email"))
    
    # NOTA: O registo no histórico já é feito pelo send_email() internamente.
    # Adicionar label "documentação" ao registo criado pelo send_email
    try:
        await db.emails.update_one(
            {"process_id": process_id, "created_by": current_user["id"], "direction": "sent"},
            {"$set": {
                "is_important": False,
                "is_read": True,
                "is_starred": False,
                "is_archived": False,
            },
            "$addToSet": {"labels": "documentação"}},
            sort=[("sent_at", -1)]
        )
    except Exception as e:
        logger.warning(f"Não foi possível adicionar label 'documentação' ao registo: {e}")
    
    logger.info(f"Documentação enviada para processo {process_id} por {current_user['email']}: {len(validated_bcc)} destinatários, {len(email_attachments)} anexos")
    
    return {
        "success": True,
        "message": f"Documentação enviada com sucesso para {len(validated_bcc)} destinatário(s) ({len(email_attachments)} anexo(s))",
        "warnings": warnings,
        "sent_to": validated_bcc,
        "attachments_sent": len(email_attachments),
        "attachments_failed": len(failed_attachments) if failed_attachments else 0
    }


# ==== LABELS CRUD (user-level labels) ====

DEFAULT_LABELS = [
    {"name": "Urgente", "color": "#ef4444"},
    {"name": "A Aguardar", "color": "#f59e0b"},
    {"name": "Concluído", "color": "#22c55e"},
    {"name": "Follow-up", "color": "#3b82f6"},
    {"name": "Reunião", "color": "#8b5cf6"},
]


def _validate_hex_color(color: str) -> bool:
    """Validate hex color format like #e74c3c or #fff."""
    return bool(re.match(r'^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$', color))


@router.get("/labels")
async def list_labels(
    current_user: dict = Depends(get_current_user)
):
    """Listar todas as labels do utilizador. Cria labels predefinidas na primeira chamada."""
    user_id = current_user["id"]
    existing = await db.email_labels.find(
        {"user_id": user_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(100)

    # Seed default labels on first access
    if not existing:
        now = datetime.now(timezone.utc).isoformat()
        for label_def in DEFAULT_LABELS:
            await db.email_labels.insert_one({
                "id": str(uuid.uuid4()),
                "name": label_def["name"],
                "color": label_def["color"],
                "user_id": user_id,
                "created_at": now,
            })
        existing = await db.email_labels.find(
            {"user_id": user_id}, {"_id": 0}
        ).sort("created_at", 1).to_list(100)

    return {"labels": existing}


@router.post("/labels")
async def create_label(
    payload: LabelCreateRequest,
    current_user: dict = Depends(get_current_user)
):
    """Criar uma nova label."""
    user_id = current_user["id"]
    name = sanitize_string(payload.name.strip(), max_length=30)
    color = payload.color.strip()

    if not name:
        raise HTTPException(status_code=400, detail="Nome da label é obrigatório")
    if not _validate_hex_color(color):
        raise HTTPException(status_code=400, detail="Cor inválida. Use formato hexadecimal (ex: #ef4444)")

    # Check for duplicate name
    dup = await db.email_labels.find_one({"user_id": user_id, "name": name})
    if dup:
        raise HTTPException(status_code=409, detail="Já existe uma label com esse nome")

    label_doc = {
        "id": str(uuid.uuid4()),
        "name": name,
        "color": color,
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.email_labels.insert_one(label_doc)
    label_doc.pop("_id", None)

    logger.info(f"Label criada: {name} ({color}) por {current_user['email']}")
    return label_doc


@router.put("/labels/{label_id}")
async def update_label(
    label_id: str,
    payload: LabelUpdateRequest,
    current_user: dict = Depends(get_current_user)
):
    """Atualizar nome e/ou cor de uma label."""
    user_id = current_user["id"]
    label = await db.email_labels.find_one({"id": label_id, "user_id": user_id})
    if not label:
        raise HTTPException(status_code=404, detail="Label não encontrada")

    update_data = {}
    if payload.name is not None:
        new_name = sanitize_string(payload.name.strip(), max_length=30)
        if not new_name:
            raise HTTPException(status_code=400, detail="Nome da label é obrigatório")
        # Check duplicate name (excluding current label)
        dup = await db.email_labels.find_one({"user_id": user_id, "name": new_name, "id": {"$ne": label_id}})
        if dup:
            raise HTTPException(status_code=409, detail="Já existe uma label com esse nome")
        update_data["name"] = new_name
    if payload.color is not None:
        color = payload.color.strip()
        if not _validate_hex_color(color):
            raise HTTPException(status_code=400, detail="Cor inválida. Use formato hexadecimal (ex: #ef4444)")
        update_data["color"] = color

    if update_data:
        await db.email_labels.update_one({"id": label_id}, {"$set": update_data})

    updated = await db.email_labels.find_one({"id": label_id}, {"_id": 0})
    logger.info(f"Label {label_id} atualizada por {current_user['email']}")
    return updated


@router.delete("/labels/{label_id}")
async def delete_label(
    label_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Eliminar label e remover de todos os emails do utilizador."""
    user_id = current_user["id"]
    label = await db.email_labels.find_one({"id": label_id, "user_id": user_id})
    if not label:
        raise HTTPException(status_code=404, detail="Label não encontrada")

    label_name = label["name"]

    # Remove label from all emails
    await db.emails.update_many(
        {"labels": label_name},
        {"$pull": {"labels": label_name}}
    )

    # Delete label document
    await db.email_labels.delete_one({"id": label_id})

    logger.info(f"Label '{label_name}' ({label_id}) eliminada por {current_user['email']}")
    return {"success": True, "message": f"Label '{label_name}' eliminada"}


# ==== FOLDERS CRUD (user-level custom folders) ====

DEFAULT_FOLDER_COLORS = [
    "#6b7280", "#ef4444", "#f59e0b", "#22c55e", "#3b82f6",
    "#8b5cf6", "#ec4899", "#14b8a6", "#f97316", "#6366f1"
]


@router.get("/folders")
async def list_folders(
    current_user: dict = Depends(get_current_user)
):
    """Listar todas as pastas personalizadas do utilizador."""
    user_id = current_user["id"]
    folders = await db.email_folders.find(
        {"user_id": user_id}, {"_id": 0}
    ).sort("created_at", 1).to_list(100)

    # Get email counts for each folder
    folder_ids = [f["id"] for f in folders]
    counts = {}
    if folder_ids:
        pipeline = [
            {"$match": {"folder_id": {"$in": folder_ids}, "is_archived": False}},
            {"$group": {"_id": "$folder_id", "count": {"$sum": 1}}}
        ]
        async for doc in db.emails.aggregate(pipeline):
            counts[doc["_id"]] = doc["count"]

    result = []
    for f in folders:
        f_copy = dict(f)
        f_copy["email_count"] = counts.get(f["id"], 0)
        result.append(f_copy)

    return {"folders": result}


@router.post("/folders")
async def create_folder(
    payload: FolderCreateRequest,
    current_user: dict = Depends(get_current_user)
):
    """Criar uma nova pasta personalizada."""
    user_id = current_user["id"]
    name = sanitize_string(payload.name.strip(), max_length=40)

    if not name:
        raise HTTPException(status_code=400, detail="Nome da pasta é obrigatório")

    # Check for duplicate name
    dup = await db.email_folders.find_one({"user_id": user_id, "name": name})
    if dup:
        raise HTTPException(status_code=409, detail="Já existe uma pasta com esse nome")

    # Validate color or use default
    color = payload.color.strip() if payload.color else "#6b7280"
    if not _validate_hex_color(color):
        color = "#6b7280"

    folder_doc = {
        "id": str(uuid.uuid4()),
        "name": name,
        "color": color,
        "user_id": user_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.email_folders.insert_one(folder_doc)
    folder_doc.pop("_id", None)
    folder_doc["email_count"] = 0

    logger.info(f"Pasta criada: {name} ({color}) por {current_user['email']}")
    return folder_doc


@router.put("/folders/{folder_id}")
async def update_folder(
    folder_id: str,
    payload: FolderUpdateRequest,
    current_user: dict = Depends(get_current_user)
):
    """Atualizar nome e/ou cor de uma pasta."""
    user_id = current_user["id"]
    folder = await db.email_folders.find_one({"id": folder_id, "user_id": user_id})
    if not folder:
        raise HTTPException(status_code=404, detail="Pasta não encontrada")

    update_data = {}
    if payload.name is not None:
        new_name = sanitize_string(payload.name.strip(), max_length=40)
        if not new_name:
            raise HTTPException(status_code=400, detail="Nome da pasta é obrigatório")
        dup = await db.email_folders.find_one({"user_id": user_id, "name": new_name, "id": {"$ne": folder_id}})
        if dup:
            raise HTTPException(status_code=409, detail="Já existe uma pasta com esse nome")
        update_data["name"] = new_name
    if payload.color is not None:
        color = payload.color.strip()
        if not _validate_hex_color(color):
            color = "#6b7280"
        update_data["color"] = color

    if update_data:
        await db.email_folders.update_one({"id": folder_id}, {"$set": update_data})

    updated = await db.email_folders.find_one({"id": folder_id}, {"_id": 0})
    logger.info(f"Pasta {folder_id} atualizada por {current_user['email']}")
    return updated


@router.delete("/folders/{folder_id}")
async def delete_folder(
    folder_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Eliminar pasta e remover referência dos emails (emails voltam à pasta de origem)."""
    user_id = current_user["id"]
    folder = await db.email_folders.find_one({"id": folder_id, "user_id": user_id})
    if not folder:
        raise HTTPException(status_code=404, detail="Pasta não encontrada")

    folder_name = folder["name"]

    # Remove folder_id from all emails in this folder (they go back to inbox)
    await db.emails.update_many(
        {"folder_id": folder_id},
        {"$unset": {"folder_id": ""}}
    )

    # Delete folder document
    await db.email_folders.delete_one({"id": folder_id})

    logger.info(f"Pasta '{folder_name}' ({folder_id}) eliminada por {current_user['email']}")
    return {"success": True, "message": f"Pasta '{folder_name}' eliminada"}


@router.post("/emails/move-to-folder")
async def move_emails_to_folder(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Mover um ou mais emails para uma pasta personalizada."""
    email_ids = data.get("email_ids", [])
    folder_id = data.get("folder_id")  # None/empty = remove from folder

    if not email_ids:
        raise HTTPException(status_code=400, detail="Selecione pelo menos um email")

    if folder_id:
        # Validate folder exists
        folder = await db.email_folders.find_one({"id": folder_id})
        if not folder:
            raise HTTPException(status_code=404, detail="Pasta não encontrada")

    update = {"$set": {"folder_id": folder_id}} if folder_id else {"$unset": {"folder_id": ""}}

    result = await db.emails.update_many(
        {"id": {"$in": email_ids}},
        update
    )

    return {
        "success": True,
        "modified_count": result.modified_count,
        "folder_id": folder_id
    }


# ==== ATTACHMENT UPLOAD ====

@router.post("/attachments/upload")
async def upload_attachments(
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Carregar um ou mais ficheiros para o S3 (pasta temporária).
    Máximo 25MB por ficheiro, máximo 10 ficheiros.
    Retorna lista de metadados com temp_key para referência futura.
    """
    from services.s3_storage import s3_service

    if not files:
        raise HTTPException(status_code=400, detail="Nenhum ficheiro enviado")

    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Máximo de 10 ficheiros por upload")

    MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB
    user_id = current_user["id"]
    uploaded = []
    errors = []

    for file in files:
        # Read content
        content = await file.read()

        if len(content) > MAX_FILE_SIZE:
            errors.append(f"{file.filename}: ficheiro excede 25MB")
            continue

        if not content:
            errors.append(f"{file.filename}: ficheiro vazio")
            continue

        file_id = str(uuid.uuid4())
        safe_filename = file.filename or "unnamed"
        temp_key = f"temp/attachments/{user_id}/{file_id}_{safe_filename}"

        try:
            import io
            file_obj = io.BytesIO(content)
            s3_service.s3_client.upload_fileobj(
                file_obj,
                s3_service.bucket_name,
                temp_key,
                ExtraArgs={'ContentType': file.content_type or 'application/octet-stream'}
            )

            attachment_meta = {
                "id": file_id,
                "file_name": safe_filename,
                "file_size": len(content),
                "mime_type": file.content_type or "application/octet-stream",
                "temp_key": temp_key,
                "user_id": user_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            # Store temp attachment metadata for lookup during send
            await db.temp_attachments.insert_one(attachment_meta)

            uploaded.append({
                "id": file_id,
                "file_name": safe_filename,
                "file_size": len(content),
                "mime_type": file.content_type or "application/octet-stream",
                "temp_key": temp_key,
            })
            logger.info(f"Attachment upload: {safe_filename} -> {temp_key}")
        except Exception as e:
            errors.append(f"{file.filename}: erro no upload - {str(e)}")
            logger.error(f"Erro no upload de attachment {safe_filename}: {e}")

    if not uploaded:
        raise HTTPException(status_code=500, detail=f"Nenhum ficheiro carregado: {'; '.join(errors)}")

    return {
        "attachments": uploaded,
        "errors": errors if errors else None,
    }


# ==== ATTACHMENT DOWNLOAD (presigned URL) ====

@router.get("/{email_id}/attachments/{file_id}/download")
async def download_email_attachment(
    email_id: str,
    file_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Obter URL pré-assinada para download de anexo de email.
    Procura o attachment pelo id no array de attachments do email.
    Se tiver s3_key, gera presigned URL (1h). Caso contrário, retorna URL existente.
    """
    from services.s3_storage import s3_service

    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")

    attachments = email.get("attachments", [])
    attachment = next((a for a in attachments if a.get("id") == file_id), None)

    if not attachment:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")

    filename = attachment.get("filename", attachment.get("file_name", "anexo"))
    content_type = attachment.get("content_type", attachment.get("mime_type", "application/octet-stream"))

    # If has s3_key, generate presigned URL
    s3_key = attachment.get("s3_key")
    if s3_key:
        url = s3_service.get_presigned_url(s3_key, expiration=3600)
        if url:
            return {"url": url, "filename": filename, "content_type": content_type}
        raise HTTPException(status_code=500, detail="Erro ao gerar URL de download")

    # Fallback: return existing URL or embedded content info
    if attachment.get("url"):
        return {"url": attachment["url"], "filename": filename, "content_type": content_type}

    raise HTTPException(status_code=404, detail="Conteúdo do anexo não disponível para download")


# ==== MARCAÇÃO DE EMAILS ====

@router.post("/{email_id}/mark")
async def mark_email(
    email_id: str,
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Marcar um email como importante, lido, etc.
    
    Tipos de marcação:
    - important: Marcar como importante
    - read: Marcar como lido
    - unread: Marcar como não lido
    - starred: Marcar com estrela
    - archived: Arquivar
    - spam: Marcar como spam
    
    Aceita tanto {"type": "read"} como {"mark_type": "read"}
    """
    mark_type_str = data.get("type") or data.get("mark_type")
    if not mark_type_str:
        raise HTTPException(status_code=422, detail="Campo 'type' obrigatório")
    
    try:
        mark_type = EmailMarkType(mark_type_str)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Tipo de marcação inválido: {mark_type_str}")
    
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    if mark_type == EmailMarkType.IMPORTANT:
        update_data["is_important"] = True
    elif mark_type == EmailMarkType.READ:
        update_data["is_read"] = True
    elif mark_type == EmailMarkType.UNREAD:
        update_data["is_read"] = False
    elif mark_type == EmailMarkType.STARRED:
        update_data["is_starred"] = True
    elif mark_type == EmailMarkType.ARCHIVED:
        update_data["is_archived"] = True
    elif mark_type == EmailMarkType.SPAM:
        update_data["is_spam"] = True
    
    await db.emails.update_one({"id": email_id}, {"$set": update_data})
    
    logger.info(f"Email {email_id} marcado como {mark_type.value} por {current_user['email']}")
    
    return {
        "success": True,
        "email_id": email_id,
        "mark_type": mark_type.value
    }


@router.delete("/{email_id}/mark/{mark_type}")
async def unmark_email(
    email_id: str,
    mark_type: EmailMarkType,
    current_user: dict = Depends(get_current_user)
):
    """Remover marcação de email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    
    if mark_type == EmailMarkType.IMPORTANT:
        update_data["is_important"] = False
    elif mark_type == EmailMarkType.STARRED:
        update_data["is_starred"] = False
    elif mark_type == EmailMarkType.ARCHIVED:
        update_data["is_archived"] = False
    
    await db.emails.update_one({"id": email_id}, {"$set": update_data})
    
    return {"success": True, "email_id": email_id, "removed": mark_type.value}


# ==== LABELS/ETIQUETAS ====

@router.post("/{email_id}/labels")
async def add_email_label(
    email_id: str,
    label: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user)
):
    """Adicionar etiqueta ao email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    labels = email.get("labels", [])
    label = sanitize_string(label, max_length=200)
    if label not in labels:
        labels.append(label)
        await db.emails.update_one(
            {"id": email_id},
            {"$set": {"labels": labels, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
    
    return {"success": True, "labels": labels}


@router.delete("/{email_id}/labels/{label}")
async def remove_email_label(
    email_id: str,
    label: str,
    current_user: dict = Depends(get_current_user)
):
    """Remover etiqueta do email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    labels = email.get("labels", [])
    if label in labels:
        labels.remove(label)
        await db.emails.update_one(
            {"id": email_id},
            {"$set": {"labels": labels, "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
    
    return {"success": True, "labels": labels}


# ==== ANEXOS ====

@router.get("/{email_id}/attachments")
async def get_email_attachments(
    email_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Listar anexos de um email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0, "attachments": 1})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    return {"attachments": email.get("attachments", [])}


@router.get("/{email_id}/attachments/{attachment_id}")
async def download_attachment(
    email_id: str,
    attachment_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Download de anexo."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    attachments = email.get("attachments", [])
    attachment = next((a for a in attachments if a.get("id") == attachment_id), None)
    
    if not attachment:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    
    # Se tiver URL externa, redirecionar
    if attachment.get("url"):
        return {"redirect_url": attachment["url"]}
    
    # Se tiver conteúdo em base64
    if attachment.get("content"):
        content = base64.b64decode(attachment["content"])
        return Response(
            content=content,
            media_type=attachment.get("content_type", "application/octet-stream"),
            headers={
                "Content-Disposition": f'attachment; filename="{attachment["filename"]}"'
            }
        )
    
    raise HTTPException(status_code=404, detail="Conteúdo do anexo não disponível")


@router.get("/{email_id}/attachments/{attachment_id}/preview")
async def preview_attachment(
    email_id: str,
    attachment_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Preview de anexo (para imagens e PDFs)."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    attachments = email.get("attachments", [])
    attachment = next((a for a in attachments if a.get("id") == attachment_id), None)
    
    if not attachment:
        raise HTTPException(status_code=404, detail="Anexo não encontrado")
    
    content_type = attachment.get("content_type", "")
    
    # Verificar se é previewable
    previewable_types = ["image/", "application/pdf", "text/"]
    if not any(pt in content_type for pt in previewable_types):
        raise HTTPException(status_code=400, detail="Este tipo de ficheiro não suporta preview")
    
    # Se tiver preview_url
    if attachment.get("preview_url"):
        return {"preview_url": attachment["preview_url"]}
    
    # Se tiver conteúdo em base64
    if attachment.get("content"):
        content = base64.b64decode(attachment["content"])
        return Response(
            content=content,
            media_type=content_type
        )
    
    raise HTTPException(status_code=404, detail="Preview não disponível")


# ==== FILTROS AVANÇADOS ====

@router.post("/search/advanced")
async def advanced_email_search(
    filters: EmailFilter,
    page: int = Query(1, ge=1),
    limit: int = Query(20, le=100),
    current_user: dict = Depends(get_current_user)
):
    """
    Pesquisa avançada de emails com filtros.
    
    Suporta:
    - Filtro por processo
    - Filtro por direção (enviado/recebido)
    - Filtro por conta (precision/power)
    - Filtro por marcações (importante, lido, estrela)
    - Filtro por anexos
    - Filtro por intervalo de datas
    - Pesquisa por texto
    - Filtro por etiquetas
    """
    query = {}
    
    # Filtro por processo
    if filters.process_id:
        query["process_id"] = filters.process_id
    
    # Filtro por direcção
    if filters.direction:
        query["direction"] = filters.direction.value
    
    # Filtro por conta
    if filters.account:
        query["account"] = filters.account
    
    # Filtros de marcação
    if filters.is_important is not None:
        query["is_important"] = filters.is_important
    if filters.is_read is not None:
        query["is_read"] = filters.is_read
    if filters.is_starred is not None:
        query["is_starred"] = filters.is_starred
    if filters.is_archived is not None:
        query["is_archived"] = filters.is_archived
    
    # Filtro por anexos
    if filters.has_attachments is not None:
        if filters.has_attachments:
            query["attachments.0"] = {"$exists": True}
        else:
            query["attachments"] = {"$size": 0}
    
    # Filtro por datas
    if filters.date_from or filters.date_to:
        date_query = {}
        if filters.date_from:
            date_query["$gte"] = filters.date_from
        if filters.date_to:
            date_query["$lte"] = filters.date_to
        query["sent_at"] = date_query
    
    # Pesquisa por texto
    if filters.search_term:
        query["$or"] = [
            {"subject": {"$regex": filters.search_term, "$options": "i"}},
            {"body": {"$regex": filters.search_term, "$options": "i"}},
            {"from_email": {"$regex": filters.search_term, "$options": "i"}},
            {"to_emails": {"$regex": filters.search_term, "$options": "i"}},
        ]
    
    # Filtro por etiquetas
    if filters.labels:
        query["labels"] = {"$all": filters.labels}
    
    # Executar query com paginação
    skip = (page - 1) * limit
    total = await db.emails.count_documents(query)
    
    emails = await db.emails.find(
        query,
        {"_id": 0}
    ).sort("sent_at", -1).skip(skip).limit(limit).to_list(limit)
    
    # Enriquecer emails
    enriched_emails = []
    for email in emails:
        enriched = await enrich_email(email)
        enriched_emails.append(enriched)
    
    return {
        "emails": enriched_emails,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    }


# ==== TIMELINE DE EMAILS ====

@router.get("/timeline/{process_id}")
async def get_email_timeline(
    process_id: str,
    current_user: dict = Depends(get_current_user)
):
    """
    Obter timeline de emails de um processo.
    Inclui eventos agrupados por dia.
    """
    emails = await db.emails.find(
        {"process_id": process_id, "is_archived": {"$ne": True}},
        {"_id": 0}
    ).sort("sent_at", 1).to_list(500)
    
    # Agrupar por data
    timeline = {}
    for email in emails:
        if email.get("sent_at"):
            date_key = email["sent_at"][:10]  # YYYY-MM-DD
            if date_key not in timeline:
                timeline[date_key] = {
                    "date": date_key,
                    "emails": [],
                    "stats": {"sent": 0, "received": 0}
                }
            
            timeline[date_key]["emails"].append(email)
            if email.get("direction") == "sent":
                timeline[date_key]["stats"]["sent"] += 1
            else:
                timeline[date_key]["stats"]["received"] += 1
    
    # Converter para lista ordenada
    timeline_list = sorted(timeline.values(), key=lambda x: x["date"], reverse=True)
    
    return {"timeline": timeline_list, "total_emails": len(emails)}


# ==== TEMPLATES DE RESPOSTA ====

@router.get("/templates", response_model=List[EmailTemplateResponse])
async def get_email_templates(
    category: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Listar templates de resposta rápida."""
    query = {}
    if category:
        query["category"] = category
    
    templates = await db.email_templates.find(
        query,
        {"_id": 0}
    ).sort("usage_count", -1).to_list(50)
    
    return templates


@router.post("/templates", response_model=EmailTemplateResponse)
async def create_email_template(
    template: EmailTemplateCreate,
    current_user: dict = Depends(get_current_user)
):
    """Criar novo template de resposta."""
    template_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    template_doc = {
        "id": template_id,
        "name": sanitize_string(template.name, max_length=200),
        "subject": sanitize_string(template.subject, max_length=300),
        "body": sanitize_string(template.body, max_length=10000),
        "category": template.category,
        "is_default": template.is_default,
        "created_by": current_user["id"],
        "created_at": now,
        "usage_count": 0
    }
    
    # Se for default, remover default de outros
    if template.is_default:
        await db.email_templates.update_many(
            {"category": template.category},
            {"$set": {"is_default": False}}
        )
    
    await db.email_templates.insert_one(template_doc)
    
    return EmailTemplateResponse(**template_doc)


@router.put("/templates/{template_id}", response_model=EmailTemplateResponse)
async def update_email_template(
    template_id: str,
    template: EmailTemplateCreate,
    current_user: dict = Depends(get_current_user)
):
    """Actualizar template de resposta."""
    existing = await db.email_templates.find_one({"id": template_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    
    update_data = {
        "name": sanitize_string(template.name, max_length=200),
        "subject": sanitize_string(template.subject, max_length=300),
        "body": sanitize_string(template.body, max_length=10000),
        "category": template.category,
        "is_default": template.is_default,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.email_templates.update_one(
        {"id": template_id},
        {"$set": update_data}
    )
    
    updated = await db.email_templates.find_one({"id": template_id}, {"_id": 0})
    return EmailTemplateResponse(**updated)


@router.delete("/templates/{template_id}")
async def delete_email_template(
    template_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Eliminar template de resposta."""
    result = await db.email_templates.delete_one({"id": template_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    
    return {"success": True}


@router.post("/templates/{template_id}/use")
async def use_template(
    template_id: str,
    process_id: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user)
):
    """Incrementar contador de uso de template."""
    await db.email_templates.update_one(
        {"id": template_id},
        {"$inc": {"usage_count": 1}}
    )
    
    # Obter template
    template = await db.email_templates.find_one({"id": template_id}, {"_id": 0})
    
    # Obter dados do processo para personalizar
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    
    # Substituir variáveis
    body = template.get("body", "")
    subject = template.get("subject", "")
    
    if process:
        body = body.replace("{cliente}", process.get("client_name", ""))
        body = body.replace("{email_cliente}", process.get("client_email", ""))
        subject = subject.replace("{cliente}", process.get("client_name", ""))
    
    return {
        "subject": subject,
        "body": body
    }


# ==== NOTIFICAÇÕES ====

@router.get("/notifications/unread")
async def get_unread_notifications(
    current_user: dict = Depends(get_current_user)
):
    """
    Obter contagem de emails não lidos por processo.
    Para mostrar badges de notificação.
    """
    # Obter processos do utilizador
    user_email = current_user.get("email", "").lower()
    
    # Admin/CEO veem todos, outros só os seus
    if current_user["role"] in ["admin", "ceo"]:
        processes = await db.processes.find({}, {"_id": 0, "id": 1, "client_name": 1}).to_list(1000)
    else:
        processes = await db.processes.find(
            {"assigned_to": current_user["id"]},
            {"_id": 0, "id": 1, "client_name": 1}
        ).to_list(1000)
    
    process_ids = [p["id"] for p in processes]
    
    # Contar emails não lidos por processo
    pipeline = [
        {"$match": {
            "process_id": {"$in": process_ids},
            "is_read": False,
            "is_archived": {"$ne": True}
        }},
        {"$group": {
            "_id": "$process_id",
            "count": {"$sum": 1},
            "latest": {"$max": "$sent_at"}
        }}
    ]
    
    unread_counts = await db.emails.aggregate(pipeline).to_list(1000)
    
    # Mapear para resposta
    result = {}
    for item in unread_counts:
        process_id = item["_id"]
        process = next((p for p in processes if p["id"] == process_id), None)
        if process:
            result[process_id] = {
                "count": item["count"],
                "latest": item["latest"],
                "client_name": process.get("client_name", "")
            }
    
    total_unread = sum(r["count"] for r in result.values())
    
    return {
        "total_unread": total_unread,
        "by_process": result
    }


@router.get("/test-connection")
async def test_email_connections(
    account: Optional[str] = Query(None, description="Conta específica (precision, power) ou todas"),
    current_user: dict = Depends(get_current_user)
):
    """Testar ligação com as contas de email."""
    if current_user["role"] not in ["admin", "ceo"]:
        raise HTTPException(status_code=403, detail="Sem permissão")
    
    results = await test_email_connection(account)
    return results


@router.get("/accounts")
async def get_configured_accounts(
    current_user: dict = Depends(get_current_user)
):
    """Listar contas de email configuradas."""
    accounts = get_email_accounts()
    return [
        {
            "name": a.name,
            "email": a.email,
            "imap_server": a.imap_server,
            "smtp_server": a.smtp_server
        }
        for a in accounts
    ]


# ==== WEBMAIL - LISTAGEM POR PASTA ====

@router.get("/webmail")
async def webmail_list(
    folder: str = Query("inbox", description="Pasta: inbox, sent, drafts, starred, trash, custom"),
    page: int = Query(1, ge=1),
    limit: int = Query(30, le=100),
    account: Optional[str] = Query(None, description="Conta IMAP: power, precision"),
    search: Optional[str] = Query(None, description="Pesquisa texto"),
    label: Optional[str] = Query(None, description="Filtrar por label"),
    custom_folder: Optional[str] = Query(None, description="ID de pasta personalizada"),
    current_user: dict = Depends(get_current_user)
):
    """
    Listar emails no formato Webmail por pasta.
    
    ISOLAMENTO DE DADOS (Segurança):
    - admin/ceo/diretor: podem ver TODOS os emails (caixa geral)
    - outros roles (consultor, intermediario, etc.): só vêem emails onde são
      recipient (inbox) ou sender (sent). Filtragem por endereço de email.
    
    - inbox: emails recebidos (direction=received, não arquivados)
    - sent: emails enviados (direction=sent)
    - starred: emails marcados como estrela
    - trash: emails arquivados
    - drafts: emails com status=draft
    - custom: emails numa pasta personalizada (requer custom_folder param)
    """
    from models.auth import UserRole
    
    user_email = (current_user.get("email") or "").lower().strip()
    user_role = current_user.get("role", "")
    can_see_all = user_role in (UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR)
    
    # === OBTER EMAIL DA CONTA IMAP SELECIONADA ===
    # Quando o user seleciona uma conta (ex: "power"), obtém o email dessa conta
    # para incluir no filtro — permite ver emails da caixa partilhada.
    account_email = None
    if account:
        try:
            accounts = await get_email_accounts_async()
            for acc in accounts:
                if acc.name == account:
                    account_email = (acc.email or "").lower().strip()
                    break
        except Exception:
            pass
    
    # === CONSTRUIR QUERY USANDO $and PARA EVITAR CONFLITOS ENTRE $or ===
    # Cada condição independente entra como um elemento separado do $and.
    # Isso evita que múltiplos $or se sobreponham.
    and_conditions = []
    
    # === ISOLAMENTO POR UTILIZADOR ===
    # Para pastas partilhadas (inbox), incluímos também o email da conta IMAP
    # para que staff possa ver emails recebidos na caixa de entrada partilhada.
    if not can_see_all and user_email:
        if folder == "inbox":
            inbox_or = [
                {"to_emails": {"$regex": re.escape(user_email), "$options": "i"}},
                {"to_emails": {"$exists": False}},  # emails legados sem to_emails
            ]
            # Se há conta selecionada, incluir também o email da conta partilhada
            if account_email and account_email != user_email:
                inbox_or.append({"to_emails": {"$regex": re.escape(account_email), "$options": "i"}})
            and_conditions.append({"$or": inbox_or})
        elif folder == "sent":
            # Enviados: o from_email deve ser do utilizador OU da conta partilhada
            sent_or = [
                {"from_email": {"$regex": re.escape(user_email), "$options": "i"}},
            ]
            if account_email and account_email != user_email:
                sent_or.append({"from_email": {"$regex": re.escape(account_email), "$options": "i"}})
            and_conditions.append({"$or": sent_or})
        elif folder == "drafts":
            # Rascunhos: criados pelo utilizador
            and_conditions.append({"created_by": current_user["id"]})
        elif folder in ("starred", "trash", "custom"):
            # O utilizador deve ser sender ou recipient
            shared_or = [
                {"from_email": {"$regex": re.escape(user_email), "$options": "i"}},
                {"to_emails": {"$regex": re.escape(user_email), "$options": "i"}},
            ]
            if account_email and account_email != user_email:
                shared_or.append({"from_email": {"$regex": re.escape(account_email), "$options": "i"}})
                shared_or.append({"to_emails": {"$regex": re.escape(account_email), "$options": "i"}})
            and_conditions.append({"$or": shared_or})
    
    # === FILTRO DE PASTA ===
    if folder == "inbox":
        and_conditions.append({"direction": "received"})
        and_conditions.append({"status": {"$ne": "draft"}})
        and_conditions.append({"is_archived": False})
    elif folder == "sent":
        and_conditions.append({"direction": "sent"})
        and_conditions.append({"status": {"$ne": "draft"}})
        and_conditions.append({"is_archived": False})
    elif folder == "starred":
        and_conditions.append({"is_starred": True})
    elif folder == "trash":
        and_conditions.append({"is_archived": True})
    elif folder == "drafts":
        and_conditions.append({"status": "draft"})
    elif folder == "custom":
        if not custom_folder:
            raise HTTPException(status_code=400, detail="ID da pasta não especificado")
        and_conditions.append({"folder_id": custom_folder})
    
    # === FILTRO POR CONTA IMAP ===
    if account:
        and_conditions.append({
            "$or": [
                {"account": account},
                {"account": {"$exists": False}},
            ]
        })
    
    # === FILTRO POR LABEL ===
    if label:
        and_conditions.append({"labels": label})
    
    # === PESQUISA TEXTUAL ===
    if search:
        search = sanitize_string(search, max_length=200)
        and_conditions.append({
            "$or": [
                {"subject": {"$regex": search, "$options": "i"}},
                {"body": {"$regex": search, "$options": "i"}},
                {"from_email": {"$regex": search, "$options": "i"}},
                {"to_emails": {"$regex": search, "$options": "i"}},
            ]
        })
    
    # Montar query final
    if len(and_conditions) == 1:
        query = and_conditions[0]
    elif and_conditions:
        query = {"$and": and_conditions}
    else:
        query = {}
    
    skip = (page - 1) * limit
    total = await db.emails.count_documents(query)
    
    logger.info(f"[Webmail List] folder={folder}, account={account}, user={user_email}, total={total}")
    
    emails = await db.emails.find(
        query,
        {"_id": 0, "body": 0, "body_html": 0}
    ).sort("sent_at", -1).skip(skip).limit(limit).to_list(limit)

    # Serialize _id to string and ensure id is always a string for frontend keying
    emails_serialized = []
    for email in emails:
        email = dict(email)
        if "_id" in email and email["_id"]:
            email["_id"] = str(email["_id"])
        if "id" in email and email["id"]:
            email["id"] = str(email["id"])
        emails_serialized.append(email)
    emails = emails_serialized

    # Contar não lidos para a pasta inbox (com isolamento de utilizador)
    unread_count = 0
    if folder == "inbox":
        unread_and = [
            {"direction": "received"},
            {"status": {"$ne": "draft"}},
            {"is_read": False},
            {"is_archived": False},
        ]
        # Aplicar isolamento ao unread_count também
        if not can_see_all and user_email:
            unread_and.append({
                "$or": [
                    {"to_emails": {"$regex": re.escape(user_email), "$options": "i"}},
                    {"to_emails": {"$exists": False}},
                ]
            })
        if account:
            unread_and.append({
                "$or": [
                    {"account": account},
                    {"account": {"$exists": False}},
                ]
            })
        unread_count = await db.emails.count_documents({"$and": unread_and})
    
    # Enriquecer emails com nome do processo/cliente
    enriched = []
    for email in emails:
        e = await enrich_email(email)
        e["id"] = str(e.get("id", ""))
        # Preview: primeira linha do body (buscar sem os campos excluídos acima)
        body_preview = email.get("body", "")[:120]
        if len(body_preview) == 120:
            body_preview += "..."
        e["preview"] = body_preview
        enriched.append(e)
    
    return {
        "emails": enriched,
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit,
        "unread_count": unread_count,
        "folder": folder
    }


@router.get("/webmail-stats")
async def webmail_stats(
    current_user: dict = Depends(get_current_user)
):
    """
    Estatísticas de Webmail para o utilizador logado.
    
    Retorna contadores de emails não lidos, enviados hoje e rascunhos pendentes.
    Respeita o isolamento de dados: consultor/intermediário só vê os seus.
    Admin/CEO/Diretor vêem a caixa geral.
    """
    from models.auth import UserRole
    
    user_email = (current_user.get("email") or "").lower().strip()
    user_role = current_user.get("role", "")
    user_id = current_user.get("id", "")
    can_see_all = user_role in (UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR)
    
    # Base queries
    inbox_base = {
        "direction": "received",
        "status": {"$ne": "draft"},
        "is_archived": False,
    }
    sent_base = {
        "direction": "sent",
        "status": {"$ne": "draft"},
        "is_archived": False,
    }
    drafts_base = {
        "status": "draft",
        "is_archived": False,
    }
    
    # Apply user isolation
    if not can_see_all and user_email:
        inbox_base["to_emails"] = {"$regex": re.escape(user_email), "$options": "i"}
        sent_base["from_email"] = {"$regex": re.escape(user_email), "$options": "i"}
        drafts_base["created_by"] = user_id
    
    # Unread count
    unread_query = {**inbox_base, "is_read": False}
    unread_count = await db.emails.count_documents(unread_query)
    
    # Sent today
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    sent_today_query = {
        **sent_base,
        "sent_at": {"$gte": today_start}
    }
    sent_today_count = await db.emails.count_documents(sent_today_query)
    
    # Drafts count
    drafts_count = await db.emails.count_documents(drafts_base)
    
    return {
        "unread_count": unread_count,
        "sent_today_count": sent_today_count,
        "drafts_count": drafts_count,
    }


@router.post("/webmail/sync")
async def webmail_sync(
    account: Optional[str] = Query(None, description="Conta: precision ou power (None = todas)"),
    days: int = Query(7, ge=1, le=30, description="Dias para sincronizar"),
    current_user: dict = Depends(get_current_user)
):
    """
    Sincronizar emails do IMAP para o Webmail (background).
    
    Faz pull de TODOS os emails recentes das pastas INBOX e Enviados,
    sem filtro de processo. Deduplica por Message-ID + conta.
    
    Executa em background — o progresso pode ser acompanhado na página
    de Tarefas em Background.
    """
    from services.background_jobs import BackgroundJobService, JobType
    
    # Verificar contas configuradas primeiro
    accounts = await get_email_accounts_async()
    if not accounts:
        return {
            "success": False,
            "error": "Nenhuma conta de email configurada. Vá a Configurações > Email e configure pelo menos uma conta IMAP.",
            "accounts_found": 0
        }
    
    # Se account foi especificado, verificar se existe
    if account:
        matched = [a for a in accounts if a.name == account]
        if not matched:
            available = [a.name for a in accounts]
            return {
                "success": False,
                "error": f"Conta '{account}' não encontrada. Contas disponíveis: {available}",
                "accounts_found": len(accounts),
                "available_accounts": available
            }
    
    # Criar job em background
    job_service = BackgroundJobService()
    job_id = await job_service.create_job(
        job_type=JobType.EMAIL_SYNC,
        user_id=current_user["id"],
        user_email=current_user.get("email", ""),
        metadata={"account": account, "days": days}
    )
    
    # Executar sincronização em background
    async def run_sync():
        try:
            await job_service.update_progress(job_id, 0, 1, "A sincronizar emails...")
            result = await sync_webmail_emails(
                account_name=account,
                days=days,
                max_emails=150
            )
            # Extract summary
            synced = result.get("emails_synced", result.get("synced", 0))
            total = result.get("emails_found", result.get("total", 0))
            msg = f"Sincronização concluída: {synced} emails"
            if result.get("success") == False:
                await job_service.fail_job(job_id, result.get("error", "Erro na sincronização"))
            else:
                await job_service.complete_job(job_id, {"synced": synced, "total": total, "details": result})
        except Exception as e:
            logger.error(f"Erro na sincronização webmail: {e}", exc_info=True)
            await job_service.fail_job(job_id, str(e))
    
    asyncio.create_task(run_sync())
    
    return {
        "success": True,
        "message": "Sincronização iniciada em background",
        "job_id": job_id,
        "status": "started"
    }


@router.post("/webmail/sync-user")
async def webmail_sync_user(
    current_user: dict = Depends(get_current_user)
):
    """
    Sincronizar emails usando as credenciais pessoais do utilizador logado.
    Requer que o utilizador tenha configurado o seu email em Configurações > Perfil.
    """
    from services.background_jobs import BackgroundJobService, JobType
    
    user_id = current_user["id"]
    
    # Verificar se o utilizador tem configuração
    user = await db.users.find_one(
        {"id": user_id},
        {"_id": 0, "email_config": 1}
    )
    
    if not user or not user.get("email_config", {}).get("is_configured"):
        return {
            "success": False,
            "error": "Configuração de email não encontrada. Vá ao seu Perfil > Configuração de Webmail para configurar."
        }
    
    # Criar job em background
    job_service = BackgroundJobService()
    job_id = await job_service.create_job(
        job_type=JobType.EMAIL_SYNC,
        user_id=user_id,
        user_email=current_user.get("email", ""),
        metadata={"sync_type": "user_personal"}
    )
    
    async def run_user_sync():
        try:
            from services.email_service import sync_user_emails
            await job_service.update_progress(job_id, 0, 1, "A sincronizar emails pessoais...")
            result = await sync_user_emails(user_id)
            if result.get("success") == False:
                await job_service.fail_job(job_id, result.get("error", "Erro na sincronização"))
            else:
                synced = result.get("total_synced", 0)
                await job_service.complete_job(job_id, {"synced": synced, "details": result})
        except Exception as e:
            logger.error(f"Erro na sincronização user emails: {e}", exc_info=True)
            await job_service.fail_job(job_id, str(e))
    
    asyncio.create_task(run_user_sync())
    
    return {
        "success": True,
        "message": "Sincronização pessoal iniciada em background",
        "job_id": job_id,
    }


@router.get("/process/{process_id}", response_model=List[EmailResponse])
async def get_process_emails(
    process_id: str,
    direction: Optional[EmailDirection] = Query(None, description="Filtrar por direção"),
    filter_by_user: bool = Query(False, description="Filtrar apenas emails onde o utilizador participou"),
    include_archived: bool = Query(False, description="Incluir emails arquivados"),
    force_refresh: bool = Query(False, description="Limpar emails em cache e re-sincronizar do IMAP"),
    current_user: dict = Depends(get_current_user)
):
    """
    Listar emails de um processo.
    
    Se force_refresh=True, elimina todos os emails sincronizados do processo
    e faz uma nova sincronização IMAP antes de devolver os resultados.
    """
    if force_refresh:
        # Limpar cache: apagar emails sincronizados (marcados com "Sincronizado de" nas notes)
        delete_result = await db.emails.delete_many({
            "process_id": process_id,
            "notes": {"$regex": "^Sincronizado de", "$options": "i"}
        })
        logger.info(f"Cache limpa para processo {process_id}: {delete_result.deleted_count} emails removidos")
        
        # Re-sincronizar do IMAP
        user_email = current_user.get("email")
        try:
            sync_result = await sync_emails_for_process(process_id, days=30, user_email=user_email)
            logger.info(f"Re-sync após limpeza de cache: {sync_result}")
        except Exception as e:
            logger.error(f"Erro na re-sync após limpeza de cache: {e}")
    
    query = {"process_id": process_id}
    
    if direction:
        query["direction"] = direction.value
    
    if not include_archived:
        query["is_archived"] = {"$ne": True}
    
    if filter_by_user:
        user_email = current_user.get("email", "").lower()
        if user_email:
            query["$or"] = [
                {"from_email": {"$regex": user_email, "$options": "i"}},
                {"to_emails": {"$elemMatch": {"$regex": user_email, "$options": "i"}}},
                {"cc_emails": {"$elemMatch": {"$regex": user_email, "$options": "i"}}}
            ]
    
    emails = await db.emails.find(query, {"_id": 0}).sort("sent_at", -1).to_list(500)
    
    enriched_emails = []
    for email in emails:
        enriched = await enrich_email(email)
        enriched_emails.append(EmailResponse(**enriched))
    
    return enriched_emails


@router.get("/stats/{process_id}")
async def get_email_stats(
    process_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Obter estatísticas de emails de um processo."""
    pipeline = [
        {"$match": {"process_id": process_id, "is_archived": {"$ne": True}}},
        {"$group": {
            "_id": "$direction",
            "count": {"$sum": 1}
        }}
    ]
    
    results = await db.emails.aggregate(pipeline).to_list(10)
    
    stats = {
        "total": 0,
        "sent": 0,
        "received": 0,
        "unread": 0,
        "important": 0,
        "starred": 0
    }
    
    for r in results:
        if r["_id"] == "sent":
            stats["sent"] = r["count"]
        elif r["_id"] == "received":
            stats["received"] = r["count"]
        stats["total"] += r["count"]
    
    # Contar não lidos, importantes e estrelados
    stats["unread"] = await db.emails.count_documents({
        "process_id": process_id,
        "is_read": False,
        "is_archived": {"$ne": True}
    })
    stats["important"] = await db.emails.count_documents({
        "process_id": process_id,
        "is_important": True
    })
    stats["starred"] = await db.emails.count_documents({
        "process_id": process_id,
        "is_starred": True
    })
    
    return stats


@router.post("/sync/{process_id}")
async def sync_process_emails(
    process_id: str,
    background_tasks: BackgroundTasks,
    days: int = Query(30, description="Sincronizar emails dos últimos X dias"),
    blocking: bool = Query(False, description="Esperar pela sincronização (pode demorar)"),
    current_user: dict = Depends(get_current_user)
):
    """Sincronizar emails de um processo."""
    user_email = current_user.get("email")
    
    if blocking:
        result = await sync_emails_for_process(process_id, days, user_email=user_email)
        return result
    else:
        async def run_sync():
            """Executa a sincronização de emails em background para o processo.

            Atualiza ``_sync_status`` com o estado (running/completed/failed)
            para que o frontend possa fazer polling do progresso.

            Args:
                Nenhum parâmetro direto — usa variáveis do closure
                (process_id, days, user_email).

            Returns:
                None. Resultado é guardado em ``_sync_status[process_id]``.
            """
            try:
                _sync_status[process_id] = {"status": "running", "started_at": datetime.now(timezone.utc).isoformat()}
                result = await sync_emails_for_process(process_id, days, user_email=user_email)
                _sync_status[process_id] = {
                    "status": "completed",
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "result": result
                }
            except Exception as e:
                logger.error(f"Erro na sincronização de emails para {process_id}: {e}")
                _sync_status[process_id] = {
                    "status": "error",
                    "error": str(e),
                    "completed_at": datetime.now(timezone.utc).isoformat()
                }
        
        asyncio.create_task(run_sync())
        
        return {
            "success": True,
            "message": "Sincronização iniciada em background",
            "process_id": process_id,
            "status": "started"
        }


@router.get("/sync-status/{process_id}")
async def get_sync_status(
    process_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Verificar o status da sincronização de emails."""
    if process_id in _sync_status:
        return _sync_status[process_id]
    return {"status": "not_found", "message": "Nenhuma sincronização encontrada"}


@router.post("/associate")
async def associate_email_to_client(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Associar um email existente a um processo/cliente específico."""
    email_id = data.get("email_id")
    process_id = data.get("process_id")
    
    if not email_id or not process_id:
        raise HTTPException(status_code=400, detail="email_id e process_id são obrigatórios")
    
    process = await db.processes.find_one({"id": process_id}, {"_id": 0, "id": 1, "client_name": 1})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    email = await db.emails.find_one(
        {"$or": [{"id": email_id}, {"message_id": email_id}]},
        {"_id": 0}
    )
    
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    if email.get("process_id") == process_id:
        return {"success": True, "message": "Email já está associado a este processo"}
    
    now = datetime.now(timezone.utc).isoformat()
    await db.emails.update_one(
        {"id": email["id"]},
        {"$set": {
            "process_id": process_id,
            "associated_by": current_user["id"],
            "associated_at": now
        }}
    )
    
    logger.info(f"Email {email['id']} associado ao processo {process_id} por {current_user['email']}")
    
    return {
        "success": True,
        "message": f"Email associado ao cliente {process.get('client_name', process_id)}",
        "email_id": email["id"],
        "process_id": process_id
    }


@router.get("/search")
async def search_emails(
    q: str = Query(..., description="Termo de pesquisa"),
    limit: int = Query(20, le=100),
    current_user: dict = Depends(get_current_user)
):
    """Pesquisar emails para associação manual."""
    if len(q) < 3:
        raise HTTPException(status_code=400, detail="Termo deve ter pelo menos 3 caracteres")
    
    query = {
        "$or": [
            {"subject": {"$regex": q, "$options": "i"}},
            {"from_email": {"$regex": q, "$options": "i"}}
        ]
    }
    
    emails = await db.emails.find(
        query,
        {"_id": 0, "id": 1, "subject": 1, "from_email": 1, "to_emails": 1, "sent_at": 1, "process_id": 1}
    ).sort("sent_at", -1).limit(limit).to_list(limit)
    
    for email in emails:
        if email.get("process_id"):
            process = await db.processes.find_one(
                {"id": email["process_id"]},
                {"_id": 0, "client_name": 1}
            )
            if process:
                email["client_name"] = process.get("client_name")
    
    return {"emails": emails, "total": len(emails)}


@router.post("/send")
async def send_email_endpoint(
    payload: EmailSendRequest,
    account: str = Query("power", description="Conta de email"),
    current_user: dict = Depends(get_current_user)
):
    """Enviar email através de uma das contas configuradas."""
    # Sanitize inputs before sending and DB insert
    to_emails = [e for e in (sanitize_email(e) for e in payload.to_emails) if e]
    cc_emails = None
    if payload.cc_emails:
        cc_emails = [e for e in (sanitize_email(e) for e in payload.cc_emails) if e]
    subject = sanitize_string(payload.subject, max_length=300)
    body = sanitize_string(payload.body, max_length=10000)
    body_html = payload.body_html

    if not to_emails:
        raise HTTPException(status_code=400, detail="Pelo menos um email destinatário válido é necessário")

    # ==== PROCESS TEMP ATTACHMENTS ====
    email_attachments = []
    temp_attachment_records = []  # Track for S3 move + cleanup
    temp_keys_to_cleanup = []

    if payload.attachment_ids:
        # Look up temp attachments from MongoDB
        temp_docs = await db.temp_attachments.find(
            {"id": {"$in": payload.attachment_ids}, "user_id": current_user["id"]},
            {"_id": 0}
        ).to_list(20)

        if len(temp_docs) != len(payload.attachment_ids):
            found_ids = {d["id"] for d in temp_docs}
            missing = [aid for aid in payload.attachment_ids if aid not in found_ids]
            logger.warning(f"Temp attachments not found: {missing}")
            # Continue with available attachments

        from services.s3_storage import s3_service

        for temp_doc in temp_docs:
            temp_key = temp_doc["temp_key"]
            file_name = temp_doc["file_name"]
            mime_type = temp_doc.get("mime_type", "application/octet-stream")

            try:
                # Download content from temp S3 path
                loop = asyncio.get_event_loop()
                content_bytes = await loop.run_in_executor(
                    None, lambda tk=temp_key: s3_service.get_file_content(tk)
                )
                if content_bytes:
                    email_attachments.append({
                        "filename": file_name,
                        "content_bytes": content_bytes,
                        "content_type": mime_type,
                    })
                    temp_attachment_records.append({
                        "id": temp_doc["id"],
                        "file_name": file_name,
                        "file_size": temp_doc.get("file_size", len(content_bytes)),
                        "mime_type": mime_type,
                        "temp_key": temp_key,
                    })
                    temp_keys_to_cleanup.append(temp_key)
                    logger.info(f"Temp attachment prepared for send: {file_name}")
                else:
                    logger.warning(f"Could not download temp attachment from S3: {temp_key}")
            except Exception as e:
                logger.error(f"Error downloading temp attachment {file_name}: {e}")

    result = await send_email(
        account_name=account,
        to_emails=to_emails,
        subject=subject,
        body=body,
        body_html=body_html,
        cc_emails=cc_emails,
        process_id=payload.process_id,
        created_by=current_user["id"],
        attachments=email_attachments if email_attachments else None
    )
    
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error", "Erro ao enviar email"))

    # ==== MOVE ATTACHMENTS FROM TEMP TO PERMANENT + UPDATE EMAIL DOC ====
    if temp_attachment_records and payload.process_id:
        from services.s3_storage import s3_service

        # Find the most recently created sent email for this user+process
        sent_email = await db.emails.find_one(
            {
                "process_id": payload.process_id,
                "created_by": current_user["id"],
                "direction": "sent",
            },
            sort=[("sent_at", -1)],
        )

        if sent_email:
            permanent_attachments = []
            for att_rec in temp_attachment_records:
                permanent_s3_key = f"Emails/{sent_email['id']}/{att_rec['file_name']}"
                try:
                    loop = asyncio.get_event_loop()
                    moved = await loop.run_in_executor(
                        None,
                        lambda sk=att_rec["temp_key"], pk=permanent_s3_key: s3_service.rename_file(sk, pk)
                    )
                    if moved:
                        logger.info(f"Attachment moved: {att_rec['temp_key']} -> {permanent_s3_key}")
                    else:
                        logger.warning(f"Failed to move attachment: {att_rec['temp_key']}")
                        permanent_s3_key = att_rec["temp_key"]  # Keep temp key as fallback
                except Exception as e:
                    logger.error(f"Error moving attachment {att_rec['temp_key']}: {e}")
                    permanent_s3_key = att_rec["temp_key"]

                permanent_attachments.append({
                    "id": att_rec["id"],
                    "filename": att_rec["file_name"],
                    "file_name": att_rec["file_name"],
                    "size": att_rec["file_size"],
                    "content_type": att_rec["mime_type"],
                    "s3_key": permanent_s3_key,
                })

            # Update email document with permanent attachment metadata
            existing_attachments = sent_email.get("attachments", [])
            await db.emails.update_one(
                {"id": sent_email["id"]},
                {"$set": {"attachments": existing_attachments + permanent_attachments}}
            )

        # Clean up temp attachment metadata from MongoDB
        await db.temp_attachments.delete_many({"id": {"$in": [r["id"] for r in temp_attachment_records]}})

        # Clean up temp files from S3 (for any that weren't moved)
        from services.s3_storage import s3_service
        for temp_key in temp_keys_to_cleanup:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, lambda tk=temp_key: s3_service.delete_file(tk))
            except Exception as e:
                logger.warning(f"Failed to cleanup temp file {temp_key}: {e}")

    result["attachments_sent"] = len(email_attachments)
    return result


# ==== RASCUNHOS AUTOMÁTICOS (Auto-Draft) ====

@router.get("/drafts")
async def list_auto_drafts(
    limit: int = Query(20, le=100),
    current_user: dict = Depends(get_current_user)
):
    """
    Listar rascunhos automáticos pendentes.
    Admin/CEO veem todos, outros só os dos seus processos.
    """
    drafts = await get_pending_drafts(
        user_id=current_user["id"],
        user_role=current_user["role"],
        limit=limit,
    )
    stats = await get_draft_stats(
        user_id=current_user["id"],
        user_role=current_user["role"],
    )
    return {"drafts": drafts, "stats": stats}


@router.get("/drafts/stats")
async def auto_drafts_stats(
    current_user: dict = Depends(get_current_user)
):
    """Obter estatísticas de rascunhos automáticos pendentes."""
    stats = await get_draft_stats(
        user_id=current_user["id"],
        user_role=current_user["role"],
    )
    return stats


@router.put("/drafts/{draft_id}")
async def edit_auto_draft(
    draft_id: str,
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Editar um rascunho automático (subject, body, to_emails)."""
    # Sanitize user inputs before passing to service
    if "subject" in data and data["subject"]:
        data["subject"] = sanitize_string(data["subject"], max_length=300)
    if "body" in data and data["body"]:
        data["body"] = sanitize_string(data["body"], max_length=10000)
    if "to_emails" in data and data["to_emails"]:
        data["to_emails"] = [e for e in (sanitize_email(e) for e in data["to_emails"]) if e]

    result = await update_draft(draft_id, data)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result.get("error", "Erro ao atualizar"))
    return result


@router.post("/drafts/{draft_id}/send")
async def send_auto_draft(
    draft_id: str,
    account: str = Query("power", description="Conta de email (power/precision)"),
    current_user: dict = Depends(get_current_user)
):
    """Enviar um rascunho automático."""
    result = await send_draft(
        draft_id=draft_id,
        user_id=current_user["id"],
        account=account,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Erro ao enviar"))
    return result


@router.delete("/drafts/{draft_id}")
async def delete_auto_draft(
    draft_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Descartar (eliminar) um rascunho automático."""
    result = await discard_draft(draft_id)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result.get("error", "Rascunho não encontrado"))
    return result


@router.post("/drafts/create")
async def manually_create_draft(
    data: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """
    Criar manualmente um rascunho automático para um documento em falta.
    Útil quando o admin quer gerar um rascunho para um processo específico.
    """
    process_id = data.get("process_id")
    doc_type = data.get("doc_type")

    if not process_id or not doc_type:
        raise HTTPException(status_code=400, detail="process_id e doc_type são obrigatórios")

    # Obter dados do processo
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")

    result = await create_missing_doc_draft(
        process_id=process_id,
        client_name=process.get("client_name", ""),
        missing_doc_type=doc_type,
        process_number=process.get("process_number", ""),
    )

    return result


# ==== ROTAS CRUD GENÉRICAS ====

@router.post("", response_model=EmailResponse)
async def create_email_record(
    email_data: EmailCreate,
    current_user: dict = Depends(get_current_user)
):
    """Registar um email no histórico."""
    email_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    # Sanitize inputs before DB insert
    from_email = sanitize_email(email_data.from_email)
    to_emails = [e for e in (sanitize_email(e) for e in email_data.to_emails) if e]
    cc_emails = [e for e in (sanitize_email(e) for e in (email_data.cc_emails or [])) if e]
    bcc_emails = [e for e in (sanitize_email(e) for e in (email_data.bcc_emails or [])) if e]
    subject = sanitize_string(email_data.subject, max_length=300)
    body = sanitize_string(email_data.body, max_length=10000)
    notes = sanitize_string(email_data.notes, max_length=1000) if email_data.notes else None

    email = {
        "id": email_id,
        "process_id": email_data.process_id,
        "direction": email_data.direction.value,
        "from_email": from_email,
        "to_emails": to_emails,
        "cc_emails": cc_emails,
        "bcc_emails": bcc_emails,
        "subject": subject,
        "body": body,
        "body_html": email_data.body_html,
        "attachments": [a.dict() for a in (email_data.attachments or [])],
        "status": email_data.status.value,
        "sent_at": email_data.sent_at or now,
        "created_at": now,
        "created_by": current_user["id"],
        "notes": notes,
        "is_important": False,
        "is_read": True,
        "is_starred": False,
        "is_archived": False,
        "labels": []
    }
    
    await db.emails.insert_one(email)
    logger.info(f"Email registado: {email_id} para processo {email_data.process_id}")
    
    enriched = await enrich_email(email)
    return EmailResponse(**enriched)


@router.get("/{email_id}", response_model=EmailResponse)
async def get_email(
    email_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Obter detalhes de um email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})

    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")

    enriched = await enrich_email(email)

    try:
        return EmailResponse(**enriched)
    except Exception as e:
        logger.error(f"Erro ao validar email {email_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar email {email_id}: {str(e)}"
        )


@router.put("/{email_id}", response_model=EmailResponse)
async def update_email(
    email_id: str,
    email_data: EmailUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Actualizar registo de email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    update_data = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if email_data.subject is not None:
        update_data["subject"] = sanitize_string(email_data.subject, max_length=300)
    if email_data.body is not None:
        update_data["body"] = sanitize_string(email_data.body, max_length=10000)
    if email_data.notes is not None:
        update_data["notes"] = sanitize_string(email_data.notes, max_length=1000)
    if email_data.status is not None:
        update_data["status"] = email_data.status.value
    if email_data.is_important is not None:
        update_data["is_important"] = email_data.is_important
    if email_data.is_read is not None:
        update_data["is_read"] = email_data.is_read
    if email_data.is_starred is not None:
        update_data["is_starred"] = email_data.is_starred
    if email_data.is_archived is not None:
        update_data["is_archived"] = email_data.is_archived
    if email_data.labels is not None:
        update_data["labels"] = email_data.labels
    
    if update_data:
        await db.emails.update_one({"id": email_id}, {"$set": update_data})
    
    updated_email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    enriched = await enrich_email(updated_email)

    try:
        return EmailResponse(**enriched)
    except Exception as e:
        logger.error(f"Erro ao validar email {email_id} após update: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao processar email {email_id}: {str(e)}"
        )


@router.delete("/{email_id}")
async def delete_email(
    email_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Eliminar registo de email."""
    email = await db.emails.find_one({"id": email_id}, {"_id": 0})
    
    if not email:
        raise HTTPException(status_code=404, detail="Email não encontrado")
    
    await db.emails.delete_one({"id": email_id})
    logger.info(f"Email {email_id} eliminado por {current_user['name']}")
    
    return {"success": True, "message": "Email eliminado"}


# ==== GESTÃO DE EMAILS MONITORIZADOS ====

@router.get("/monitored/{process_id}")
async def get_monitored_emails(
    process_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Obter lista de emails monitorizados de um processo."""
    process = await db.processes.find_one({"id": process_id}, {"_id": 0, "client_email": 1, "monitored_emails": 1})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    return {
        "client_email": process.get("client_email"),
        "monitored_emails": process.get("monitored_emails", [])
    }


@router.post("/monitored/{process_id}")
async def add_monitored_email(
    process_id: str,
    email: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user)
):
    """Adicionar email à lista de monitorizados."""
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    email = sanitize_email(email)
    if not email:
        raise HTTPException(status_code=400, detail="Email inválido")
    
    monitored = process.get("monitored_emails", [])
    
    if email in monitored or email == process.get("client_email", "").lower():
        raise HTTPException(status_code=400, detail="Email já está na lista")
    
    monitored.append(email)
    await db.processes.update_one(
        {"id": process_id},
        {"$set": {"monitored_emails": monitored}}
    )
    
    logger.info(f"Email {email} adicionado à monitorização do processo {process_id}")
    
    return {
        "success": True,
        "monitored_emails": monitored
    }


@router.delete("/monitored/{process_id}/{email}")
async def remove_monitored_email(
    process_id: str,
    email: str,
    current_user: dict = Depends(get_current_user)
):
    """Remover email da lista de monitorizados."""
    process = await db.processes.find_one({"id": process_id})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    email = email.lower().strip()
    monitored = process.get("monitored_emails", [])
    
    if email not in monitored:
        raise HTTPException(status_code=404, detail="Email não encontrado na lista")
    
    monitored.remove(email)
    await db.processes.update_one(
        {"id": process_id},
        {"$set": {"monitored_emails": monitored}}
    )
    
    logger.info(f"Email {email} removido da monitorização do processo {process_id}")
    
    return {
        "success": True,
        "monitored_emails": monitored
    }
