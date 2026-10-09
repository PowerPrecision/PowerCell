/**
 * Portal bloqueado por processo inativo (Bloco 3, ponto 14).
 *
 * O servidor responde 403 com `detail: { codigo: "portal_inativo", mensagem }`
 * em CADA pedido do Portal, nos logins e no link curto. O ecrã decide pelo
 * CÓDIGO e nunca pelo texto, que pode mudar; o texto só se mostra.
 */

export const CODIGO_PORTAL_INATIVO = "portal_inativo";

export const MENSAGEM_PORTAL_INATIVO =
  "O acesso ao Portal está suspenso porque este processo se encontra inativo. Contacte o seu consultor.";

/**
 * A resposta é o bloqueio por processo inativo?
 *
 * @param {number} status Código HTTP.
 * @param {*} corpo Corpo JSON já lido (ou `undefined`).
 */
export const eBloqueioDoPortal = (status, corpo) =>
  status === 403 &&
  corpo != null &&
  typeof corpo === "object" &&
  corpo.detail != null &&
  typeof corpo.detail === "object" &&
  corpo.detail.codigo === CODIGO_PORTAL_INATIVO;

/** O texto a mostrar; recua para a mensagem canónica se o servidor não a trouxer. */
export const mensagemDoBloqueio = (corpo) => {
  const mensagem = corpo?.detail?.mensagem;
  return typeof mensagem === "string" && mensagem.trim() ? mensagem : MENSAGEM_PORTAL_INATIVO;
};

/** Chaves onde o Portal guarda a sessão do cliente (localStorage e sessionStorage). */
export const CHAVES_DA_SESSAO_DO_PORTAL = [
  "portalToken",
  "portal_token",
  "portalClientId",
  "portalClientName",
  "portalProcessId",
  "portalAuthMethod",
  "portalLastActivity",
  "portal_verified",
  "portal_client_id",
  "portal_client_name",
  "portal_process_id",
  "portalVerified",
];

/** Esquece a sessão. Nunca levanta: um storage bloqueado não pode partir o ecrã. */
export const limparSessaoDoPortal = () => {
  for (const armazem of ["localStorage", "sessionStorage"]) {
    try {
      const s = window[armazem];
      CHAVES_DA_SESSAO_DO_PORTAL.forEach((chave) => s.removeItem(chave));
    } catch {
      /* storage indisponível — o servidor continua a recusar o token */
    }
  }
};
