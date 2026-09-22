/**
 * Perfil do Portal: do esquema ao formulário e de volta (Lote 3, ponto 7).
 *
 * PURO E TESTÁVEL de propósito. O `ClientPortal.jsx` tem 2963 linhas; a
 * hidratação do formulário e a construção do payload são as duas peças
 * onde um erro faz o cliente perder dados sem se aperceber, e dentro
 * daquele ficheiro não se conseguiam testar.
 *
 * O esquema vem do backend (`form_schema`), derivado do mesmo
 * `form_config` que alimenta o formulário interno do CRM. Cada entrada
 * traz o `destino` — `["contacto" | "dados_pessoais", nome_na_ficha]` —
 * que é o que permite montar o payload sem uma segunda lista escrita à
 * mão.
 */

/** Um valor que o utilizador não preencheu. */
const vazio = (valor) =>
  valor === null || valor === undefined || String(valor).trim() === "";

/**
 * Valores iniciais do formulário, a partir da ficha do cliente.
 *
 * @param {Array} schema - `form_schema` do backend.
 * @param {Object} profile - Resposta de `GET /portal/me`.
 * @returns {Object} valores indexados por `field_key`.
 */
export function hidratarFormulario(schema, profile) {
  const valores = {};
  for (const campo of Array.isArray(schema) ? schema : []) {
    const [grupo, nome] = campo?.destino || [];
    if (!grupo || !nome) continue;

    const origem = profile?.[grupo] || {};
    let valor = origem[nome];

    // A ficha guardou historicamente a data de nascimento com dois nomes
    // (`data_nascimento` e `birth_date`). Ler só um deixava o campo vazio
    // em fichas antigas — e o cliente preenchia-o de novo sem necessidade.
    if (vazio(valor) && nome === "data_nascimento") {
      valor = origem.birth_date;
    }

    valores[campo.field_key] = vazio(valor) ? "" : valor;
  }
  return valores;
}

/**
 * Payload de `PUT /portal/me`, agrupado como o backend o espera.
 *
 * Só inclui campos que estão no esquema: é isso que garante que o que se
 * envia é exactamente o que se mostrou. Um campo em branco vai como
 * `null` (apagar é uma intenção legítima), e não é omitido.
 *
 * @param {Array} schema
 * @param {Object} valores - Estado do formulário, por `field_key`.
 * @returns {{contacto: Object, dados_pessoais: Object}}
 */
export function construirPayload(schema, valores) {
  const payload = { contacto: {}, dados_pessoais: {} };

  for (const campo of Array.isArray(schema) ? schema : []) {
    const [grupo, nome] = campo?.destino || [];
    if (!grupo || !nome || !(grupo in payload)) continue;

    const valor = valores?.[campo.field_key];
    payload[grupo][nome] = vazio(valor) ? null : valor;
  }

  return payload;
}

/**
 * Campos obrigatórios do esquema que continuam por preencher.
 *
 * @returns {Array<{field_key: string, label: string}>}
 */
export function obrigatoriosEmFalta(schema, valores) {
  return (Array.isArray(schema) ? schema : [])
    .filter((campo) => campo?.is_required && vazio(valores?.[campo.field_key]))
    .map((campo) => ({ field_key: campo.field_key, label: campo.label }));
}
