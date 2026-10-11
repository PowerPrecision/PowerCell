/**
 * «Marcar como Pago» na Lista de Processos — quando se oferece.
 *
 * As comissões pagam-se no FIM, com o processo já «Concluído». O servidor
 * (excepção cirúrgica ao D-34) deixa passar a «paga» uma comissão de um
 * processo fechado sem o reabrir; este módulo diz à listagem para quais
 * linhas mostrar o atalho.
 *
 * A DECISÃO É DO SERVIDOR, não do ecrã: `processo_fechado` e
 * `comissoes_pendentes` vêm calculados ao servir (nunca gravados) e só vêm
 * para quem pode marcar como pago — para os outros perfis as chaves nem
 * existem, e o botão não aparece. O ecrã não repete a lista de papéis nem a
 * lista de fases terminais (duas cópias divergem sem dar erro).
 */

/**
 * Quem pode marcar uma comissão como paga. ESPELHO de
 * `PAPEIS_QUE_MARCAM_COMO_PAGO` (backend/services/finance_helpers.py) — há
 * um teste que lê o Python e exige o mesmo conjunto. Serve só para não
 * mostrar um botão que o servidor vai recusar nas Finanças (onde as linhas
 * vêm para todos os perfis de leitura); na Lista de Processos a decisão é
 * das chaves que o servidor manda.
 */
export const PAPEIS_QUE_MARCAM_COMO_PAGO = Object.freeze([
  "master", "admin", "ceo", "diretor", "administrativo",
]);

export function temDireitoAMarcarComoPago(papel) {
  return PAPEIS_QUE_MARCAM_COMO_PAGO.includes(String(papel || "").toLowerCase());
}

/**
 * @param {Object|null|undefined} processo - uma linha da listagem
 * @returns {boolean}
 */
export function deveOferecerMarcarComoPago(processo) {
  if (!processo || processo.processo_fechado !== true) return false;
  const pendentes = Number(processo.comissoes_pendentes);
  return Number.isFinite(pendentes) && pendentes > 0;
}

/** «1 comissão» / «2 comissões». */
export function textoDasComissoes(quantidade) {
  const n = Number(quantidade) || 0;
  return n === 1 ? "1 comissão" : `${n} comissões`;
}

/**
 * A linha depois de pagar: nada por pagar. Pura — devolve uma linha nova.
 * @param {Object} processo
 * @param {number} [atualizadas] - o `updated` do servidor
 */
export function aposMarcarComoPago(processo, atualizadas) {
  const restantes = Math.max(0, Number(processo?.comissoes_pendentes || 0) - Number(atualizadas || 0));
  return { ...processo, comissoes_pendentes: restantes };
}
