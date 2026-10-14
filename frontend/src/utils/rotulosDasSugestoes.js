/**
 * Nomes legíveis dos campos que a IA pode sugerir (Lote 4, ponto 4).
 *
 * As chaves são as de `AI_SUGGESTION_FIELD_MAP` (backend) — os nomes com que a
 * sugestão chega ao ecrã. Um campo que não esteja aqui NÃO desaparece nem
 * aparece com a chave crua colada: cai num recurso legível (`humanizar`), que
 * é um aviso de que o mapa ficou para trás, não um erro.
 */
export const ROTULOS_DAS_SUGESTOES = {
  client_name: "Nome do cliente",
  nif: "NIF",
  documento_id: "Nº do documento de identificação",
  cc_number: "Nº do documento de identificação",
  birth_date: "Data de nascimento",
  cc_validity: "Validade do documento",
  data_validade_cc: "Validade do documento",
  nationality: "Nacionalidade",
  naturalidade: "Naturalidade",
  gender: "Sexo",
  address: "Morada fiscal",
  fiscal_address: "Morada fiscal",
  estado_civil: "Estado civil",
  monthly_income: "Rendimento mensal líquido",
  rendimento_mensal: "Rendimento mensal líquido",
  salario_liquido: "Rendimento mensal líquido",
  rendimento_bruto: "Rendimento bruto",
  salario_bruto: "Rendimento bruto",
  employer_name: "Entidade empregadora",
  empresa: "Entidade empregadora",
  entidade_empregadora: "Entidade empregadora",
  tipo_contrato: "Tipo de contrato",
  employment_type: "Tipo de contrato",
  categoria_profissional: "Categoria profissional",
  subsidiario_alimentacao: "Subsídio de alimentação",
  data_referencia: "Data de referência",
  valor_imovel: "Valor do imóvel",
  localizacao: "Localização do imóvel",
  tipologia: "Tipologia",
  area: "Área bruta",
  artigo_matricial: "Artigo matricial",
  valor_patrimonial_tributario: "Valor patrimonial tributário",
  area_bruta: "Área bruta",
};

function humanizar(chave) {
  const texto = String(chave || "").replace(/_/g, " ").trim();
  return texto ? texto.charAt(0).toUpperCase() + texto.slice(1) : "";
}

export function rotuloDaSugestao(campo) {
  return ROTULOS_DAS_SUGESTOES[campo] || humanizar(campo);
}

/** O que se escreve numa célula: nunca uma célula em branco (não se distingue de um erro). */
export function textoDoValor(valor) {
  if (valor === null || valor === undefined || valor === "") return "—";
  if (typeof valor === "boolean") return valor ? "Sim" : "Não";
  if (Array.isArray(valor)) return valor.length ? valor.join(", ") : "—";
  if (typeof valor === "object") return JSON.stringify(valor);
  return String(valor);
}
