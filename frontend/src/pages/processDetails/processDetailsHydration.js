/**
 * Hidratação do estado editável de ProcessDetails a partir do payload API.
 * Extraído de ProcessDetails.js — comportamento idêntico (FASE 3 + UNIFICAÇÃO).
 */

const ESTADO_CIVIL_MAP = {
  "Solteiro(a)": "solteiro", Solteiro: "solteiro",
  "Casado(a)": "casado", Casado: "casado",
  "Casado(a) - Comunhão de Bens": "casado_geral",
  "Casado(a) - Comunhão de Aquiridos": "casado_adquiridos",
  "Casado(a) - Comunhão de Adquiridos": "casado_adquiridos",
  "Casado(a) - Separação de Bens": "casado_separacao",
  "Divorciado(a)": "divorciado", Divorciado: "divorciado",
  "Viúvo(a)": "viuvo", "Viúvo": "viuvo",
  "União de Facto": "uniao_facto",
};

const TIPO_IMOVEL_MAP = {
  Apartamento: "apartamento", Moradia: "moradia",
  Terreno: "terreno", Outro: "outro",
};

const EMPLOYMENT_TYPE_MAP = {
  Efetivo: "efetivo", "Termo Certo": "termo_certo",
  "Termo Incerto": "termo_incerto", Independente: "independente",
  Empresário: "empresario", "Empresário em Nome Individual": "empresario",
  Reformado: "reformado", Desempregado: "desempregado",
};

function stripBlindIndexes(obj) {
  const clean = { ...(obj || {}) };
  delete clean.nif_hash;
  delete clean.email_hash;
  delete clean.telefone_hash;
  return clean;
}

/**
 * Constrói personalData a partir do cliente (fonte de verdade) ou fallback do processo.
 */
export function buildPersonalData(processData, clientData) {
  if (clientData) {
    const clientPersonal = stripBlindIndexes(clientData.dados_pessoais || {});
    clientPersonal.nome_completo = clientData.nome || processData.client_name || "";
    const resolvedEmail = clientData.contacto?.email || processData.client_email || "";
    const resolvedPhone = clientData.contacto?.telefone || processData.client_phone || "";
    clientPersonal.email = resolvedEmail;
    clientPersonal.telefone = resolvedPhone;
    if (clientData.dados_pessoais?.nif) {
      clientPersonal.nif = clientData.dados_pessoais.nif;
    }
    return { personalData: clientPersonal, resolvedEmail, resolvedPhone };
  }

  return {
    personalData: stripBlindIndexes(processData.personal_data || {}),
    resolvedEmail: "",
    resolvedPhone: "",
  };
}

/**
 * Aplica normalizações backward-compat (UNIFICAÇÃO) sobre slices do formulário.
 */
export function normalizeFormSlices(processData, personalData, financialData, realEstateData, titular2Data) {
  let personal = { ...personalData };
  let financial = { ...financialData };
  let realEstate = { ...realEstateData };
  let titular2 = { ...titular2Data };
  let processPatch = {};

  const pd = processData.personal_data || {};
  const fd = processData.financial_data || {};
  const rd = processData.real_estate_data || {};
  const t2 = processData.titular2_data || {};

  if ((pd.morada || pd.address) && !pd.morada_fiscal) {
    personal = { ...personal, morada_fiscal: personal.morada || personal.address || "" };
  }
  if ((fd.rendimento_mensal || fd.salario_liquido) && !fd.monthly_income) {
    financial = {
      ...financial,
      monthly_income: financial.rendimento_mensal || financial.salario_liquido,
    };
  }
  if ((fd.empresa || fd.entidade_patronal) && !fd.employer_name) {
    financial = {
      ...financial,
      employer_name: financial.empresa || financial.entidade_patronal,
    };
  }
  if (fd.tipo_contrato && !fd.employment_type) {
    financial = { ...financial, employment_type: financial.tipo_contrato };
  }
  if (fd.antiguidade_emprego && !fd.employment_duration) {
    financial = { ...financial, employment_duration: financial.antiguidade_emprego };
  }
  if (personal.sexo === "Masculino") {
    personal = { ...personal, sexo: "M" };
  } else if (personal.sexo === "Feminino") {
    personal = { ...personal, sexo: "F" };
  }
  if (personal.estado_civil && ESTADO_CIVIL_MAP[personal.estado_civil]) {
    personal = { ...personal, estado_civil: ESTADO_CIVIL_MAP[personal.estado_civil] };
  }
  if (realEstate.tipo_imovel && TIPO_IMOVEL_MAP[realEstate.tipo_imovel]) {
    realEstate = { ...realEstate, tipo_imovel: TIPO_IMOVEL_MAP[realEstate.tipo_imovel] };
  }
  if (financial.employment_type && EMPLOYMENT_TYPE_MAP[financial.employment_type]) {
    financial = {
      ...financial,
      employment_type: EMPLOYMENT_TYPE_MAP[financial.employment_type],
    };
  }
  if (titular2.estado_civil && ESTADO_CIVIL_MAP[titular2.estado_civil]) {
    titular2 = { ...titular2, estado_civil: ESTADO_CIVIL_MAP[titular2.estado_civil] };
  }
  if (pd.email && !processData.client_email) {
    processPatch.client_email = pd.email;
  }
  if ((pd.phone || pd.telefone) && !processData.client_phone) {
    processPatch.client_phone = pd.phone || pd.telefone;
  }

  // unused in maps but kept for parity with original t2/rd reads
  void t2;
  void rd;

  return { personalData: personal, financialData: financial, realEstateData: realEstate, titular2Data: titular2, processPatch };
}

/**
 * View-model completo para o estado editável de ProcessDetails.
 *
 * @param {object} processData - GET /processes/{id}
 * @param {object|null} clientData - GET /clients/{id} ou null
 */
export function deriveProcessDetailsViewModel(processData, clientData) {
  const { personalData: rawPersonal, resolvedEmail, resolvedPhone } = buildPersonalData(
    processData,
    clientData,
  );

  let process = { ...processData };
  if (clientData && (resolvedEmail || resolvedPhone)) {
    process = {
      ...process,
      client_email: process.client_email || resolvedEmail || "",
      client_phone: process.client_phone || resolvedPhone || "",
    };
  }

  const titular2Raw = stripBlindIndexes(processData.titular2_data || {});
  // stripBlindIndexes already removed nif_hash; original also deleted only nif_hash on titular2
  delete titular2Raw.nif_hash;

  const normalized = normalizeFormSlices(
    processData,
    rawPersonal,
    processData.financial_data || {},
    processData.real_estate_data || {},
    titular2Raw,
  );

  process = { ...process, ...normalized.processPatch };

  return {
    process,
    clientId: processData.client_id || null,
    clientData: clientData || null,
    personalData: normalized.personalData,
    titular2Data: normalized.titular2Data,
    financialData: normalized.financialData,
    realEstateData: normalized.realEstateData,
    creditData: processData.credit_data || {},
    status: processData.status || "",
    aiSummary: processData.ai_executive_summary || null,
    aiAnalysisDate: processData.ai_analysis_date || null,
    aiSuggestions: processData.ai_suggestions || [],
    isDataConfirmed: processData.is_data_confirmed || false,
  };
}
