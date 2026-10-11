/**
 * Formulário público POR EMPRESA — regras puras do link de registo.
 *
 * O registo público deixou de ser genérico: cada empresa tem o seu formulário e o
 * link de registo leva o identificador dela (`/registo?empresa=<company_id>`).
 * O servidor carrega ESTRITAMENTE o formulário da rede dessa empresa e recusa (404)
 * um identificador desconhecido — nunca cai no formulário de outra.
 *
 * Um ponto único: o ecrã de administração que MONTA o link e o formulário público
 * que o LÊ usam estas duas funções, para o nome do parâmetro não divergir.
 */

/** Nome do parâmetro de URL que identifica a empresa. */
export const PARAMETRO_DA_EMPRESA = "empresa";

/**
 * O link de registo público de uma empresa.
 * @param {string} origem - `window.location.origin`.
 * @param {string} empresaId - `company_id` (nunca o nome: dois homónimos não se distinguem).
 * @returns {string} `""` quando falta um dos dois (sem destino não se desenha o link).
 */
export function linkDeRegistoDaEmpresa(origem, empresaId) {
  const base = typeof origem === "string" ? origem.trim().replace(/\/+$/, "") : "";
  const id = typeof empresaId === "string" ? empresaId.trim() : "";
  if (!base || !id) return "";
  return `${base}/registo?${PARAMETRO_DA_EMPRESA}=${encodeURIComponent(id)}`;
}

/**
 * O identificador da empresa que vem no URL do formulário público.
 * @param {string|URLSearchParams} pesquisa - `location.search` ou os parâmetros já lidos.
 * @returns {string} `""` quando não há (link antigo, sem empresa).
 */
export function empresaDoLink(pesquisa) {
  const params = pesquisa instanceof URLSearchParams ? pesquisa : new URLSearchParams(pesquisa || "");
  return (params.get(PARAMETRO_DA_EMPRESA) || "").trim();
}
