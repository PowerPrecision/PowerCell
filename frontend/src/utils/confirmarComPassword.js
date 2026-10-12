/**
 * Confirmação de uma acção destrutiva com a PASSWORD actual — leitura do erro do servidor (puro).
 *
 * O servidor (`reauth_password`) responde:
 *   400 { detail: "Indique a sua password…" }                    → faltou a password
 *   403 { detail: "Password incorrecta." }                       → password errada (NUNCA 401: o
 *                                                                  interceptor deslogaria o utilizador)
 *   429 { detail: { message, retry_after_minutes } }             → travão por tentativas
 *   409 { detail: { message, fases_em_uso: [{name, total}] } }   → recusa de estado (repor ao modelo)
 *   404 { detail: "…" }                                          → o alvo já não existe / fora do âmbito
 *
 * Devolve `{ tipo, mensagem, fases }` — o diálogo escolhe o que mostra por `tipo`, nunca por texto.
 * `password_errada` é o único em que o campo se limpa e se volta a pedir.
 *
 * @param {*} err
 * @param {{ recusado?: string, naoEncontrado?: string, erro?: string }} [textos]  mensagens de recuo
 */
export function lerErroDeConfirmacao(err, textos = {}) {
  const {
    recusado = "Não é possível executar esta acção neste momento.",
    naoEncontrado = "O registo já não existe.",
    erro = "Não foi possível concluir a acção. Tente novamente.",
  } = textos;
  const status = err?.response?.status;
  const detail = err?.response?.data?.detail;
  const mensagem =
    typeof detail === "string" ? detail : typeof detail?.message === "string" ? detail.message : null;

  if (status === 403) {
    return { tipo: "password_errada", mensagem: mensagem || "Password incorrecta.", fases: [] };
  }
  if (status === 429) {
    return {
      tipo: "bloqueado",
      mensagem: mensagem || "Muitas tentativas falhadas. Tente novamente dentro de alguns minutos.",
      fases: [],
    };
  }
  if (status === 409) {
    // `Array.isArray` e não `|| []`: ver FRONTEND_GUIDELINES § 27.38.
    const fases = Array.isArray(detail?.fases_em_uso) ? detail.fases_em_uso : [];
    return { tipo: fases.length ? "fases_em_uso" : "recusado", mensagem: mensagem || recusado, fases };
  }
  if (status === 400 || status === 404) {
    return { tipo: "recusado", mensagem: mensagem || (status === 404 ? naoEncontrado : recusado), fases: [] };
  }
  return { tipo: "erro", mensagem: erro, fases: [] };
}

export default { lerErroDeConfirmacao };
