"""
Envio / preview de documentação para balcões bancários.

Extraído de `routes/emails.py`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import string
import traceback
import uuid
from typing import Optional

from fastapi import HTTPException, Request

from database import db
from services.email_service import send_email
from services.email_template_vars import (
    _extract_email_variables,
    _build_professional_email_html,
)
from services.process_service import decrypt_sensitive_data
from utils.input_sanitization import sanitize_string, sanitize_email, sanitize_html

logger = logging.getLogger(__name__)


# ==== DOCUMENT RECIPIENTS & SEND DOCUMENTATION (antes de /{email_id} para evitar conflito) ====

async def run_get_document_recipients(current_user: dict):
    """
    Obter lista de destinatários disponíveis para envio de documentação.
    Retorna balcões globais (sistema) + balcões personalizados do utilizador.
    Os personalizados são identificados com is_custom: true.
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
    
    # Parse recipients JSON (balcões globais do sistema)
    recipients = []
    if doc_config.recipients:
        try:
            recipients = json.loads(doc_config.recipients)
        except (json.JSONDecodeError, TypeError):
            recipients = []
    
    # Marcar balcões globais como não-personalizados
    for r in recipients:
        r["is_custom"] = False
    
    # Adicionar balcões personalizados do utilizador
    user_id = current_user["id"]
    cursor = db["user_custom_branches"].find({"user_id": user_id}).sort("name", 1)
    user_branches = await cursor.to_list(100)
    for b in user_branches:
        recipients.append({
            "id": str(b["_id"]),
            "name": b["name"],
            "email": b["email"],
            "is_custom": True,
            "active": True,
        })
    
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


# ==== PREVIEW TEMPLATE (na config, com dados de exemplo — sem process_id) ====

async def run_preview_email_template(data: dict, current_user: dict):
    """
    Pré-visualiza o template de email de documentação com dados de exemplo.

    PORQUÊ: No painel de administração (Configurações → Destinatários → Template),
    o administrador precisa de visualizar como o email ficará antes de guardar
    o template. Ao contrário do /preview-documentation/{process_id}, este endpoint
    não requer um processo real — usa dados de exemplo preenchidos automaticamente.

    Funciona de forma idêntica ao "Pré-visualizar RGPD" do template de RGPD:
    o utilizador clica no botão e vê imediatamente o resultado renderizado.

    Args:
        data: Corpo do request com campo opcional `email_template`.
            Se não fornecido, usa o template guardado na configuração do sistema.
        current_user: Utilizador autenticado (injetado pelo Depends).

    Returns:
        dict: Contém html (string com dados de exemplo substituídos),
            subject, e sample_data (para referência).
    """
    from services.system_config import get_system_config

    # Obter template: do body ou da configuração guardada
    email_template = data.get("email_template")

    if not email_template:
        config = await get_system_config()
        doc_config = config.document_recipients
        email_template = doc_config.email_template

    if not email_template:
        raise HTTPException(
            status_code=400,
            detail="Nenhum template definido. Escreva ou restaure o template pré-definido antes de pré-visualizar."
        )

    # Dados de exemplo (simulam um processo real para o admin ver o resultado)
    sample_vars = {
        # Dados básicos
        "client_name": "João Manuel Silva",
        "client_nif": "234567890",
        "process_number": "PC-2025-0042",
        "documents_list": "- Cartão de Cidadão.pdf\n- Comprovativo de IBAN.pdf\n- Último IRS.pdf\n- Mapa de Responsabilidades.pdf",

        # 1º Proponente
        "p1_nome": "João Manuel Silva",
        "p1_email": "joao.silva@email.pt",
        "p1_telefone": "+351 912 345 678",
        "p1_data_nascimento": "15/03/1988",
        "p1_tipo_doc": "CC 12345678",
        "p1_nif": "234567890",
        "p1_estado_civil": "Casado",
        "p1_regime_casamento": "Comunhão de Adquiridos",
        "p1_profissao": "Engenheiro de Software",
        "p1_vinculo": "Contrato Efetivo",
        "p1_salario": "2.150,00 €",
        "p1_dependentes": "1",
        "p1_despesas": "450,00 €",
        "p1_situacao_bancaria": "Sem situações registadas",

        # 2º Proponente
        "p2_nome": "Maria Ana Santos",
        "p2_email": "maria.santos@email.pt",
        "p2_telefone": "+351 923 456 789",

        # Crédito Atual
        "banco_atual": "Millennium bcp",
        "num_titulares": 2,
        "contrato_mais_2_anos": "Sim",
        "valor_aquisicao": "285.000,00 €",
        "montante_divida": "195.000,00 €",

        # Transferência Pretendida
        "valor_extra": "30.000,00 €",
        "localidade_imovel": "Lisboa",
        "possibilidade_fiador": "Não",

        # Variáveis Financeiras
        "CAPITAIS_PROPRIOS": "90.000,00 €",
        "VALOR_IMOVEL": "285.000,00 €",
        "VALOR_FINANCIAMENTO": "195.000,00 €",
        "PRAZO_FINANCIAMENTO": "30 anos",
        "COMPRA_SOZINHO": "Não (Com Co-titular)",

        # Remetente
        "sender_name": current_user.get("name", "Consultor PowerCell"),
        "sender_email": current_user.get("email", "consultor@powercell.pt"),
        "sender_phone": current_user.get("phone", "+351 210 000 000"),
    }

    # Normalizar placeholders: [VAR_NAME] → {VAR_NAME}
    normalized_template = re.sub(r'\[([A-Z_]+)\]', r'{\1}', email_template)

    # Substituir variáveis no template
    try:
        email_body = normalized_template.format(**sample_vars)
    except KeyError as e:
        # Fallback: substituir apenas as variáveis encontradas
        logger.warning(f"[preview-template] Variável não encontrada: {e}")
        safe_vars = {k: v for k, v in sample_vars.items()}
        # Substituir as que existem e deixar as outras como placeholder visível
        import string
        class SafeFormatter(string.Formatter):
            def get_value(self, key, args, kwargs):
                try:
                    return super().get_value(key, args, kwargs)
                except (KeyError, IndexError):
                    return f'<span style="background:#fef3c7;color:#92400e;padding:2px 6px;border-radius:4px;font-size:12px;">⚠️ {{{key}}}</span>'
        formatter = SafeFormatter()
        try:
            email_body = formatter.format(normalized_template, **safe_vars)
        except Exception:
            email_body = normalized_template

    return {
        "success": True,
        "html": email_body,
        "subject": "Documentação - João Manuel Silva (Processo #PC-2025-0042)",
        "sample_data": sample_vars,
    }


# ==== PREVIEW DOCUMENTATION (gera HTML sem enviar) ====

async def run_preview_documentation_email(process_id: str, current_user: dict):
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
    
    # ── Desencriptar dados sensíveis para o preview ──
    process = decrypt_sensitive_data(process)
    
    # Obter configuração
    config = await get_system_config()
    doc_config = config.document_recipients
    
    # NOTA: O preview deve funcionar mesmo que o envio de documentação esteja
    # desactivado. O utilizador precisa de visualizar o template antes de
    # activar a funcionalidade. A restrição `enabled` só se aplica ao envio
    # (endpoint /send-documentation).
    
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
        # Normalizar placeholders: [VAR_NAME] → {VAR_NAME}
        # Os templates de email bancário usam [CAPITAIS_PROPRIOS] etc.
        normalized_template = re.sub(r'\[([A-Z_]+)\]', r'{\1}', email_template)
        # Usar template personalizado da configuração com todas as variáveis
        try:
            email_body = normalized_template.format(**template_vars)
        except KeyError as e:
            logger.warning(f"Variável não encontrada no template: {e}")
            # Fallback com variáveis básicas
            email_body = normalized_template.format(
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
        "subject": f"Documentação - {client_name} (Proc. {process_number})",
        "template_vars": template_vars,
        "available_variables": list(template_vars.keys()),
        "documents_count": len(documents) if documents else 0
    }


# ==== SEND DOCUMENTATION (antes de /{email_id} para evitar conflito de rota) ====
# Estes endpoints devem estar ANTES das rotas com /{email_id} para que
# o FastAPI faça match correcto e não trate "send-documentation" como um email_id.

async def run_send_documentation_email(
    process_id: str,
    data: dict,
    current_user: dict,
    request: Optional[Request] = None,
):
    """
    Envia documentação do processo para balcões/bancos com anexos
    descarregados do S3 e validação de destinatários contra conflitos.

    Porquê a validação de destinatários: impede o envio acidental de
    documentação a bancos onde o cliente já tem conta ativa ou simulação
    em curso (conflito de interesse regulado por legislação bancária).

    A construção do corpo do email segue uma prioridade decrescente:
    1. custom_html_body (Rich Text Editor — disponível para todos os utilizadores).
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
    try:
        return await _send_documentation_email_impl(process_id, data, current_user, request)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"[send-documentation] Erro inesperado: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Erro ao enviar documentação: {str(e)}")


async def _send_documentation_email_impl(
    process_id: str,
    data: dict,
    current_user: dict,
    request: Optional[Request] = None,
):
    """Implementação do envio de documentação (separada para error handling)."""
    from services.system_config import get_system_config
    
    # Obter processo
    process = await db.processes.find_one({"id": process_id}, {"_id": 0})
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    
    # ── Desencriptar dados sensíveis antes de usar no email ──
    # Garante que NIF, telefone, documento_id, etc. chegam ao banco
    # como texto legível (nunca ENC:xxx)
    process = decrypt_sensitive_data(process)
    
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
    _bancos_raw = financial_data.get("bancos_creditos", []) or []
    # bancos_creditos pode ser [{banco, valor}] (novo) ou ["CGD"] (legacy)
    bancos_creditos = []
    for item in _bancos_raw:
        if isinstance(item, dict):
            bancos_creditos.append(item.get("banco", ""))
        else:
            bancos_creditos.append(item)
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
    # 2. custom_message: mensagem de texto personalizada (com substituição de variáveis)
    # 3. email_template: template personalizado da configuração
    # 4. template HTML profissional por defeito
    # ============================================================
    
    if custom_html_body:
        # USAR HTML CUSTOMIZADO DO EDITOR WYSIWYG (disponível para todos os utilizadores)
        # Sanitizar para segurança (remover scripts perigosos) MAS preservar formatação HTML
        # que o Rich Text Editor gera (tabelas, negritos, parágrafos, etc.)
        # CRITICAL: allow_email_html=True preserva tags de formatação profissional
        # (div, table, h3, strong, etc.) enquanto remove scripts/iframe/form perigosos.
        # Antes usava sanitize_html() sem allow_email_html, o que stripava TODAS as tags
        # e os emails chegavam aos balcões como texto corrido sem formatação.
        email_body = sanitize_html(custom_html_body, allow_email_html=True)
        logger.info(f"Usando custom_html_body do Rich Text Editor para processo {process_id} (utilizador: {current_user['role']})")
    
    elif custom_message:
        custom_message = sanitize_string(custom_message, max_length=10000)
        # Normalizar placeholders: [VAR_NAME] → {VAR_NAME}
        normalized_custom = re.sub(r'\[([A-Z_]+)\]', r'{\1}', custom_message)
        try:
            resolved_text = normalized_custom.format(**template_vars)
        except KeyError as e:
            logger.warning(f"Variável não encontrada no custom_message: {e}")
            resolved_text = normalized_custom.format(
                client_name=client_name,
                client_nif=client_nif,
                process_number=process_number,
                documents_list=documents_list,
                sender_name=current_user.get("name", ""),
                sender_email=current_user.get("email", "")
            )
        # ── Converter texto simples em HTML profissional ──
        # Os bancos precisam de emails com parágrafos organizados,
        # não texto corrido sem formatação
        email_body = (
            "<div style='font-family: Arial, sans-serif; font-size: 14px; "
            "line-height: 1.6; color: #333; max-width: 600px;'>"
            + resolved_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                .replace('\n', '<br />')
            + "</div>"
        )
    elif email_template:
        # Sanitizar o template ANTES de resolver variáveis (preserva tags HTML de email)
        email_template = sanitize_html(email_template, allow_email_html=True)
        # Normalizar placeholders: [VAR_NAME] → {VAR_NAME}
        normalized_template = re.sub(r'\[([A-Z_]+)\]', r'{\1}', email_template)
        # Usar template personalizado da configuração com todas as variáveis
        try:
            resolved_text = normalized_template.format(**template_vars)
        except KeyError as e:
            logger.warning(f"Variável não encontrada no template: {e}")
            # Fallback com variáveis básicas
            resolved_text = normalized_template.format(
                client_name=client_name,
                client_nif=client_nif,
                process_number=process_number,
                documents_list=documents_list,
                sender_name=current_user.get("name", ""),
                sender_email=current_user.get("email", "")
            )
        # ── Verificar se o template já contém HTML ──
        # Se não tem tags HTML, converter texto para HTML
        has_html = bool(re.search(r'<(div|p|br|span|table|ul|ol|h[1-6])', resolved_text, re.IGNORECASE))
        if has_html:
            email_body = resolved_text
        else:
            email_body = (
                "<div style='font-family: Arial, sans-serif; font-size: 14px; "
                "line-height: 1.6; color: #333; max-width: 600px;'>"
                + resolved_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                    .replace('\n', '<br />')
                + "</div>"
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
    # Subject: usar o assunto enviado pelo frontend (editável), ou gerar padrão
    # CRITICAL: O processo Nº deve SEMPRE constar no assunto quando se envia
    # documentação para balcões (requisito regulatório dos bancos).
    custom_subject = data.get("subject")
    if custom_subject and custom_subject.strip():
        subject = custom_subject.strip()
        # Remover tag [Proc-xxxx] caso exista no subject customizado
        subject = re.sub(r'\s*\[Proc-[\w-]+\]\s*', ' ', subject).strip()
    else:
        subject = f"Documentação - {client_name} (Proc. {process_number})"
    
    # Garantir que o número do processo está sempre no assunto
    # (mesmo em assunto customizado pelo utilizador)
    if process_number and str(process_number) != "N/A":
        # Verificar se já contém o número do processo
        proc_patterns = [
            re.escape(str(process_number)),  # Número exato
            r'Proc\.?\s*' + re.escape(str(process_number)),  # "Proc. XXX" ou "Proc XXX"
            r'Processo\s*' + re.escape(str(process_number)),  # "Processo XXX"
        ]
        has_proc_in_subject = any(re.search(p, subject, re.IGNORECASE) for p in proc_patterns)
        if not has_proc_in_subject:
            subject = f"{subject} (Proc. {process_number})"
    
    # BCC adicional: emails introduzidos manualmente pelo utilizador
    bcc_manual = [e for e in (sanitize_email(e) for e in data.get("bcc_emails", [])) if e]
    # Combinar BCC dos destinatários validados + BCC manual
    all_bcc = validated_bcc + [e for e in bcc_manual if e not in validated_bcc]
    
    # ==== PREPARAR ANEXOS (download do S3) ====
    email_attachments = []
    failed_attachments = []
    for doc in documents:
        filename = doc.get("original_name", doc.get("filename", "documento"))
        s3_path = doc.get("s3_path") or doc.get("path")
        
        if s3_path:
            try:
                from services.s3_storage import s3_service
                content_bytes = await asyncio.get_running_loop().run_in_executor(
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
    plain_text_body = re.sub(r'<[^>]+>', '', email_body).strip()
    plain_text_body = re.sub(r'\n{3,}', '\n\n', plain_text_body)

    # === EMPRESA ATIVA — para resolver a assinatura correta ===
    # Cada user pode ter uma assinatura diferente por empresa (UCR). Lemos a
    # empresa ativa da sessão (header X-Company-Id) para que o send_email use
    # a assinatura da empresa que o utilizador selecionou, e não a default.
    active_company_id = None
    if request is not None:
        try:
            from services.auth import get_active_company_id_async
            active_company_id = await get_active_company_id_async(request, current_user)
        except Exception:
            active_company_id = None

    result = await send_email(
        account_name="power",
        to_emails=to_emails,
        subject=subject,
        body=plain_text_body,
        body_html=email_body,
        cc_emails=cc_emails if cc_emails else None,
        bcc_emails=all_bcc,
        reply_to=current_user.get("email"),
        from_email=current_user.get("email"),
        process_id=process_id,
        created_by=current_user["id"],
        attachments=email_attachments if email_attachments else None,
        force_system=True,
        system_purpose="DOCUMENTS",
        skip_proc_tag=True,
        active_company_id=active_company_id
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
    
    # Contagem total de destinatários (TO + CC + BCC)
    total_recipients = len(to_emails) + len(cc_emails) + len(all_bcc)
    
    logger.info(f"Documentação enviada para processo {process_id} por {current_user['email']}: {total_recipients} destinatário(s) (TO:{len(to_emails)} CC:{len(cc_emails)} BCC:{len(all_bcc)}), {len(email_attachments)} anexos")
    
    return {
        "success": True,
        "message": f"Documentação enviada com sucesso para {total_recipients} destinatário(s) ({len(email_attachments)} anexo(s))",
        "warnings": warnings,
        "sent_to": all_bcc,
        "sent_to_emails": to_emails,
        "sent_cc_emails": cc_emails,
        "sent_bcc_emails": all_bcc,
        "total_recipients": total_recipients,
        "attachments_sent": len(email_attachments),
        "attachments_failed": len(failed_attachments) if failed_attachments else 0
    }


