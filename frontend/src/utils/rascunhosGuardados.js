/**
 * Rascunhos da página «Rascunhos» (notas/modelos de texto do próprio utilizador).
 *
 * Vivem no `localStorage` do browser (não há API). O defeito (Lote 4, Out 2026):
 * a chave era UMA para o browser inteiro — trocar de empresa no cabeçalho, ou outra
 * pessoa entrar no mesmo computador, mostrava os rascunhos de quem lá esteve antes,
 * incluindo os de outra empresa. Hoje a chave leva o utilizador E a empresa activa.
 *
 * Os rascunhos antigos (chave sem âmbito) não se perdem nem se espalham: passam UMA vez
 * para o âmbito de quem abrir a página primeiro e a chave antiga é apagada.
 */

export const CHAVE_LEGADA = "powercell_drafts";

const SEM_VALOR = "sem";

export function chaveDosRascunhos(userId, companyId) {
  return `${CHAVE_LEGADA}:${userId || SEM_VALOR}:${companyId || SEM_VALOR}`;
}

function ler(chave) {
  try {
    const bruto = localStorage.getItem(chave);
    if (!bruto) return null;
    const valor = JSON.parse(bruto);
    return Array.isArray(valor) ? valor : null;
  } catch {
    return null;
  }
}

/** Os rascunhos deste utilizador nesta empresa (migra os antigos uma vez). */
export function carregarRascunhos(chave) {
  const proprios = ler(chave);
  if (proprios) return proprios;

  const antigos = ler(CHAVE_LEGADA);
  if (antigos) {
    guardarRascunhos(chave, antigos);
    try {
      localStorage.removeItem(CHAVE_LEGADA);
    } catch {
      // storage indisponível: a cópia antiga fica, mas já não é lida
    }
    return antigos;
  }
  return [];
}

export function guardarRascunhos(chave, rascunhos) {
  try {
    localStorage.setItem(chave, JSON.stringify(rascunhos));
  } catch {
    // localStorage cheio ou indisponível
  }
}
