/**
 * A sessão do Portal do Parceiro — onde vive o token e quando morre.
 *
 * PORQUE É UM MÓDULO À PARTE, COM CHAVE E ARMAZENAMENTO PRÓPRIOS
 * ==============================================================
 * O parceiro é uma família de identidade diferente da do staff (outro
 * segredo, outro `type`, outra dependência no servidor). O cliente HTTP do
 * staff (`services/api.js`) lê o token do staff e injecta `X-Company-Id` e
 * `X-Active-Role` — dois cabeçalhos que um parceiro não deve enviar nem
 * sequer conhecer. Por isso o token do parceiro:
 *
 *   * vive sob uma chave que o cliente do staff NUNCA lê;
 *   * vive em `sessionStorage` (por separador, morre com ele) e não em
 *     `localStorage`: uma sessão de 8 horas num computador partilhado de
 *     uma agência não deve sobreviver ao fecho do browser;
 *   * é lido através deste módulo, que não rebenta quando o armazenamento
 *     está bloqueado (modo privado, política do browser): sem token, o
 *     ecrã mostra o login — nunca um erro em branco.
 */

export const CHAVE_DA_SESSAO = "powercell_partner_session";
export const EVENTO_SESSAO_EXPIRADA = "partner:sessao-expirada";

/** O armazenamento, ou `null` quando o browser o recusa (nunca levanta). */
function armazenamento() {
  try {
    const s = globalThis.sessionStorage;
    if (!s) return null;
    // Alguns browsers só levantam ao ESCREVER.
    s.setItem("__partner_probe__", "1");
    s.removeItem("__partner_probe__");
    return s;
  } catch {
    return null;
  }
}

/** `{ token, expiraEm }` ou `null`. Uma sessão já expirada conta como nenhuma. */
export function lerSessao(agora = Date.now()) {
  const s = armazenamento();
  if (!s) return null;
  try {
    const bruto = s.getItem(CHAVE_DA_SESSAO);
    if (!bruto) return null;
    const sessao = JSON.parse(bruto);
    if (!sessao || typeof sessao.token !== "string" || !sessao.token) return null;
    if (typeof sessao.expiraEm === "number" && sessao.expiraEm <= agora) {
      s.removeItem(CHAVE_DA_SESSAO);
      return null;
    }
    return { token: sessao.token, expiraEm: sessao.expiraEm ?? null };
  } catch {
    return null;
  }
}

export function lerToken() {
  return lerSessao()?.token ?? null;
}

/** Guarda o token. `expiraEmSegundos` vem do servidor (`expires_in`). */
export function guardarSessao(token, expiraEmSegundos, agora = Date.now()) {
  const s = armazenamento();
  if (!s || !token) return false;
  try {
    const expiraEm =
      Number.isFinite(expiraEmSegundos) && expiraEmSegundos > 0
        ? agora + expiraEmSegundos * 1000
        : null;
    s.setItem(CHAVE_DA_SESSAO, JSON.stringify({ token, expiraEm }));
    return true;
  } catch {
    return false;
  }
}

export function limparSessao() {
  const s = armazenamento();
  if (!s) return;
  try {
    s.removeItem(CHAVE_DA_SESSAO);
  } catch {
    /* nada a fazer: sem armazenamento não há sessão a limpar */
  }
}

/** Avisa a árvore do parceiro de que a sessão morreu (401 do servidor). */
export function anunciarSessaoExpirada() {
  limparSessao();
  try {
    globalThis.dispatchEvent?.(new Event(EVENTO_SESSAO_EXPIRADA));
  } catch {
    /* ambiente sem eventos */
  }
}
