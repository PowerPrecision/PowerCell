"""
Variáveis e HTML profissional para templates de email de documentação.

Extraído de `routes/emails.py`.
"""
from __future__ import annotations

from services.process_service import decrypt_sensitive_data


def _extract_email_variables(process: dict, user: dict, documents_list: str) -> dict:
    """
    Extrai todas as variáveis disponíveis para uso em templates de email,
    agregando dados de múltiplas secções do processo num dicionário plano.

    SEGURANÇA: Desencripta campos sensíveis (NIF, telefone, documento_id, etc.)
    antes de os disponibilizar para substituição no template. Os dados que chegam
    ao banco têm de ser texto limpo e legível, nunca hashes cifrados.

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
    # ── Desencriptar campos sensíveis ANTES de extrair variáveis ──
    # Garante que NIF, telefone, documento_id, morada_fiscal, etc.
    # chegam ao banco como texto legível (nunca ENC:xxx)
    process = decrypt_sensitive_data(process)

    personal_data = process.get("personal_data", {}) or {}
    titular2_data = process.get("titular2_data", {}) or {}
    financial_data = process.get("financial_data", {}) or {}
    real_estate_data = process.get("real_estate_data", {}) or {}
    # credit_data: sub-estrutura do cartão "Dados de Crédito" (ProcessDetails.js).
    # Contém requested_amount, loan_term_years, interest_rate, monthly_payment,
    # bank_name, etc. — os campos que o QA reportou como estando a retornar "N/A".
    credit_data = process.get("credit_data", {}) or {}

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
        except Exception:
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
    # tem_creditos_activos pode ser lista (novos dados) ou bool (legacy)
    _tca = financial_data.get("tem_creditos_activos")
    if isinstance(_tca, list) and len(_tca) > 0:
        situacao_bancaria.append(f"Tem créditos ativos: {', '.join(_tca)}")
    elif isinstance(_tca, bool) and _tca:
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
    
    # ==== VARIÁVEIS FINANCEIRAS PARA TEMPLATES DE BANCOS ====
    # [VALOR_IMOVEL] — Valor de aquisição do imóvel
    valor_imovel_raw = (
        financial_data.get("valor_imovel")
        or financial_data.get("real_estate_base_value")
        or real_estate_data.get("valor_imovel")
        or real_estate_data.get("real_estate_base_value")
        or financial_data.get("valor_aquisicao")
    )
    valor_imovel = format_currency(valor_imovel_raw)
    
    # [VALOR_FINANCIAMENTO] — Montante pedido de financiamento
    # FIX (Pacote K): adicionados paths do novo cartão "Dados de Crédito"
    # (credit_data.requested_amount) e do campo valor_financiado (singular)
    # usado no cartão "Situação Financeira" do ProcessDetails.js.
    valor_financiamento_raw = (
        credit_data.get("requested_amount")
        or financial_data.get("credit_base_value")
        or financial_data.get("requested_amount")
        or financial_data.get("montante_pretendido")
        or financial_data.get("valor_financiamento")
        or financial_data.get("valor_financiado")
    )
    valor_financiamento = format_currency(valor_financiamento_raw)
    
    # [CAPITAIS_PROPRIOS] — Capitais próprios (valor_imovel - valor_financiamento)
    # FIX (Pacote K): adicionado path capital_proprio (SINGULAR) — é o nome
    # usado no cartão "Rendimentos" do ProcessDetails.js (linha 3490).
    capitais_proprios_raw = (
        financial_data.get("capitais_proprios")
        or financial_data.get("capital_proprio")
    )
    if capitais_proprios_raw is not None and capitais_proprios_raw != "":
        capitais_proprios = format_currency(capitais_proprios_raw)
    elif valor_imovel_raw and valor_financiamento_raw:
        try:
            cp = float(valor_imovel_raw) - float(valor_financiamento_raw)
            capitais_proprios = format_currency(cp)
        except (ValueError, TypeError):
            capitais_proprios = "N/A"
    else:
        capitais_proprios = "N/A"
    
    # [PRAZO_FINANCIAMENTO] — Prazo em anos/meses
    # FIX (Pacote K): adicionado path credit_data.loan_term_years — é o nome
    # usado no cartão "Dados de Crédito" do ProcessDetails.js (linha 4743).
    prazo_raw = (
        credit_data.get("loan_term_years")
        or financial_data.get("prazo_financiamento")
        or financial_data.get("loan_term")
        or financial_data.get("prazo")
        or financial_data.get("prazo_anos")
    )
    if prazo_raw:
        try:
            prazo_val = int(float(prazo_raw))
            prazo_financiamento = f"{prazo_val} anos"
        except (ValueError, TypeError):
            prazo_financiamento = safe_val(prazo_raw)
    else:
        prazo_financiamento = "N/A"
    
    # [COMPRA_SOZINHO] — Se há co-titulares
    co_buyers = process.get("co_buyers") or process.get("compradores") or []
    has_cotitular = (
        has_second_proponent
        or (isinstance(co_buyers, list) and len(co_buyers) > 0)
        or num_titulares > 1
    )
    compra_sozinho = "Não (Com Co-titular)" if has_cotitular else "Sim"
    
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
        
        # Variáveis Financeiras (Templates de Bancos)
        "CAPITAIS_PROPRIOS": capitais_proprios,
        "VALOR_IMOVEL": valor_imovel,
        "VALOR_FINANCIAMENTO": valor_financiamento,
        "PRAZO_FINANCIAMENTO": prazo_financiamento,
        "COMPRA_SOZINHO": compra_sozinho,
        
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
        except Exception:
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
    # tem_creditos_activos pode ser lista (novos dados) ou bool (legacy)
    _tca2 = financial_data.get("tem_creditos_activos")
    if isinstance(_tca2, list) and len(_tca2) > 0:
        situacao_bancaria.append(f"Tem créditos ativos: {', '.join(_tca2)}")
    elif isinstance(_tca2, bool) and _tca2:
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
