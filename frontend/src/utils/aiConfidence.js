/**
 * Confiança da IA por campo — e o valor conta (Lote 3, ponto 2).
 *
 * O DEFEITO
 * `getConfidenceIndicator` do `ProcessDetails` decidia assim:
 *
 *     const conf = aiFieldConfidence?.[fieldName];
 *     if (conf === undefined || conf === null || !aiExtractedData) return null;
 *
 * Olhava para o NÚMERO e nunca para o VALOR. O campo NIF tem
 * `placeholder="9 dígitos"`, logo um NIF vazio desenha esse texto cinzento
 * no input — e ao lado dele o badge anunciava **«IA 100%»**.
 *
 * Quem lê aquilo conclui que o NIF foi extraído e verificado pela IA. É
 * **o badge que faz o placeholder parecer um dado**: sem ele, um campo
 * vazio lê-se como um campo vazio. Dar confiança máxima a uma extracção
 * nula é pior do que não mostrar confiança nenhuma, porque desliga a
 * desconfiança exactamente no campo que mais precisa dela.
 *
 * AS TRÊS RECUSAS
 *   1. **Valor vazio** (`""`, `null`, `undefined`, só espaços) — não há
 *      extracção nenhuma a que atribuir confiança.
 *   2. **Valor igual ao placeholder** — a IA que lê um FORMULÁRIO EM
 *      BRANCO devolve o texto de ajuda («9 dígitos», «11 dígitos») como
 *      se fosse o valor. É um modo de falha real da extracção por visão,
 *      e é indistinguível de um acerto se ninguém comparar.
 *   3. **Valor que falha a validação do próprio campo** — um NIF tem 9
 *      dígitos; o que não tiver não é um NIF, e dizer "100%" sobre ele é
 *      uma afirmação que o próprio formulário já sabe que é falsa (o
 *      `validateNIF` corre ali ao lado, no `onChange`).
 *
 * O que fica: quando o valor existe e é plausível, a confiança aparece
 * como sempre. **Isto não esconde a IA — impede-a de mentir.**
 */

/** Texto que é, na prática, "nada". */
function estaVazio(valor) {
  if (valor === null || valor === undefined) return true;
  if (typeof valor === "number") return false;
  return String(valor).trim() === "";
}

/**
 * Normaliza para comparar com o placeholder sem tropeçar em acentos,
 * maiúsculas ou espaços — «9 Dígitos» e «9 digitos » são o mesmo texto.
 */
function normalizar(texto) {
  return String(texto ?? "")
    .trim()
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "");
}

/**
 * O valor é (ou contém) o texto do placeholder?
 *
 * A comparação é por igualdade normalizada e não por `includes` nos dois
 * sentidos: um `includes` largo recusaria um valor legítimo que por azar
 * contivesse a palavra do placeholder.
 */
export function pareceOPlaceholder(valor, placeholder) {
  if (estaVazio(valor) || estaVazio(placeholder)) return false;
  return normalizar(valor) === normalizar(placeholder);
}

/**
 * Patamares de confiança. São os mesmos de sempre — o que mudou foi
 * QUANDO se mostram, não as cores.
 */
export const PATAMARES = [
  {
    minimo: 0.8,
    nivel: "high",
    badge: "bg-green-100 text-green-700 border-green-300",
    borderClass: "border-l-4 border-l-green-400",
  },
  {
    minimo: 0.6,
    nivel: "medium",
    badge: "bg-amber-100 text-amber-700 border-amber-300",
    borderClass: "border-l-4 border-l-amber-400",
  },
  {
    minimo: 0,
    nivel: "low",
    badge: "bg-red-100 text-red-700 border-red-300",
    borderClass: "border-l-4 border-l-red-400",
  },
];

/**
 * O indicador de confiança de um campo, ou `null` quando não há nada
 * honesto a dizer.
 *
 * @param {Object} entrada
 * @param {any}      entrada.valor        — o valor que ESTÁ no campo.
 * @param {number}   [entrada.confianca]  — 0..1 reportada pela IA.
 * @param {boolean}  [entrada.houveExtraccao=true] — a IA correu mesmo?
 * @param {string}   [entrada.placeholder] — o texto de ajuda do input.
 * @param {Function} [entrada.validar]    — `(valor) => boolean`, a mesma
 *   validação que o formulário já usa. Quando devolve `false`, não há
 *   indicador: o campo já sabe que o valor não serve.
 * @returns {{badge:string, label:string, borderClass:string, nivel:string}|null}
 */
export function indicadorDeConfianca({
  valor,
  confianca,
  houveExtraccao = true,
  placeholder,
  validar,
} = {}) {
  if (!houveExtraccao) return null;
  if (confianca === undefined || confianca === null) return null;
  if (typeof confianca !== "number" || Number.isNaN(confianca)) return null;

  // 1) Sem valor não há extracção a que atribuir confiança.
  if (estaVazio(valor)) return null;

  // 2) O texto de ajuda não é um dado.
  if (pareceOPlaceholder(valor, placeholder)) return null;

  // 3) Um valor que o próprio formulário recusa não merece um selo.
  if (typeof validar === "function") {
    let valido = false;
    try {
      valido = Boolean(validar(valor));
    } catch {
      // Um validador que rebenta não pode calar o indicador por acidente,
      // mas também não o pode abençoar: trata-se como "não sei" e mostra-se
      // — a alternativa era esconder confiança legítima por um erro nosso.
      valido = true;
    }
    if (!valido) return null;
  }

  const patamar = PATAMARES.find((p) => confianca >= p.minimo) || PATAMARES[PATAMARES.length - 1];
  return {
    badge: patamar.badge,
    borderClass: patamar.borderClass,
    nivel: patamar.nivel,
    label: `${Math.round(confianca * 100)}%`,
  };
}

/**
 * Placeholders por campo, num só sítio.
 *
 * Escrito ao lado do `placeholder=` de cada input divergiria dele na
 * primeira vez que alguém mudasse o texto de ajuda — e a divergência é
 * silenciosa: o indicador voltava a aprovar o placeholder.
 */
export const PLACEHOLDERS_POR_CAMPO = {
  nif: "9 dígitos",
  niss: "11 dígitos",
};

/**
 * Validadores por campo. Só os que o formulário já tem — inventar
 * validação nova aqui era mudar as regras de negócio por uma porta
 * lateral.
 */
export function validadoresPadrao({ validateNIF } = {}) {
  const out = {};
  if (typeof validateNIF === "function") {
    out.nif = (v) => {
      const r = validateNIF(v);
      // `validateNIF` devolve `{valid, error}`; um `error` preenchido é
      // recusa. Aceita-se também um booleano, para não ficar preso à forma.
      if (typeof r === "boolean") return r;
      if (r && typeof r === "object") return !r.error;
      return true;
    };
  }
  return out;
}
