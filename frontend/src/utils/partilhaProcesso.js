/**
 * Partilha de um processo (D-25) — regras puras do cartão de gestão.
 *
 * A Via Rápida abre um processo à rede de quem foi atribuído, sem aprovação,
 * e tirar a atribuição não revoga. Este é o lado manual: ver QUEM tem acesso
 * e retirá-lo. O servidor é a parede (decide quem pode revogar); isto só
 * traduz o documento e esconde o botão a quem de certeza não pode.
 */

/** Perfis que o servidor admite a revogar (a casa dona é validada lá). */
export const PAPEIS_QUE_REVOGAM = ["master", "admin", "ceo", "diretor"];

export function podeRevogarPartilha(papel) {
  return PAPEIS_QUE_REVOGAM.includes(String(papel || "").trim().toLowerCase());
}

/**
 * As empresas convidadas, na ordem do registo.
 * `Array.isArray` e nunca `|| []`: um objecto é truthy e o `.map` rebentaria
 * noutro sítio (FRONTEND_GUIDELINES § 27.38).
 */
export function parceirosDoProcesso(processo) {
  const registo = processo?.partner_companies;
  if (!Array.isArray(registo)) return [];
  const vistos = new Set();
  const parceiros = [];
  for (const entrada of registo) {
    const id = String(entrada?.company_id ?? "").trim();
    const nome = String(entrada?.company_name ?? "").trim();
    const chave = id || nome;
    if (!chave || vistos.has(chave)) continue;
    vistos.add(chave);
    parceiros.push({
      id,
      nome: nome || id,
      desde: typeof entrada?.added_at === "string" ? entrada.added_at : null,
    });
  }
  return parceiros;
}

/** Sem `company_id` não há como revogar: o botão não se desenha. */
export function sePodeRevogar(parceiro) {
  return Boolean(parceiro?.id);
}
