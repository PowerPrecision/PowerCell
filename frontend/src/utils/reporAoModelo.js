/**
 * «Repor ao Modelo» — leitura do erro do servidor (puro).
 *
 * O servidor responde:
 *   403 { detail: "Password incorrecta." }                         → password errada
 *   429 { detail: { message, retry_after_minutes } }               → travão por tentativas
 *   409 { detail: { message, fases_em_uso: [{name, total}] } }     → processos em fases que o modelo não tem
 *   409 { detail: "O modelo de workflow está vazio…" }
 *   404 { detail: "Rede não encontrada" }
 *
 * Devolve `{ tipo, mensagem, fases }` — o diálogo escolhe o que mostra por `tipo`, nunca
 * por texto. `password_errada` é o único em que o campo se limpa e se volta a pedir.
 */
export function lerErroDeReposicao(err) {
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
    return {
      tipo: fases.length ? "fases_em_uso" : "recusado",
      mensagem: mensagem || "Não é possível repor ao modelo neste momento.",
      fases,
    };
  }
  if (status === 404) {
    return { tipo: "recusado", mensagem: mensagem || "Rede não encontrada.", fases: [] };
  }
  return {
    tipo: "erro",
    mensagem: "Não foi possível repor ao modelo. Tente novamente.",
    fases: [],
  };
}

export default { lerErroDeReposicao };
