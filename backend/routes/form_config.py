"""
Rotas para configuração dinâmica do formulário público.
Permite ao admin gerir quais campos são visíveis/obrigatórios e criar campos personalizados.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import db
from services.auth import require_roles, require_management
from models.auth import UserRole
from datetime import datetime, timezone
import uuid
from utils.input_sanitization import sanitize_string

router = APIRouter(prefix="/admin/form-config", tags=["form-config"])


class FormFieldConfig(BaseModel):
    """Configuração de um campo individual do formulário público.

    Cada instância define como um campo deve ser renderizado no
    formulário de registo público: visibilidade, obrigatoriedade,
    tipo de input, ordem, e opções (para selects/checkboxes).

    Attributes:
        field_key: Identificador único do campo (ex: "nome", "nif").
        label: Etiqueta visível para o utilizador.
        step: Número do passo do formulário (1-6).
        is_visible: Se o campo é mostrado no formulário.
        is_required: Se o campo é obrigatório para submissão.
        field_type: Tipo de input ("text", "select", "checkbox", etc.).
        options: Lista de opções para selects/checkboxes/radios.
        order: Ordem de apresentação dentro do passo.
        is_custom: Se o campo foi criado pelo admin (vs padrão).
        placeholder: Texto placeholder para o campo.
        hint: Texto de ajuda abaixo do campo.
    """
    field_key: str
    label: str
    step: int
    is_visible: bool = True
    is_required: bool = False
    field_type: str = "text"
    options: Optional[list] = None
    order: int = 0
    is_custom: bool = False
    placeholder: Optional[str] = None
    hint: Optional[str] = None


class FormConfigUpdate(BaseModel):
    """Payload para atualizar a configuração completa do formulário.

    Envia a lista completa de campos com as suas configurações.
    Os campos não incluídos são removidos da configuração.

    Attributes:
        fields: Lista de dicionários com a configuração de cada campo.
    """
    fields: list[dict]


class CustomFieldCreate(BaseModel):
    """Payload para criar um campo personalizado no formulário.

    Campos personalizados permitem ao admin recolher informações
    adicionais não previstas no formulário padrão.

    Attributes:
        label: Etiqueta visível do campo.
        step: Número do passo onde o campo aparece (1-6).
        field_type: Tipo de input ("text", "select", "checkbox", "radio", "date", "number").
        is_required: Se o campo é obrigatório.
        options: Lista de opções para selects/checkboxes/radios.
        placeholder: Texto placeholder.
        hint: Texto de ajuda.
    """
    label: str
    step: int  # 1-6
    field_type: str  # text, select, checkbox, radio, date, number
    is_required: bool = False
    options: Optional[list] = None  # For select/checkbox/radio
    placeholder: Optional[str] = None
    hint: Optional[str] = None


class TemplateSave(BaseModel):
    """Payload para guardar uma configuração de formulário como template.

    Permite ao admin guardar e reutilizar configurações do formulário.

    Attributes:
        name: Nome do template.
        description: Descrição opcional do template.
    """
    name: str
    description: Optional[str] = None


# Configuração padrão do formulário
# Fonte de verdade: todos os campos devem existir aqui para aparecerem no Gestor de Formulários.
# O frontend (PublicClientForm.js) usa getFieldStyle/getFieldLabel/isFieldRequired para
# aplicar visibilidade, labels e obrigatoriedade a partir deste config.
#
# Cada campo pode ter:
#   - options: lista de opções para selects/checkboxes/radios
#   - depends_on: regras de visibilidade condicional
#     {"field": X, "value": V}     → visível quando campo X == V
#     {"field": X, "not_value": V} → visível quando campo X != V
#     {"field": X, "contains": V}  → visível quando campo X (array) contém V
#   - data_path: onde o campo vai no payload (root, personal_data, titular2_data, real_estate_data, financial_data)
DEFAULT_FORM_CONFIG = [
    # ── Step 1 — Dados Pessoais - Titular ──────────────────────────────
    {"field_key": "name", "label": "Nome completo", "step": 1, "is_visible": True, "is_required": True, "field_type": "text", "order": 1, "is_custom": False, "data_path": "root"},
    {"field_key": "email", "label": "Email", "step": 1, "is_visible": True, "is_required": True, "field_type": "email", "order": 2, "is_custom": False, "data_path": "root"},
    {"field_key": "phone", "label": "Telemóvel", "step": 1, "is_visible": True, "is_required": True, "field_type": "tel", "order": 3, "is_custom": False, "data_path": "root"},
    {"field_key": "nif", "label": "NIF", "step": 1, "is_visible": True, "is_required": True, "field_type": "text", "order": 4, "is_custom": False, "data_path": "personal_data"},
    {"field_key": "documento_id", "label": "Cartão de Cidadão/Passaporte", "step": 1, "is_visible": True, "is_required": True, "field_type": "text", "order": 5, "is_custom": False, "data_path": "personal_data"},
    {"field_key": "data_validade_cc", "label": "Data Validade CC", "step": 1, "is_visible": True, "is_required": True, "field_type": "date", "order": 6, "is_custom": False, "data_path": "personal_data"},
    {"field_key": "naturalidade", "label": "Naturalidade", "step": 1, "is_visible": True, "is_required": True, "field_type": "text", "order": 7, "is_custom": False, "data_path": "personal_data"},
    {"field_key": "nacionalidade", "label": "Nacionalidade", "step": 1, "is_visible": True, "is_required": True, "field_type": "text", "order": 8, "is_custom": False, "data_path": "personal_data"},
    {"field_key": "morada_fiscal", "label": "Morada Fiscal", "step": 1, "is_visible": True, "is_required": True, "field_type": "text", "order": 9, "is_custom": False, "data_path": "personal_data"},
    {"field_key": "birth_date", "label": "Data de Nascimento", "step": 1, "is_visible": True, "is_required": True, "field_type": "date", "order": 10, "is_custom": False, "data_path": "personal_data"},
    {"field_key": "estado_civil", "label": "Estado Civil", "step": 1, "is_visible": True, "is_required": True, "field_type": "select", "order": 11, "is_custom": False, "data_path": "personal_data",
     "options": ["Solteiro(a)", "Casado(a) - Comunhão de Bens", "Casado(a) - Comunhão de Aquiridos", "Casado(a) - Separação de Bens", "Divorciado(a)", "Viúvo(a)", "União de Facto"]},
    {"field_key": "menor_35_anos", "label": "Menor de 35 anos", "step": 1, "is_visible": True, "is_required": False, "field_type": "checkbox", "order": 12, "is_custom": False, "data_path": "personal_data"},
    {"field_key": "compra_tipo", "label": "Tipo de compra", "step": 1, "is_visible": True, "is_required": False, "field_type": "select", "order": 13, "is_custom": False, "data_path": "personal_data",
     "options": ["individual", "outra_pessoa"]},
    {"field_key": "sexo", "label": "Sexo", "step": 1, "is_visible": True, "is_required": False, "field_type": "radio", "order": 14, "is_custom": False, "data_path": "personal_data",
     "options": ["Masculino", "Feminino", "Outro"]},
    {"field_key": "codigo_postal", "label": "Código Postal", "step": 1, "is_visible": True, "is_required": False, "field_type": "text", "order": 15, "is_custom": False, "data_path": "personal_data"},
    {"field_key": "profissao", "label": "Profissão", "step": 1, "is_visible": True, "is_required": False, "field_type": "text", "order": 16, "is_custom": False, "data_path": "personal_data"},
    {"field_key": "altura", "label": "Altura (m)", "step": 1, "is_visible": False, "is_required": False, "field_type": "number", "order": 17, "is_custom": False, "data_path": "personal_data"},

    # ── Step 2 — Segundo Titular (condicional: compra_tipo === "outra_pessoa") ─
    {"field_key": "titular2_name", "label": "Nome do 2º Titular", "step": 2, "is_visible": True, "is_required": False, "field_type": "text", "order": 1, "is_custom": False, "data_path": "titular2_data", "depends_on": {"field": "compra_tipo", "value": "outra_pessoa"}},
    {"field_key": "titular2_email", "label": "Email (2º Titular)", "step": 2, "is_visible": True, "is_required": False, "field_type": "email", "order": 2, "is_custom": False, "data_path": "titular2_data", "depends_on": {"field": "compra_tipo", "value": "outra_pessoa"}},
    {"field_key": "titular2_phone", "label": "Telefone (2º Titular)", "step": 2, "is_visible": True, "is_required": False, "field_type": "tel", "order": 3, "is_custom": False, "data_path": "titular2_data", "depends_on": {"field": "compra_tipo", "value": "outra_pessoa"}},
    {"field_key": "titular2_nif", "label": "NIF (2º Titular)", "step": 2, "is_visible": True, "is_required": False, "field_type": "text", "order": 4, "is_custom": False, "data_path": "titular2_data", "depends_on": {"field": "compra_tipo", "value": "outra_pessoa"}},
    {"field_key": "titular2_documento_id", "label": "Documento ID (2º Titular)", "step": 2, "is_visible": True, "is_required": False, "field_type": "text", "order": 5, "is_custom": False, "data_path": "titular2_data", "depends_on": {"field": "compra_tipo", "value": "outra_pessoa"}},
    {"field_key": "titular2_naturalidade", "label": "Naturalidade (2º Titular)", "step": 2, "is_visible": True, "is_required": False, "field_type": "text", "order": 6, "is_custom": False, "data_path": "titular2_data", "depends_on": {"field": "compra_tipo", "value": "outra_pessoa"}},
    {"field_key": "titular2_nacionalidade", "label": "Nacionalidade (2º Titular)", "step": 2, "is_visible": True, "is_required": False, "field_type": "text", "order": 7, "is_custom": False, "data_path": "titular2_data", "depends_on": {"field": "compra_tipo", "value": "outra_pessoa"}},
    {"field_key": "titular2_morada_fiscal", "label": "Morada Fiscal (2º Titular)", "step": 2, "is_visible": True, "is_required": False, "field_type": "text", "order": 8, "is_custom": False, "data_path": "titular2_data", "depends_on": {"field": "compra_tipo", "value": "outra_pessoa"}},
    {"field_key": "titular2_birth_date", "label": "Data Nascimento (2º Titular)", "step": 2, "is_visible": True, "is_required": False, "field_type": "date", "order": 9, "is_custom": False, "data_path": "titular2_data", "depends_on": {"field": "compra_tipo", "value": "outra_pessoa"}},
    {"field_key": "titular2_estado_civil", "label": "Estado Civil (2º Titular)", "step": 2, "is_visible": True, "is_required": False, "field_type": "select", "order": 10, "is_custom": False, "data_path": "titular2_data", "depends_on": {"field": "compra_tipo", "value": "outra_pessoa"}},

    # ── Step 3 — Dados do Imóvel ──────────────────────────────────────
    {"field_key": "finalidade", "label": "Finalidade do pedido", "step": 3, "is_visible": True, "is_required": True, "field_type": "select", "order": 1, "is_custom": False, "data_path": "real_estate_data",
     "options": ["compra_imovel", "refinanciamento"]},
    {"field_key": "tipo_imovel", "label": "Tipo de imóvel", "step": 3, "is_visible": True, "is_required": True, "field_type": "select", "order": 2, "is_custom": False, "data_path": "real_estate_data",
     "options": ["Apartamento", "Moradia", "Terreno", "Outro"],
     "depends_on": {"field": "finalidade", "not_value": "refinanciamento"}},
    {"field_key": "num_quartos", "label": "Nº quartos", "step": 3, "is_visible": True, "is_required": True, "field_type": "select", "order": 3, "is_custom": False, "data_path": "real_estate_data",
     "options": ["T0", "T1", "T2", "T3", "T4", "T5+"],
     "depends_on": {"field": "finalidade", "not_value": "refinanciamento"}},
    {"field_key": "localizacao", "label": "Localização/Zona preferida", "step": 3, "is_visible": True, "is_required": True, "field_type": "text", "order": 4, "is_custom": False, "data_path": "real_estate_data",
     "depends_on": {"field": "finalidade", "not_value": "refinanciamento"}},
    {"field_key": "caracteristicas", "label": "Características Pretendidas", "step": 3, "is_visible": True, "is_required": False, "field_type": "checkbox", "order": 5, "is_custom": False, "data_path": "real_estate_data",
     "options": ["Elevador", "2 WCs", "Transportes perto", "Garagem", "Piscina", "Varanda", "Andar máximo", "Outro"],
     "depends_on": {"field": "finalidade", "not_value": "refinanciamento"}},
    {"field_key": "outras_caracteristicas", "label": "Outras características", "step": 3, "is_visible": True, "is_required": False, "field_type": "text", "order": 6, "is_custom": False, "data_path": "real_estate_data",
     "depends_on": {"field": "caracteristicas", "contains": "Outro"}},
    {"field_key": "area_pretendida", "label": "Área pretendida (m²)", "step": 3, "is_visible": True, "is_required": False, "field_type": "number", "order": 7, "is_custom": False, "data_path": "real_estate_data",
     "depends_on": {"field": "finalidade", "not_value": "refinanciamento"}},
    {"field_key": "valor_maximo_imovel", "label": "Valor máximo do imóvel", "step": 3, "is_visible": True, "is_required": False, "field_type": "number", "order": 8, "is_custom": False, "data_path": "real_estate_data",
     "depends_on": {"field": "finalidade", "not_value": "refinanciamento"}},
    {"field_key": "ja_tem_casa_escolhida", "label": "Já tem casa escolhida", "step": 3, "is_visible": True, "is_required": False, "field_type": "checkbox", "order": 9, "is_custom": False, "data_path": "real_estate_data",
     "depends_on": {"field": "finalidade", "not_value": "refinanciamento"}},
    {"field_key": "proprietario_nome", "label": "Nome do proprietário", "step": 3, "is_visible": True, "is_required": False, "field_type": "text", "order": 10, "is_custom": False, "data_path": "real_estate_data",
     "depends_on": {"field": "ja_tem_casa_escolhida", "value": True}},
    {"field_key": "proprietario_contacto", "label": "Contacto do proprietário", "step": 3, "is_visible": True, "is_required": False, "field_type": "text", "order": 11, "is_custom": False, "data_path": "real_estate_data",
     "depends_on": {"field": "ja_tem_casa_escolhida", "value": True}},
    {"field_key": "caracteristicas_imovel", "label": "Características do imóvel escolhido", "step": 3, "is_visible": True, "is_required": False, "field_type": "textarea", "order": 12, "is_custom": False, "data_path": "real_estate_data",
     "depends_on": {"field": "ja_tem_casa_escolhida", "value": True}},
    {"field_key": "outras_informacoes", "label": "Outras informações", "step": 3, "is_visible": True, "is_required": False, "field_type": "textarea", "order": 13, "is_custom": False, "data_path": "real_estate_data",
     "depends_on": {"field": "finalidade", "not_value": "refinanciamento"}},
    # Campos de refinanciamento (step 3, condicionais)
    {"field_key": "valor_transferencia", "label": "Valor a Transferir/Consolidar (€)", "step": 3, "is_visible": True, "is_required": False, "field_type": "number", "order": 14, "is_custom": False, "data_path": "real_estate_data",
     "depends_on": {"field": "finalidade", "value": "refinanciamento"}},
    {"field_key": "valor_extra", "label": "Valor Extra Necessário (€)", "step": 3, "is_visible": True, "is_required": False, "field_type": "number", "order": 15, "is_custom": False, "data_path": "real_estate_data",
     "depends_on": {"field": "finalidade", "value": "refinanciamento"}},
    {"field_key": "prazo_pretendido", "label": "Prazo pretendido (anos)", "step": 3, "is_visible": True, "is_required": False, "field_type": "select", "order": 16, "is_custom": False, "data_path": "real_estate_data",
     "options": ["5", "10", "15", "20", "25", "30", "35", "40"],
     "depends_on": {"field": "finalidade", "value": "refinanciamento"}},

    # ── Step 4 — Situação Financeira ──────────────────────────────────
    {"field_key": "acesso_portal_financas", "label": "Acesso ao portal das finanças", "step": 4, "is_visible": True, "is_required": False, "field_type": "select", "order": 1, "is_custom": False, "data_path": "financial_data", "options": ["Portal das Finanças", "Segurança Social Direta", "Ambos", "Nenhuma"]},
    {"field_key": "chave_movel_digital", "label": "Chave Móvel Digital", "step": 4, "is_visible": True, "is_required": True, "field_type": "select", "order": 2, "is_custom": False, "data_path": "financial_data", "options": ["Sim", "Não"]},
    {"field_key": "renda_habitacao_atual", "label": "Renda de habitação atual", "step": 4, "is_visible": True, "is_required": False, "field_type": "number", "order": 3, "is_custom": False, "data_path": "financial_data"},
    {"field_key": "precisa_vender_casa", "label": "Precisa de vender casa?", "step": 4, "is_visible": True, "is_required": False, "field_type": "select", "order": 4, "is_custom": False, "data_path": "financial_data", "options": ["Sim", "Não"]},
    {"field_key": "efetivo", "label": "Efetivo?", "step": 4, "is_visible": True, "is_required": False, "field_type": "select", "order": 5, "is_custom": False, "data_path": "financial_data", "options": ["Sim", "Não"]},
    {"field_key": "trabalha_estrangeiro", "label": "Trabalha no estrangeiro?", "step": 4, "is_visible": True, "is_required": False, "field_type": "select", "order": 6, "is_custom": False, "data_path": "financial_data", "options": ["Sim", "Não"]},
    {"field_key": "employment_type", "label": "Tipo de Contrato de Trabalho", "step": 4, "is_visible": True, "is_required": True, "field_type": "select", "order": 7, "is_custom": False, "data_path": "financial_data",
     "options": ["Efetivo", "Termo Certo", "Termo Incerto", "Independente", "Empresário", "Reformado", "Desempregado"]},
    {"field_key": "employment_duration", "label": "Antiguidade no emprego", "step": 4, "is_visible": True, "is_required": False, "field_type": "text", "order": 8, "is_custom": False, "data_path": "financial_data"},
    {"field_key": "employer_name", "label": "Nome da empresa", "step": 4, "is_visible": True, "is_required": False, "field_type": "text", "order": 9, "is_custom": False, "data_path": "financial_data"},
    {"field_key": "employer_nif", "label": "NIF da empresa", "step": 4, "is_visible": True, "is_required": False, "field_type": "text", "order": 10, "is_custom": False, "data_path": "financial_data"},
    {"field_key": "fiador", "label": "Fiador?", "step": 4, "is_visible": True, "is_required": False, "field_type": "select", "order": 11, "is_custom": False, "data_path": "financial_data", "options": ["Sim", "Não"]},
    {"field_key": "salario_liquido", "label": "Salário mensal líquido", "step": 4, "is_visible": True, "is_required": True, "field_type": "number", "order": 12, "is_custom": False, "data_path": "financial_data"},

    # ── Step 5 — Créditos e Capital ───────────────────────────────────
    {"field_key": "bancos_creditos", "label": "Bancos com créditos ativos", "step": 5, "is_visible": True, "is_required": True, "field_type": "checkbox", "order": 1, "is_custom": False, "data_path": "financial_data",
     "options": ["ABANCA", "BBVA", "BEST", "BIG", "BPI", "CGD", "Crédito Agrícola", "CTT", "Millennium bcp", "Novo Banco", "Popular", "Santander Totta", "Outro"]},
    {"field_key": "tem_creditos_activos", "label": "Bancos com contas abertas", "step": 5, "is_visible": True, "is_required": False, "field_type": "checkbox", "order": 2, "is_custom": False, "data_path": "financial_data",
     "options": ["ABANCA", "BBVA", "BEST", "BIG", "BPI", "CGD", "Crédito Agrícola", "CTT", "Millennium bcp", "Novo Banco", "Popular", "Santander Totta", "Nenhuma"]},
    {"field_key": "bancos_simulacoes", "label": "Simulações efetuadas", "step": 5, "is_visible": True, "is_required": False, "field_type": "checkbox", "order": 3, "is_custom": False, "data_path": "financial_data",
     "options": ["ABANCA", "BBVA", "BEST", "BIG", "BPI", "CGD", "Crédito Agrícola", "CTT", "Millennium bcp", "Novo Banco", "Popular", "Santander Totta", "Nenhuma"]},
    {"field_key": "tempo_restante_credito", "label": "Tempo restante do crédito (meses)", "step": 5, "is_visible": True, "is_required": False, "field_type": "select", "order": 4, "is_custom": False, "data_path": "financial_data",
     "options": ["Menos de 1 ano", "1 a 5 anos", "5 a 10 anos", "10 a 15 anos", "15 a 20 anos", "Mais de 20 anos"],
     "depends_on": {"field": "finalidade", "value": "refinanciamento"}},
    {"field_key": "capital_proprio", "label": "Capital próprio disponível", "step": 5, "is_visible": True, "is_required": True, "field_type": "number", "order": 5, "is_custom": False, "data_path": "financial_data"},
    {"field_key": "valor_financiado", "label": "Valor a financiar", "step": 5, "is_visible": True, "is_required": True, "field_type": "number", "order": 6, "is_custom": False, "data_path": "financial_data"},

    # ── Step 6 — Confirmação / Consentimentos ────────────────────────
    {"field_key": "consent_data", "label": "Autorizo o tratamento dos meus dados (RGPD)", "step": 6, "is_visible": True, "is_required": True, "field_type": "checkbox", "order": 1, "is_custom": False, "data_path": "root"},
    {"field_key": "consent_contact", "label": "Aceito ser contactado pela equipa", "step": 6, "is_visible": True, "is_required": True, "field_type": "checkbox", "order": 2, "is_custom": False, "data_path": "root"},
]


@router.get("/fields")
async def get_form_config(user: dict = Depends(require_management())):
    """Obter configuração atual do formulário.

    Se existir config na DB, faz merge com DEFAULT_FORM_CONFIG para garantir
    que novos campos adicionados em actualizações aparecem automaticamente.
    Campos customizados (is_custom=True) existentes na DB são preservados.
    """
    config = await db.form_config.find_one({"type": "public_form"}, {"_id": 0})
    if not config:
        return {"fields": DEFAULT_FORM_CONFIG}

    saved_fields = config.get("fields", [])
    # Construir mapa dos campos existentes (incluindo custom)
    saved_map = {f["field_key"]: f for f in saved_fields}
    merged = []

    # Primeiro: adicionar todos os campos do DEFAULT (nativos)
    added_keys = set()
    for default_field in DEFAULT_FORM_CONFIG:
        key = default_field["field_key"]
        if key in saved_map:
            # Campo existe — usar versão salva (com eventuais alterações do admin)
            merged.append(saved_map[key])
        else:
            # Campo novo (adicionado em actualização) — usar default
            merged.append(default_field)
        added_keys.add(key)

    # Depois: adicionar campos customizados que não existem no default
    for saved_field in saved_fields:
        key = saved_field["field_key"]
        if key not in added_keys:
            merged.append(saved_field)

    # Ordenar por step + order
    merged.sort(key=lambda f: (f.get("step", 0), f.get("order_index", f.get("order", 0))))
    return {"fields": merged}


@router.put("/fields")
async def update_form_config(
    data: FormConfigUpdate,
    user: dict = Depends(require_management())
):
    """Actualizar configuração do formulário."""
    now = datetime.now(timezone.utc).isoformat()
    
    # Sanitize field labels and options in incoming data
    for field in data.fields:
        if field.get("label"):
            field["label"] = sanitize_string(field["label"], max_length=200)
        if field.get("placeholder"):
            field["placeholder"] = sanitize_string(field["placeholder"], max_length=200)
        if field.get("hint"):
            field["hint"] = sanitize_string(field["hint"], max_length=200)
        if field.get("options") and isinstance(field["options"], list):
            field["options"] = [sanitize_string(opt, max_length=200) if isinstance(opt, str) else opt for opt in field["options"]]
    
    await db.form_config.update_one(
        {"type": "public_form"},
        {"$set": {
            "type": "public_form",
            "fields": data.fields,
            "updated_at": now,
            "updated_by": user.get("id"),
        }},
        upsert=True
    )
    
    return {"message": "Configuração atualizada com sucesso", "updated_at": now}


@router.post("/custom-field")
async def create_custom_field(
    data: CustomFieldCreate,
    user: dict = Depends(require_management())
):
    """Criar um campo personalizado no formulário."""
    if data.step < 1 or data.step > 6:
        raise HTTPException(status_code=400, detail="Passo deve ser entre 1 e 6")
    
    if data.field_type not in ("text", "select", "checkbox", "radio", "date", "number"):
        raise HTTPException(status_code=400, detail="Tipo de campo inválido")
    
    if data.field_type in ("select", "checkbox", "radio") and not data.options:
        raise HTTPException(status_code=400, detail="Campos de seleção requerem opções")
    
    # Sanitize user-provided text fields
    safe_label = sanitize_string(data.label, max_length=200)
    safe_placeholder = sanitize_string(data.placeholder, max_length=200) if data.placeholder else None
    safe_hint = sanitize_string(data.hint, max_length=200) if data.hint else None
    safe_options = [sanitize_string(opt, max_length=200) if isinstance(opt, str) else opt for opt in (data.options or [])]
    
    # Gerar key único a partir do label
    field_key = f"custom_{uuid.uuid4().hex[:8]}"
    
    # Obter config atual
    config = await db.form_config.find_one({"type": "public_form"}, {"_id": 0})
    fields = config.get("fields", DEFAULT_FORM_CONFIG.copy()) if config else DEFAULT_FORM_CONFIG.copy()
    
    # Calcular order (último do passo)
    step_fields = [f for f in fields if f.get("step") == data.step]
    max_order = max((f.get("order", 0) for f in step_fields), default=0)
    
    new_field = {
        "field_key": field_key,
        "label": safe_label,
        "step": data.step,
        "is_visible": True,
        "is_required": data.is_required,
        "field_type": data.field_type,
        "options": safe_options,
        "order": max_order + 1,
        "order_index": max_order + 1,
        "is_custom": True,
        "placeholder": safe_placeholder,
        "hint": safe_hint,
    }
    
    fields.append(new_field)
    
    now = datetime.now(timezone.utc).isoformat()
    await db.form_config.update_one(
        {"type": "public_form"},
        {"$set": {
            "type": "public_form",
            "fields": fields,
            "updated_at": now,
            "updated_by": user.get("id"),
        }},
        upsert=True
    )
    
    return {"message": "Campo personalizado criado", "field": new_field}


@router.delete("/custom-field/{field_key}")
async def delete_custom_field(
    field_key: str,
    user: dict = Depends(require_management())
):
    """Eliminar campo personalizado do formulário."""
    config = await db.form_config.find_one({"type": "public_form"}, {"_id": 0})
    if not config:
        raise HTTPException(status_code=404, detail="Configuração não encontrada")
    
    fields = config.get("fields", [])
    
    target = next((f for f in fields if f.get("field_key") == field_key), None)
    if not target:
        raise HTTPException(status_code=404, detail="Campo não encontrado")
    
    if not target.get("is_custom"):
        raise HTTPException(status_code=400, detail="Não é possível eliminar campos padrão do sistema")
    
    fields = [f for f in fields if f.get("field_key") != field_key]
    
    now = datetime.now(timezone.utc).isoformat()
    await db.form_config.update_one(
        {"type": "public_form"},
        {"$set": {"fields": fields, "updated_at": now, "updated_by": user.get("id")}}
    )
    
    return {"message": "Campo personalizado eliminado"}


@router.post("/reset")
async def reset_form_config(user: dict = Depends(require_roles([UserRole.ADMIN]))):
    """Repor configuração padrão do formulário (remove campos personalizados)."""
    now = datetime.now(timezone.utc).isoformat()
    
    await db.form_config.update_one(
        {"type": "public_form"},
        {"$set": {
            "type": "public_form",
            "fields": DEFAULT_FORM_CONFIG,
            "updated_at": now,
            "updated_by": user.get("id"),
        }},
        upsert=True
    )
    
    return {"message": "Configuração reposta para valores padrão", "fields": DEFAULT_FORM_CONFIG}


# =============================================
# TEMPLATES DE FORMULÁRIO
# =============================================

# Template: Crédito Habitação - formulário completo
TEMPLATE_CREDITO_HABITACAO = {
    "name": "Crédito Habitação",
    "description": "Formulário completo para pedidos de crédito habitação. Inclui todos os campos padrão com dados do imóvel e histórico bancário.",
    "is_system": True,
    "fields": DEFAULT_FORM_CONFIG,  # Usa todos os campos padrão
}

# Template: Refinanciamento - sem dados de imóvel novo, foca em créditos existentes
_REFINANCIAMENTO_FIELDS = [f for f in DEFAULT_FORM_CONFIG if f["step"] != 3] + [
    {"field_key": "finalidade", "label": "Finalidade do refinanciamento", "step": 3, "is_visible": True, "is_required": True, "field_type": "select", "order": 1, "is_custom": False},
    {"field_key": "valor_transferencia", "label": "Valor a transferir/consolidar (€)", "step": 3, "is_visible": True, "is_required": True, "field_type": "number", "order": 2, "is_custom": False},
    {"field_key": "prazo_pretendido", "label": "Prazo pretendido (anos)", "step": 3, "is_visible": True, "is_required": True, "field_type": "number", "order": 3, "is_custom": False},
    {"field_key": "banco_atual", "label": "Banco do crédito atual", "step": 3, "is_visible": True, "is_required": True, "field_type": "text", "order": 4, "is_custom": False},
    {"field_key": "spread_atual", "label": "Spread atual (%)", "step": 3, "is_visible": True, "is_required": False, "field_type": "number", "order": 5, "is_custom": False},
]

TEMPLATE_REFINANCIAMENTO = {
    "name": "Refinanciamento",
    "description": "Formulário otimizado para pedidos de transferência/refinanciamento de crédito. Substitui dados do imóvel por dados do crédito existente.",
    "is_system": True,
    "fields": _REFINANCIAMENTO_FIELDS,
}

# Template: Crédito Pessoal - simplificado, sem dados imobiliários
_CREDITO_PESSOAL_FIELDS = [
    f for f in DEFAULT_FORM_CONFIG 
    if f["step"] in (1, 2, 4, 5) or f["field_key"] in ("compra_com_outra_pessoa", "titular2_name")
]
# Ajustar steps: remover step 3 (imóvel), renumerar
for f in _CREDITO_PESSOAL_FIELDS:
    if f["step"] == 4:
        f = {**f, "step": 3}
    elif f["step"] == 5:
        f = {**f, "step": 4}
# Rebuild with correct steps
_CP_REBUILT = []
for f in DEFAULT_FORM_CONFIG:
    if f["step"] == 1:
        _CP_REBUILT.append(f)
    elif f["step"] == 2:
        _CP_REBUILT.append(f)
    elif f["step"] == 4:
        _CP_REBUILT.append({**f, "step": 3})
    elif f["step"] == 5:
        _CP_REBUILT.append({**f, "step": 4})
# Add specific field for amount
_CP_REBUILT.append({"field_key": "montante_pretendido", "label": "Montante pretendido (€)", "step": 3, "is_visible": True, "is_required": True, "field_type": "number", "order": 0, "is_custom": False})
_CP_REBUILT.append({"field_key": "finalidade_credito", "label": "Finalidade do crédito", "step": 3, "is_visible": True, "is_required": True, "field_type": "text", "order": 0, "is_custom": False})

TEMPLATE_CREDITO_PESSOAL = {
    "name": "Crédito Pessoal",
    "description": "Formulário simplificado para crédito pessoal. Sem dados imobiliários, focado em situação financeira e montante pretendido.",
    "is_system": True,
    "fields": _CP_REBUILT,
}

SYSTEM_TEMPLATES = [TEMPLATE_CREDITO_HABITACAO, TEMPLATE_REFINANCIAMENTO, TEMPLATE_CREDITO_PESSOAL]


@router.get("/templates")
async def list_templates(user: dict = Depends(require_management())):
    """Listar todos os templates de formulário (sistema + personalizados)."""
    # Templates do sistema
    system = []
    for t in SYSTEM_TEMPLATES:
        system.append({
            "id": f"system_{t['name'].lower().replace(' ', '_')}",
            "name": t["name"],
            "description": t["description"],
            "is_system": True,
            "field_count": len(t["fields"]),
        })
    
    # Templates personalizados (guardados na DB)
    custom_templates = await db.form_templates.find(
        {}, {"_id": 0}
    ).to_list(100)
    
    for t in custom_templates:
        t["is_system"] = False
        t["field_count"] = len(t.get("fields", []))
    
    return {"templates": system + custom_templates}


@router.get("/templates/{template_id}/preview")
async def preview_template(
    template_id: str,
    user: dict = Depends(require_management())
):
    """Obter campos de um template para pré-visualização (sem ativar)."""
    if template_id.startswith("system_"):
        system_name = template_id.replace("system_", "").replace("_", " ")
        template = next(
            (t for t in SYSTEM_TEMPLATES if t["name"].lower() == system_name),
            None
        )
        if not template:
            raise HTTPException(status_code=404, detail="Template não encontrado")
        return {
            "name": template["name"],
            "description": template["description"],
            "fields": template["fields"],
            "is_system": True,
        }
    
    tpl = await db.form_templates.find_one({"id": template_id}, {"_id": 0})
    if not tpl:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    
    return {
        "name": tpl.get("name"),
        "description": tpl.get("description", ""),
        "fields": tpl.get("fields", []),
        "is_system": False,
    }


@router.post("/templates")
async def save_as_template(
    data: TemplateSave,
    user: dict = Depends(require_management())
):
    """Guardar a configuração atual como template."""
    if not data.name.strip():
        raise HTTPException(status_code=400, detail="Nome do template é obrigatório")
    
    # Sanitize user-provided text fields
    safe_name = sanitize_string(data.name, max_length=200)
    safe_description = sanitize_string(data.description, max_length=500) if data.description else ""
    
    # Obter config atual
    config = await db.form_config.find_one({"type": "public_form"}, {"_id": 0})
    fields = config.get("fields", DEFAULT_FORM_CONFIG) if config else DEFAULT_FORM_CONFIG
    
    template_id = f"tpl_{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    
    template_doc = {
        "id": template_id,
        "name": safe_name,
        "description": safe_description,
        "fields": fields,
        "created_at": now,
        "created_by": user.get("id"),
    }
    
    await db.form_templates.insert_one(template_doc)
    
    return {
        "message": "Template guardado com sucesso",
        "template": {
            "id": template_id,
            "name": safe_name,
            "description": safe_description,
            "field_count": len(fields),
            "created_at": now,
        }
    }


@router.post("/templates/{template_id}/activate")
async def activate_template(
    template_id: str,
    user: dict = Depends(require_management())
):
    """Ativar um template, substituindo a configuração atual do formulário."""
    now = datetime.now(timezone.utc).isoformat()
    
    # Verificar se é template do sistema
    if template_id.startswith("system_"):
        system_name = template_id.replace("system_", "").replace("_", " ")
        template = next(
            (t for t in SYSTEM_TEMPLATES if t["name"].lower() == system_name),
            None
        )
        if not template:
            raise HTTPException(status_code=404, detail="Template do sistema não encontrado")
        fields = template["fields"]
    else:
        # Template personalizado
        tpl = await db.form_templates.find_one({"id": template_id}, {"_id": 0})
        if not tpl:
            raise HTTPException(status_code=404, detail="Template não encontrado")
        fields = tpl.get("fields", DEFAULT_FORM_CONFIG)
    
    # Aplicar ao formulário ativo
    await db.form_config.update_one(
        {"type": "public_form"},
        {"$set": {
            "type": "public_form",
            "fields": fields,
            "updated_at": now,
            "updated_by": user.get("id"),
            "active_template": template_id,
        }},
        upsert=True
    )
    
    return {"message": "Template ativado com sucesso", "field_count": len(fields)}


@router.post("/templates/{template_id}/duplicate")
async def duplicate_template(
    template_id: str,
    user: dict = Depends(require_management())
):
    """Duplicar um template (sistema ou personalizado) como template personalizado."""
    now = datetime.now(timezone.utc).isoformat()
    
    # Obter fields do template original
    if template_id.startswith("system_"):
        system_name = template_id.replace("system_", "").replace("_", " ")
        template = next(
            (t for t in SYSTEM_TEMPLATES if t["name"].lower() == system_name),
            None
        )
        if not template:
            raise HTTPException(status_code=404, detail="Template não encontrado")
        fields = template["fields"]
        original_name = template["name"]
    else:
        tpl = await db.form_templates.find_one({"id": template_id}, {"_id": 0})
        if not tpl:
            raise HTTPException(status_code=404, detail="Template não encontrado")
        fields = tpl.get("fields", [])
        original_name = tpl.get("name", "Template")
    
    new_id = f"tpl_{uuid.uuid4().hex[:8]}"
    new_doc = {
        "id": new_id,
        "name": f"{original_name} (cópia)",
        "description": f"Cópia de {original_name}",
        "fields": fields,
        "created_at": now,
        "created_by": user.get("id"),
    }
    
    await db.form_templates.insert_one(new_doc)
    
    return {
        "message": "Template duplicado com sucesso",
        "template": {
            "id": new_id,
            "name": new_doc["name"],
            "field_count": len(fields),
        }
    }


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN]))
):
    """Eliminar template personalizado."""
    if template_id.startswith("system_"):
        raise HTTPException(status_code=400, detail="Não é possível eliminar templates do sistema")
    
    result = await db.form_templates.delete_one({"id": template_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Template não encontrado")
    
    return {"message": "Template eliminado"}
