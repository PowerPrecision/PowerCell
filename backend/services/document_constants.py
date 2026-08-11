"""
Constantes partilhadas das rotas de documentos (mensagens de erro / defaults / HTTP).

Extraído de `routes/documents.py`.
"""

# ====================================================================
# CONSTANTES PARA MENSAGENS DE ERRO (SonarQube - DRY)
# ====================================================================
ERROR_CLIENT_NOT_FOUND = "Cliente não encontrado"
ERROR_PROCESS_NOT_FOUND = "Processo não encontrado"
ERROR_S3_NOT_CONFIGURED = "S3 não configurado"
ERROR_FILE_ACCESS_DENIED = "Acesso não autorizado a este ficheiro"
ERROR_S3_UPLOAD_FAILED = "Erro ao enviar ficheiro para o armazenamento S3"
ERROR_DOWNLOAD_URL = "Erro ao gerar link de download"
ERROR_PRESIGNED_URL = "Erro ao gerar URL"
ERROR_DELETE_FILE = "Erro ao eliminar ficheiro"
ERROR_RECORD_NOT_FOUND = "Registo não encontrado"
ERROR_S3_FILE_NOT_FOUND = "Ficheiro não encontrado no S3"
ERROR_S3_ACCESS = "Erro ao aceder ao ficheiro"
ERROR_CATEGORIZE_DOC = "Erro ao categorizar documento"
ERROR_NO_VALID_FILES = "Nenhum ficheiro válido enviado"
ERROR_NO_SUGGESTIONS = "Nenhuma sugestão enviada"
ERROR_NO_ORGANIZATION = "Nenhuma organização especificada"
ERROR_S3_PATH_REQUIRED = "s3_path é obrigatório"
ERROR_DOC_NOT_CATEGORIZED = (
    "Documento não foi categorizado pela IA. Execute a categorização primeiro."
)
ERROR_NEW_NAME_REQUIRED = "novo_nome é obrigatório quando apply_ai_name=False"
ERROR_RENAME_FAILED = "Falha ao renomear ficheiro no S3"
ERROR_CLIENT_WITHOUT_PROCESS = (
    "Cliente encontrado mas sem processo associado. Não é possível fazer upload."
)

# ====================================================================
# CONSTANTES PARA VALORES DEFAULT (SonarQube - DRY)
# ====================================================================
DEFAULT_CLIENT_NAME = "Cliente"
DEFAULT_CONSULTOR_NAME = "N/D"
DEFAULT_FILE_PREFIX = "Ficheiro: "
MIME_TYPE_PDF = "application/pdf"

# ====================================================================
# CONSTANTES PARA RESPOSTAS HTTP (SonarQube - Documentation)
# ====================================================================
HTTP_400_RESPONSE = {"description": "Bad Request - Parâmetros inválidos"}
HTTP_403_RESPONSE = {"description": "Forbidden - Acesso não autorizado"}
HTTP_404_RESPONSE = {"description": "Not Found - Recurso não encontrado"}
HTTP_500_RESPONSE = {"description": "Internal Server Error - Erro interno do servidor"}

# Mapa de categorias para pedidos de documentos do portal
DOCUMENT_CATEGORY_MAP = {
    "Cartao_Cidadao": {"label": "Cartão de Cidadão", "icon": "🪪"},
    "IRS": {"label": "Declaração de IRS", "icon": "📋"},
    "Recibo_Vencimento": {"label": "Recibo de Vencimento", "icon": "💰"},
    "Comprovativo_IBAN": {"label": "Comprovativo de IBAN", "icon": "🏦"},
    "Certidao_Nascimento": {"label": "Certidão de Nascimento", "icon": "📄"},
    "Atestado_Trabalho": {"label": "Atestado de Trabalho", "icon": "🏢"},
    "Mapa_Creditos": {"label": "Mapa de Créditos", "icon": "📊"},
    "Declaracao_Imposto_Renda": {"label": "Declaração de Imposto de Renda", "icon": "📑"},
    "Certidao_Permanente": {"label": "Certidão Permanente", "icon": "📜"},
    "Contrato_Promessa": {"label": "Contrato de Promessa", "icon": "📝"},
    "Plantas_Casa": {"label": "Plantas da Casa", "icon": "🏠"},
    "Certificado_Energetico": {"label": "Certificado Energético", "icon": "⚡"},
    "Outros": {"label": "Outro Documento", "icon": "📎"},
}
