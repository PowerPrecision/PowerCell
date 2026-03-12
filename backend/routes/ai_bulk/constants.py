"""
Constantes para o módulo AI Bulk.
Extraído de ai_bulk.py para melhor organização (SonarQube).
"""

# ====================================================================
# TAMANHO DO CHUNK PARA LEITURA
# ====================================================================
CHUNK_SIZE = 64 * 1024  # 64KB

# ====================================================================
# MENSAGENS DE ERRO
# ====================================================================
ERROR_PROCESS_NOT_FOUND = "Processo não encontrado"
ERROR_SESSION_NOT_FOUND = "Sessão não encontrada"
ERROR_JOB_NOT_FOUND = "Job não encontrado"
ERROR_CLIENT_NOT_FOUND = "Cliente não encontrado"
ERROR_INVALID_INDEX = "Índice inválido"
ERROR_AGGREGATION_SESSION_NOT_FOUND = "Sessão de agregação não encontrada"
ERROR_AGGREGATION_SESSION_EXPIRED = "Sessão de agregação expirada"
MSG_DUPLICATE_DOCUMENT_IGNORED = "Documento duplicado ignorado"
MSG_DUPLICATE_DOCUMENT_CACHED = "Documento duplicado encontrado em cache"
ERROR_ONLY_RUNNING_JOBS_CAN_CANCEL = "Apenas jobs em execução podem ser cancelados"
ERROR_ONLY_RUNNING_JOBS_CAN_PAUSE = "Apenas jobs em execução podem ser pausados"
ERROR_ONLY_PAUSED_JOBS_CAN_RESUME = "Apenas jobs pausados podem ser retomados"
REASON_MANUALLY_EDITED = "Campo editado manualmente"

# ====================================================================
# NOMES NORMALIZADOS DE DOCUMENTOS
# ====================================================================
NORMALIZED_NAMES = {
    "cc": "CC.pdf",
    "recibo_vencimento": "Recibo_Vencimento.pdf",
    "irs": "IRS.pdf",
    "contrato_trabalho": "Contrato_Trabalho.pdf",
    "caderneta_predial": "Caderneta_Predial.pdf",
    "extrato_bancario": "Extrato_Bancario.pdf",
    "outro": "Documento.pdf"
}

# ====================================================================
# PADRÕES PARA DETETAR CC FRENTE/VERSO
# ====================================================================
CC_FRENTE_PATTERNS = ["frente", "front", "_f.", "_f_", "cc_1", "cc1", "ccf"]
CC_VERSO_PATTERNS = ["verso", "back", "tras", "_v.", "_v_", "cc_2", "cc2", "ccv"]

# ====================================================================
# TIPOS DE DOCUMENTOS PROPENSOS A DUPLICADOS
# ====================================================================
DUPLICATE_PRONE_TYPES = {
    "recibo_vencimento",  # Recibos de vencimento mensais
    "extrato_bancario",   # Extratos bancários
    "recibo",             # Recibos genéricos
    "irs",                # Declarações IRS (mesmo ano)
    "contrato_trabalho",  # Contratos de trabalho
    "certidao",           # Certidões
}

# ====================================================================
# MAPEAMENTO DE TIPOS DE DOCUMENTO PARA CATEGORIAS S3
# ====================================================================
DOCUMENT_TYPE_TO_CATEGORY = {
    "cc": "Documentos Pessoais",
    "passaporte": "Documentos Pessoais",
    "carta_conducao": "Documentos Pessoais",
    "comprovativo_morada": "Documentos Pessoais",
    "irs": "Financeiros",
    "recibo_vencimento": "Financeiros",
    "extrato_bancario": "Financeiros",
    "nota_liquidacao": "Financeiros",
    "contrato_trabalho": "Financeiros",
    "caderneta_predial": "Imóvel",
    "certidao_teor": "Imóvel",
    "cpcv": "Imóvel",
    "avaliacao": "Imóvel",
    "simulacao": "Bancários",
    "pre_aprovacao": "Bancários",
}

# ====================================================================
# MAPEAMENTO CAMPO → SECÇÃO DA FICHA DE CLIENTE
# ====================================================================
FIELD_TO_SECTION = {
    # Dados pessoais
    "nome": "personal_data",
    "name": "personal_data",
    "nif": "personal_data",
    "NIF": "personal_data",
    "data_nascimento": "personal_data",
    "morada": "personal_data",
    "codigo_postal": "personal_data",
    "localidade": "personal_data",
    "telefone": "personal_data",
    "email": "personal_data",
    "estado_civil": "personal_data",
    "nacionalidade": "personal_data",
    "cc_numero": "personal_data",
    "cc_validade": "personal_data",
    "genero": "personal_data",
    
    # Dados profissionais
    "profissao": "financial_data",
    "entidade_empregadora": "financial_data",
    "tipo_contrato": "financial_data",
    "antiguidade": "financial_data",
    "rendimento_mensal": "financial_data",
    "monthly_income": "financial_data",
    "outros_rendimentos": "financial_data",
    
    # Dados do imóvel
    "tipo_imovel": "real_estate_data",
    "finalidade": "real_estate_data",
    "valor_imovel": "real_estate_data",
    "morada_imovel": "real_estate_data",
    "distrito": "real_estate_data",
    "concelho": "real_estate_data",
    "freguesia": "real_estate_data",
}

# ====================================================================
# PLACEHOLDERS CONHECIDOS (valores a ignorar)
# ====================================================================
KNOWN_PLACEHOLDERS = {
    # Datas
    'YYYY-MM-DD', 'DD/MM/YYYY', 'DD-MM-YYYY',
    # Valores genéricos
    'N/A', 'NA', 'NULL', 'NONE', '',
    # Números placeholder
    '123456789', '000000000', '0', '00000000', '12345678',
    # Patterns
    'YYYY', 'DD'
}
