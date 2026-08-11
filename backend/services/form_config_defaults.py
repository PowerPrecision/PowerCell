"""Default form field/step configuration constants.

Extraído de `routes/form_config.py`.
"""
from __future__ import annotations

# Configuração padrão de visibilidade condicional de passos
# Estrutura: { "step_number": { "depends_on": { "field": X, "value": V } } }
# Quando o depends_on não for satisfeito, o passo inteiro é escondido no formulário público.
DEFAULT_STEP_CONFIG = {
    "2": {
        "depends_on": {"field": "compra_tipo", "value": "outra_pessoa"},
        "label": "Passo visível apenas quando Tipo de compra = outra_pessoa"
    }
}


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
     "options": [{"value": "solteiro", "label": "Solteiro(a)"}, {"value": "casado", "label": "Casado(a)"}, {"value": "casado_adquiridos", "label": "Casado(a) - Comunhão de Adquiridos"}, {"value": "casado_geral", "label": "Casado(a) - Comunhão Geral de Bens"}, {"value": "casado_separacao", "label": "Casado(a) - Separação de Bens"}, {"value": "divorciado", "label": "Divorciado(a)"}, {"value": "viuvo", "label": "Viúvo(a)"}, {"value": "uniao_facto", "label": "União de Facto"}]},
    {"field_key": "menor_35_anos", "label": "Menor de 35 anos", "step": 1, "is_visible": True, "is_required": False, "field_type": "checkbox", "order": 12, "is_custom": False, "data_path": "personal_data"},
    {"field_key": "compra_tipo", "label": "Tipo de compra", "step": 1, "is_visible": True, "is_required": False, "field_type": "select", "order": 13, "is_custom": False, "data_path": "personal_data",
     "options": ["individual", "outra_pessoa"]},
    {"field_key": "sexo", "label": "Sexo", "step": 1, "is_visible": True, "is_required": False, "field_type": "radio", "order": 14, "is_custom": False, "data_path": "personal_data",
     "options": [{"value": "M", "label": "Masculino"}, {"value": "F", "label": "Feminino"}, {"value": "O", "label": "Outro"}]},
    {"field_key": "codigo_postal", "label": "Código Postal", "step": 1, "is_visible": True, "is_required": False, "field_type": "text", "order": 15, "is_custom": False, "data_path": "personal_data"},
    {"field_key": "profissao", "label": "Profissão", "step": 1, "is_visible": True, "is_required": False, "field_type": "text", "order": 16, "is_custom": False, "data_path": "personal_data"},
    {"field_key": "altura", "label": "Altura (m)", "step": 1, "is_visible": False, "is_required": False, "field_type": "number", "order": 17, "is_custom": False, "data_path": "personal_data"},

    {"field_key": "niss", "label": "Nº Segurança Social (NISS)", "step": 1, "is_visible": True, "is_required": False, "field_type": "text", "order": 3, "is_custom": False, "data_path": "personal_data",
     "hint": "Número de Identificação na Segurança Social (11 dígitos)"},

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
    {"field_key": "titular2_estado_civil", "label": "Estado Civil (2º Titular)", "step": 2, "is_visible": True, "is_required": False, "field_type": "select", "order": 10, "is_custom": False, "data_path": "titular2_data", "depends_on": {"field": "compra_tipo", "value": "outra_pessoa"},
     "options": [{"value": "solteiro", "label": "Solteiro(a)"}, {"value": "casado", "label": "Casado(a)"}, {"value": "casado_adquiridos", "label": "Casado(a) - Comunhão de Adquiridos"}, {"value": "casado_geral", "label": "Casado(a) - Comunhão Geral de Bens"}, {"value": "casado_separacao", "label": "Casado(a) - Separação de Bens"}, {"value": "divorciado", "label": "Divorciado(a)"}, {"value": "viuvo", "label": "Viúvo(a)"}, {"value": "uniao_facto", "label": "União de Facto"}]},

    # ── Step 3 — Dados do Imóvel ──────────────────────────────────────
    {"field_key": "finalidade", "label": "Finalidade do pedido", "step": 3, "is_visible": True, "is_required": True, "field_type": "select", "order": 1, "is_custom": False, "data_path": "real_estate_data",
     "options": ["compra_imovel", "refinanciamento"]},
    {"field_key": "tipo_imovel", "label": "Tipo de imóvel", "step": 3, "is_visible": True, "is_required": False, "field_type": "select", "order": 2, "is_custom": False, "data_path": "real_estate_data",
     "options": [{"value": "apartamento", "label": "Apartamento"}, {"value": "moradia", "label": "Moradia"}, {"value": "terreno", "label": "Terreno"}, {"value": "outro", "label": "Outro"}],
     "depends_on": {"field": "finalidade", "not_value": "refinanciamento"},
     "depends_on_all": [{"field": "finalidade", "not_value": "refinanciamento"}, {"field": "ja_tem_casa_escolhida", "not_value": True}],
     "hint": "Obrigatório se ainda não tem casa escolhida"},
    {"field_key": "num_quartos", "label": "Nº quartos", "step": 3, "is_visible": True, "is_required": False, "field_type": "select", "order": 3, "is_custom": False, "data_path": "real_estate_data",
     "options": ["T0", "T1", "T2", "T3", "T4", "T5+"],
     "depends_on": {"field": "finalidade", "not_value": "refinanciamento"},
     "depends_on_all": [{"field": "finalidade", "not_value": "refinanciamento"}, {"field": "ja_tem_casa_escolhida", "not_value": True}],
     "hint": "Obrigatório se ainda não tem casa escolhida"},
    {"field_key": "localizacao", "label": "Localização/Zona preferida", "step": 3, "is_visible": True, "is_required": False, "field_type": "text", "order": 4, "is_custom": False, "data_path": "real_estate_data",
     "depends_on": {"field": "finalidade", "not_value": "refinanciamento"},
     "depends_on_all": [{"field": "finalidade", "not_value": "refinanciamento"}, {"field": "ja_tem_casa_escolhida", "not_value": True}],
     "hint": "Obrigatório se ainda não tem casa escolhida"},
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
    {"field_key": "chave_movel_digital", "label": "Chave Móvel Digital", "step": 4, "is_visible": True, "is_required": True, "field_type": "select", "order": 3, "is_custom": False, "data_path": "financial_data", "options": ["Sim", "Não"]},
    {"field_key": "renda_habitacao_atual", "label": "Renda de habitação atual", "step": 4, "is_visible": True, "is_required": False, "field_type": "number", "order": 4, "is_custom": False, "data_path": "financial_data"},
    {"field_key": "precisa_vender_casa", "label": "Precisa de vender casa?", "step": 4, "is_visible": True, "is_required": False, "field_type": "select", "order": 5, "is_custom": False, "data_path": "financial_data", "options": ["Sim", "Não"]},
    {"field_key": "efetivo", "label": "Efetivo?", "step": 4, "is_visible": True, "is_required": False, "field_type": "select", "order": 6, "is_custom": False, "data_path": "financial_data", "options": ["Sim", "Não"]},
    {"field_key": "trabalha_estrangeiro", "label": "Trabalha no estrangeiro?", "step": 4, "is_visible": True, "is_required": False, "field_type": "select", "order": 7, "is_custom": False, "data_path": "financial_data", "options": ["Sim", "Não"]},
    {"field_key": "employment_type", "label": "Tipo de Contrato de Trabalho", "step": 4, "is_visible": True, "is_required": True, "field_type": "select", "order": 8, "is_custom": False, "data_path": "financial_data",
     "options": [{"value": "efetivo", "label": "Efetivo"}, {"value": "termo_certo", "label": "Termo Certo"}, {"value": "termo_incerto", "label": "Termo Incerto"}, {"value": "independente", "label": "Independente"}, {"value": "empresario", "label": "Empresário"}, {"value": "reformado", "label": "Reformado"}, {"value": "desempregado", "label": "Desempregado"}]},
    {"field_key": "employment_duration", "label": "Antiguidade no emprego", "step": 4, "is_visible": True, "is_required": False, "field_type": "text", "order": 9, "is_custom": False, "data_path": "financial_data"},
    {"field_key": "employer_name", "label": "Nome da empresa", "step": 4, "is_visible": True, "is_required": False, "field_type": "text", "order": 10, "is_custom": False, "data_path": "financial_data"},
    {"field_key": "employer_nif", "label": "NIF da empresa", "step": 4, "is_visible": True, "is_required": False, "field_type": "text", "order": 11, "is_custom": False, "data_path": "financial_data"},
    {"field_key": "fiador", "label": "Fiador?", "step": 4, "is_visible": True, "is_required": False, "field_type": "select", "order": 12, "is_custom": False, "data_path": "financial_data", "options": ["Sim", "Não"]},
    {"field_key": "salario_liquido", "label": "Salário mensal líquido", "step": 4, "is_visible": True, "is_required": True, "field_type": "number", "order": 13, "is_custom": False, "data_path": "financial_data"},

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
