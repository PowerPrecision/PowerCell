/**
 * Limiares de SLA por macro-fase — regras puras do formulário.
 *
 * Os limiares dizem quantos DIAS um processo pode ficar numa macro-fase antes
 * de contar como atrasado no BI. Vivem em `SystemConfig.dashboard_slas` e
 * nunca no código (mudar um limiar não pode exigir um deploy).
 *
 * As macro-fases TERMINAIS não têm limiar de propósito: um processo concluído
 * não demora em concluído, fica lá. Ver
 * `services/process_phase_clock.MACROS_SEM_PERMANENCIA`.
 */

/** As três macro-fases com limiar, na ordem do funil. */
export const MACROS_COM_SLA = [
  { chave: "novo", etiqueta: "Novo", ajuda: "Entre a entrada e o início da análise" },
  { chave: "analise", etiqueta: "Análise", ajuda: "Recolha documental e instrução do processo" },
  { chave: "aprovado", etiqueta: "Aprovado", ajuda: "Entre a aprovação e a escritura" },
];

/** Omissões do backend (`models/system_config.DashboardSlaConfig`). */
export const LIMIARES_POR_OMISSAO = {
  enabled: true,
  novo: 7,
  analise: 15,
  aprovado: 30,
};

/** Um limiar é um número de dias inteiro e positivo; o máximo evita gralhas. */
export const MINIMO_DE_DIAS = 1;
export const MAXIMO_DE_DIAS = 365;

/**
 * Formulário a partir do que o servidor devolveu.
 *
 * Os campos ficam em TEXTO de propósito: um `<input type="number">` com estado
 * numérico não deixa apagar o conteúdo para escrever outro valor (o `0`
 * reaparece a cada tecla). A conversão acontece só no `construirPayload`.
 */
export function hidratarLimiares(config) {
  const base = { ...LIMIARES_POR_OMISSAO, ...(config || {}) };
  return {
    enabled: base.enabled !== false,
    novo: String(base.novo ?? LIMIARES_POR_OMISSAO.novo),
    analise: String(base.analise ?? LIMIARES_POR_OMISSAO.analise),
    aprovado: String(base.aprovado ?? LIMIARES_POR_OMISSAO.aprovado),
  };
}

/**
 * Valida um campo e devolve a mensagem de erro, ou `""` se estiver bem.
 *
 * Devolve a MENSAGEM e não um booleano porque quem valida sabe porque é que
 * recusou, e obrigar o componente a redescobri-lo duplicava a regra.
 */
export function erroDoLimiar(valor) {
  const texto = String(valor ?? "").trim();
  if (!texto) return "Indique um número de dias.";
  if (!/^\d+$/.test(texto)) return "Só números inteiros de dias.";
  const numero = Number(texto);
  if (numero < MINIMO_DE_DIAS) return `O mínimo é ${MINIMO_DE_DIAS} dia.`;
  if (numero > MAXIMO_DE_DIAS) return `O máximo é ${MAXIMO_DE_DIAS} dias.`;
  return "";
}

/** Mapa `{campo: mensagem}` só com os campos que têm erro. */
export function errosDoFormulario(formulario) {
  const erros = {};
  for (const { chave } of MACROS_COM_SLA) {
    const erro = erroDoLimiar(formulario?.[chave]);
    if (erro) erros[chave] = erro;
  }
  return erros;
}

/**
 * Payload para o `PATCH`, ou `null` quando há erros.
 *
 * Devolve NÚMEROS: o backend valida com Pydantic e uma string passaria a
 * coerção, mas gravar `"7"` onde o resto do sistema tem `7` é a diferença que
 * mais tarde faz um `===` falhar em silêncio.
 */
export function construirPayload(formulario) {
  if (Object.keys(errosDoFormulario(formulario)).length > 0) return null;
  return {
    enabled: Boolean(formulario.enabled),
    novo: Number(formulario.novo),
    analise: Number(formulario.analise),
    aprovado: Number(formulario.aprovado),
  };
}

/** `true` se o formulário difere do que veio do servidor. */
export function houveAlteracoes(formulario, config) {
  const original = hidratarLimiares(config);
  return (
    original.enabled !== Boolean(formulario.enabled) ||
    MACROS_COM_SLA.some(({ chave }) => original[chave] !== String(formulario[chave]))
  );
}
