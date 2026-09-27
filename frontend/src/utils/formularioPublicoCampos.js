/**
 * Ponto 9 — Portal/Formulário público stress-free (regras puras).
 *
 * O PROBLEMA: o formulário público mostrava os 64 campos de cada passo
 * ao mesmo nível, com asteriscos vermelhos e "(obrigatório)" a martelar,
 * e uma barra de progresso que contava como obrigatórios campos que não
 * bloqueiam nada. Um cliente que compra com outra pessoa via a barra
 * exigir 10 campos do 2º titular que, no `form_config`, são todos
 * opcionais. O medo de falhar a submissão era, em boa parte, o produto a
 * mentir-lhe.
 *
 * A REGRA, uma fonte de verdade só: **primário = obrigatório no
 * `form_config`**. É o painel que o administrador já controla, e é o
 * mesmo campo (`is_required`) que o `validateStep` usa para bloquear.
 * Tudo o resto é secundário: entra num painel expansível, fechado por
 * omissão, sem asterisco — porque `RequiredLabel` só desenha o asterisco
 * quando o campo é mesmo obrigatório.
 *
 * Antes disto havia TRÊS listas de "obrigatório" a divergir: o config
 * (que bloqueia), uma lista fixa por passo (que alimentava a barra) e a
 * união das duas. Uma só.
 */

/**
 * Parte os campos de um passo em primários e secundários.
 *
 * @param {Array<{field_key: string, is_required?: boolean}>} campos
 * @param {(campo: object) => boolean} [ehObrigatorio] — permite honrar os
 *   overrides do admin (`isFieldRequired`), que vencem o `is_required`
 *   do próprio campo. Sem ela, lê-se `is_required` directamente.
 * @returns {{primarios: Array, secundarios: Array}}
 */
export function separarCamposPorPrioridade(campos, ehObrigatorio) {
  const lista = Array.isArray(campos) ? campos.filter(Boolean) : [];
  const decidir =
    typeof ehObrigatorio === "function"
      ? ehObrigatorio
      : (campo) => Boolean(campo?.is_required);

  const primarios = [];
  const secundarios = [];
  for (const campo of lista) {
    (decidir(campo) ? primarios : secundarios).push(campo);
  }

  // Um passo SEM campos obrigatórios não tem nada a esconder — e um
  // passo que abre visualmente vazio, com tudo atrás de um botão,
  // assusta mais do que a lista toda à vista. É o caso do 2º titular,
  // onde os 10 campos são todos opcionais.
  if (!primarios.length) {
    return { primarios: secundarios, secundarios: [] };
  }

  return { primarios, secundarios };
}

/**
 * Um valor conta como preenchido?
 *
 * `false` num booleano NÃO conta: os consentimentos RGPD são checkboxes
 * e um "não aceito" não é um campo respondido para efeitos de progresso.
 */
export function estaPreenchido(valor) {
  if (typeof valor === "boolean") return valor === true;
  if (Array.isArray(valor)) return valor.length > 0;
  if (valor === null || valor === undefined) return false;
  return String(valor).trim() !== "";
}

/**
 * Progresso contado SÓ sobre o que bloqueia mesmo.
 *
 * @param {string[]} chavesObrigatorias
 * @param {object} formData
 * @returns {{completos: number, total: number, percentagem: number}}
 */
export function contarProgressoObrigatorios(chavesObrigatorias, formData) {
  const chaves = Array.isArray(chavesObrigatorias)
    ? chavesObrigatorias.filter(Boolean)
    : [];
  const dados = formData || {};
  const total = chaves.length;
  if (!total) return { completos: 0, total: 0, percentagem: 0 };

  let completos = 0;
  for (const chave of chaves) {
    if (estaPreenchido(dados[chave])) completos += 1;
  }
  return {
    completos,
    total,
    percentagem: Math.round((completos / total) * 100),
  };
}

/**
 * Texto do painel de campos secundários.
 *
 * Nunca diz "obrigatório", "em falta" nem "tem de". Diz o que o cliente
 * ganha em preencher, e deixa claro que pode seguir sem isso — é essa a
 * diferença entre um formulário que acompanha e um que ameaça.
 */
export function textoDoPainelSecundario(quantidade) {
  if (!quantidade || quantidade < 1) return null;
  const plural = quantidade === 1 ? "" : "s";
  return {
    titulo: "Informação adicional importante",
    resumo:
      `${quantidade} campo${plural} que nos ajuda${quantidade === 1 ? "" : "m"} ` +
      "a preparar melhor o seu processo",
    ajuda:
      "Pode preencher agora ou mais tarde, na sua Área de Cliente. " +
      "Nada aqui o impede de continuar.",
  };
}
