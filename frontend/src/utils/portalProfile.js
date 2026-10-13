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
  valor === null ||
  valor === undefined ||
  (Array.isArray(valor) ? valor.length === 0 : String(valor).trim() === "");

/**
 * Grupos do pedido que existem sempre (como antes) e os que só viajam quando o
 * esquema tem campos para eles: o backend ignora o que não conhece, mas um
 * payload sem secções é o que o PUT de sempre enviava.
 */
const GRUPOS_BASE = ["contacto", "dados_pessoais"];
const GRUPOS_DAS_SECCOES = ["titular2_data", "real_estate_data", "financial_data"];

/** Cartões do perfil, pela ordem do registo (o backend envia o mesmo em `secoes`). */
export const SECCOES_POR_OMISSAO = [
  { id: "titular", titulo: "Dados Pessoais" },
  { id: "segundo_titular", titulo: "Segundo Titular" },
  { id: "imovel", titulo: "Imóvel Pretendido" },
  { id: "financeiro", titulo: "Situação Financeira" },
];

/**
 * Parte o esquema nos cartões do perfil.
 *
 * Só devolve cartões COM campos; um esquema sem `section` (resposta de um servidor
 * anterior) cai todo no cartão dos dados pessoais, como sempre foi.
 *
 * @returns {Array<{id: string, titulo: string, campos: Array}>}
 */
export function secoesDoPerfil(schema, secoes) {
  const campos = Array.isArray(schema) ? schema : [];
  const ordem =
    Array.isArray(secoes) && secoes.length > 0 ? secoes : SECCOES_POR_OMISSAO;
  // Uma lista parcial do servidor não pode esconder cartões que o esquema desenha: o que
  // falta acrescenta-se no fim, com o título de omissão.
  const conhecidas = new Set(ordem.map((s) => s.id));
  return ordem
    .map(({ id, titulo }) => ({
      id,
      titulo,
      campos: campos.filter((c) => (c?.section || "titular") === id),
    }))
    .concat(
      // Uma secção que o servidor desenhou e que a lista não tem não pode sumir.
      [...new Set(campos.map((c) => c?.section || "titular"))]
        .filter((id) => !conhecidas.has(id))
        .map((id) => ({
          id,
          titulo: SECCOES_POR_OMISSAO.find((s) => s.id === id)?.titulo || id,
          campos: campos.filter((c) => (c?.section || "titular") === id),
        })),
    )
    .filter((s) => s.campos.length > 0);
}

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
    // Só de leitura: o valor (NIF mascarado, listas resumidas) vem em `somente_leitura`
    // e nunca entra no estado editável — não há nada que o payload possa devolver.
    if (campo.read_only) continue;

    const origem = profile?.[grupo] || {};
    let valor = origem[nome];

    // A ficha guardou historicamente a data de nascimento com dois nomes
    // (`data_nascimento` e `birth_date`). Ler só um deixava o campo vazio
    // em fichas antigas — e o cliente preenchia-o de novo sem necessidade.
    if (vazio(valor) && nome === "data_nascimento") {
      valor = origem.birth_date;
    }

    if (campo.field_type === "checkbox") {
      // Caixa simples → booleano; grupo de opções → lista. Nunca "" (um texto
      // numa caixa marcava-a, e `[]` convertido em "" perdia o tipo).
      valores[campo.field_key] = Array.isArray(campo.options) && campo.options.length > 0
        ? (Array.isArray(valor) ? valor : [])
        : valor === true;
      continue;
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
 * Os campos só de leitura (NIF, listas de bancos…) NUNCA viajam: o que se vê só para ler
 * não se devolve, e o servidor recusava-os de qualquer modo.
 *
 * Uma caixa desmarcada (`false`) é um valor, não um campo vazio.
 *
 * ``base`` (os valores com que o formulário foi hidratado) faz as SECÇÕES (2.º titular,
 * imóvel, finanças) enviarem só o que MUDOU: estas escritas espelham-se no processo, onde a
 * equipa pode ter corrigido um valor entretanto — reenviar o que o cliente não tocou
 * repunha o valor antigo por cima da correcção. Os dados pessoais e contactos vivem só na
 * ficha do cliente e continuam a ir inteiros, como sempre.
 *
 * @returns {{contacto: Object, dados_pessoais: Object, titular2_data?: Object,
 *   real_estate_data?: Object, financial_data?: Object}}
 */
export function construirPayload(schema, valores, base) {
  const payload = { contacto: {}, dados_pessoais: {} };

  for (const campo of Array.isArray(schema) ? schema : []) {
    const [grupo, nome] = campo?.destino || [];
    if (!grupo || !nome || campo.read_only) continue;
    if (!GRUPOS_BASE.includes(grupo) && !GRUPOS_DAS_SECCOES.includes(grupo)) continue;
    const valor = valores?.[campo.field_key];
    if (
      base &&
      GRUPOS_DAS_SECCOES.includes(grupo) &&
      JSON.stringify(valor ?? null) === JSON.stringify(base[campo.field_key] ?? null)
    ) {
      continue;
    }
    if (!(grupo in payload)) payload[grupo] = {};
    payload[grupo][nome] = valor === false ? false : vazio(valor) ? null : valor;
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
    .filter(
      (campo) =>
        campo?.is_required &&
        !campo.read_only &&
        campo.field_type !== "checkbox" &&
        vazio(valores?.[campo.field_key]),
    )
    .map((campo) => ({ field_key: campo.field_key, label: campo.label }));
}
