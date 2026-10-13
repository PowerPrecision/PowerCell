/**
 * Helpers de limpeza/formatação de formulários antes de submeter o processo.
 * Extraídos de ProcessDetails.js.
 *
 * APAGAR UM CAMPO: estes helpers descartavam os vazios, e o servidor nunca
 * recebia o pedido de limpeza (o valor antigo voltava no refetch). Os que
 * recebem `{ base }` — o que foi carregado do servidor — enviam o vazio
 * EXPLÍCITO para os campos que tinham valor e o utilizador apagou; um campo que
 * já nasceu vazio continua omitido. Ver `utils/camposLimpos.js`.
 */
import {
  ALIASES_FINANCEIROS,
  ALIASES_PESSOAIS,
  FORA_DA_LIMPEZA_PESSOAL,
  camposLimpos,
  limparAliasesDosCampos,
} from "../../utils/camposLimpos";

/** Converte data em formato português para ISO (yyyy-MM-dd). */
export const convertPortugueseDateToISO = (dateStr) => {
  if (!dateStr) return dateStr;

  // Se já está em formato ISO (yyyy-MM-dd), retornar como está
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
    return dateStr;
  }

  const monthsMap = {
    janeiro: "01", fevereiro: "02", março: "03", abril: "04",
    maio: "05", junho: "06", julho: "07", agosto: "08",
    setembro: "09", outubro: "10", novembro: "11", dezembro: "12",
  };

  // Tentar parsear formato "DD de MMMM de YYYY"
  const match = dateStr.toLowerCase().match(/(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})/);
  if (match) {
    const day = match[1].padStart(2, "0");
    const month = monthsMap[match[2]];
    const year = match[3];
    if (month) {
      return `${year}-${month}-${day}`;
    }
  }

  // Tentar parsear formato "DD/MM/YYYY"
  const shortMatch = dateStr.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (shortMatch) {
    const day = shortMatch[1].padStart(2, "0");
    const month = shortMatch[2].padStart(2, "0");
    const year = shortMatch[3];
    return `${year}-${month}-${day}`;
  }

  // Se não conseguir parsear, retornar null para evitar erros
  return null;
};

/** Formata data para input type="date" (sempre retorna yyyy-MM-dd ou vazio). */
export const formatDateForInput = (dateStr) => {
  if (!dateStr) return "";
  const iso = convertPortugueseDateToISO(dateStr);
  return iso || "";
};

/**
 * Limpa dados pessoais antes de enviar.
 *
 * Com `base`, os campos que tinham valor e foram apagados vão como `""` (e
 * levam os nomes alternativos do mesmo dado). Sem `base` descartam-se os vazios,
 * como sempre.
 */
export const cleanPersonalDataForSubmit = (data, { base } = {}) => {
  const cleaned = { ...data };

  // Uma data que não se consegue ler NÃO é um pedido para apagar: omite-se.
  // (Antes ia `null`, que no servidor sobrepunha o valor guardado.)
  if (cleaned.data_nascimento) {
    cleaned.data_nascimento = convertPortugueseDateToISO(cleaned.data_nascimento) || undefined;
  }
  if (cleaned.data_validade_cc) {
    cleaned.data_validade_cc = convertPortugueseDateToISO(cleaned.data_validade_cc) || undefined;
  }

  delete cleaned.nif_hash;
  delete cleaned.email_hash;
  delete cleaned.telefone_hash;
  delete cleaned.marital_status; // phantom field, usar estado_civil

  const stringFields = ["nif", "niss", "documento_id", "altura", "codigo_postal", "phone"];
  for (const field of stringFields) {
    if (cleaned[field] !== undefined && cleaned[field] !== null && cleaned[field] !== "") {
      cleaned[field] = String(cleaned[field]);
    }
  }

  if (cleaned.menor_35_anos !== undefined && cleaned.menor_35_anos !== null) {
    cleaned.menor_35_anos = Boolean(cleaned.menor_35_anos);
  }

  if (cleaned.nif) {
    cleaned.nif = cleaned.nif.replace(/[^\d]/g, "");
    if (cleaned.nif.length !== 9) {
      delete cleaned.nif;
    }
  }

  Object.keys(cleaned).forEach((key) => {
    if (cleaned[key] === undefined || cleaned[key] === "") {
      delete cleaned[key];
    }
  });

  // Campos APAGADOS: vazio explícito. Calcula-se sobre `data` (antes da limpeza
  // acima): um NIF a meio de escrever (`"123"`) é descartado, não apagado.
  const limpos = camposLimpos(base, data, { ignorar: FORA_DA_LIMPEZA_PESSOAL });
  for (const campo of limpos) cleaned[campo] = "";
  limparAliasesDosCampos(cleaned, limpos, ALIASES_PESSOAIS, "", base);

  return cleaned;
};

/**
 * Limpa dados do 2º titular antes de enviar.
 *
 * Aqui os vazios descartam-se de propósito: o servidor SUBSTITUI a secção
 * `titular2_data` (ficha do cliente e cópia do processo), por isso um campo que
 * não vai no pedido deixa de existir. Um NIF que não tem 9 dígitos é omitido
 * pela mesma regra — quem chama valida-o ANTES (`handleSave`), senão uma gralha
 * apagava o NIF guardado.
 */
export const cleanTitular2DataForSubmit = (data) => {
  const cleaned = { ...data };
  if (cleaned.birth_date) {
    cleaned.birth_date = convertPortugueseDateToISO(cleaned.birth_date) || undefined;
  }
  delete cleaned.nif_hash;

  if (cleaned.nif) {
    cleaned.nif = String(cleaned.nif).replace(/[^\d]/g, "");
    if (cleaned.nif.length !== 9) {
      delete cleaned.nif;
    }
  }

  Object.keys(cleaned).forEach((key) => {
    if (cleaned[key] === undefined || cleaned[key] === "") {
      delete cleaned[key];
    }
  });
  return cleaned;
};

/** Limpa dados do imóvel antes de enviar. */
export const cleanRealEstateDataForSubmit = (data) => {
  const cleaned = { ...data };
  // Converter strings vazias → null (para permitir limpar campos no backend)
  Object.keys(cleaned).forEach((key) => {
    if (cleaned[key] === undefined) {
      delete cleaned[key];
    } else if (cleaned[key] === "") {
      cleaned[key] = null;
    }
  });
  return cleaned;
};

/** Limpa dados de crédito antes de enviar. */
export const cleanCreditDataForSubmit = (data) => {
  const cleaned = { ...data };
  if (cleaned.valuation_date) {
    cleaned.valuation_date = convertPortugueseDateToISO(cleaned.valuation_date);
  }
  if (cleaned.bank_approval_date) {
    cleaned.bank_approval_date = convertPortugueseDateToISO(cleaned.bank_approval_date);
  }
  Object.keys(cleaned).forEach((key) => {
    if (cleaned[key] === undefined) {
      delete cleaned[key];
    } else if (cleaned[key] === "") {
      cleaned[key] = null;
    }
  });
  return cleaned;
};

/**
 * Limpa dados financeiros para envio (apenas campos válidos do modelo).
 *
 * Um campo vazio vai como `null` (o servidor retira-o da secção). Com `base`, um
 * campo canónico apagado leva também os nomes alternativos que o servidor tinha
 * (`salario_liquido` para `monthly_income`…): sem isso a hidratação seguinte
 * promovia o alternativo e o valor «voltava».
 */
export const cleanFinancialDataForSubmit = (data, { base } = {}) => {
  const validFields = [
    "acesso_portal_financas", "chave_movel_digital", "renda_habitacao_atual",
    "precisa_vender_casa", "efetivo", "fiador", "bancos_creditos",
    "capital_proprio", "valor_financiado", "valor_pretendido", "valor_entrada",
    "data_sinal", "reforco_sinal", "comissao_mediacao",
    "portal_financas_utilizador", "portal_financas_senha",
    "seg_social_utilizador", "seg_social_senha",
    "monthly_income", "employment_type", "employment_duration", "employer_name",
    "employer_nif", "trabalha_estrangeiro", "bancos_simulacoes", "tempo_restante_credito",
    "rendimento_mensal", "rendimento_bruto", "salario_liquido", "salario_bruto",
    "empresa", "tipo_contrato", "categoria_profissional", "subsidiario_alimentacao",
    "data_referencia",
    "nr_dependentes", "number_of_dependents", "rendimento_co_titular",
    "creditos_existentes", "prestacao_creditos_mensal",
    "rendimento_agregado",
    "rendimento_anual",
    "antiguidade_emprego",
    "outros_rendimentos", "despesas_mensais",
    "tem_creditos_activos",
  ];

  const cleaned = {};
  for (const key of validFields) {
    if (data[key] !== undefined) {
      if (data[key] === null || data[key] === "") {
        cleaned[key] = null;
      } else {
        cleaned[key] = data[key];
      }
    }
  }

  const limpos = camposLimpos(base, data).filter((c) => validFields.includes(c));
  for (const campo of limpos) cleaned[campo] = null;
  limparAliasesDosCampos(cleaned, limpos, ALIASES_FINANCEIROS, null, base);
  return cleaned;
};
