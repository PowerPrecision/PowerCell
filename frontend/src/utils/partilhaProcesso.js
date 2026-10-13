/**
 * Partilha de um processo (D-25) — regras puras do cartão de gestão.
 *
 * A Via Rápida abre um processo à rede de quem foi atribuído, sem aprovação,
 * e tirar a atribuição não revoga. Este é o lado manual: ver QUEM tem acesso
 * e retirá-lo. O servidor é a parede (decide quem pode revogar); isto só
 * traduz o documento e esconde o botão a quem de certeza não pode.
 */

/**
 * Perfis que o servidor admite a ENVIAR um processo para outra rede.
 * ESPELHO de `PAPEIS_QUE_PARTILHAM` (backend/services/process_sharing_api.py) —
 * há um teste que lê o Python. A casa dona é validada no servidor.
 */
export const PAPEIS_QUE_PARTILHAM = ["master", "admin", "ceo", "diretor", "administrativo"];

export function podePartilharProcesso(papel) {
  return PAPEIS_QUE_PARTILHAM.includes(String(papel || "").trim().toLowerCase());
}

/**
 * Como o ecrã descreve o que vai acontecer ao enviar para um destino.
 * Pura — o servidor repete a decisão; isto só evita surpresas.
 *
 * @param {{tem_index?: boolean}|null} destino
 * @param {boolean} viaVerde
 * @returns {string}
 */
export function efeitoDaPartilha(destino, viaVerde) {
  if (!destino) return "";
  if (destino.ja_partilhado) return "Este processo já está partilhado com esta rede.";
  if (!destino.tem_index) {
    return "Esta rede não tem equipa de Index: vai ver o processo, sem fila de triagem.";
  }
  // O remetente escolhe a REDE, nunca a pessoa: a distribuição interna é do destino.
  return viaVerde
    ? "Via Verde: salta o Index desta rede; consultor e intermediário são atribuídos pela própria rede de destino."
    : "Entra na fila de Index desta rede; é a rede que decide quem o trata.";
}

/** Nome legível de um destino: as empresas da rede. */
export function nomeDoDestino(destino) {
  const empresas = Array.isArray(destino?.empresas) ? destino.empresas.filter(Boolean) : [];
  return empresas.length ? empresas.join(" / ") : String(destino?.network_id ?? "");
}

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
  // Cadeia (Out 2026): o servidor diz DE QUEM veio cada elo e se o utilizador o pode
  // retirar (`linhagem.partilhas`). Sem a linhagem (sessão/servidor antigos) fica `null`:
  // não se sabe, e o botão volta a depender só do papel — o servidor recusa na mesma.
  const extras = new Map();
  for (const p of Array.isArray(processo?.linhagem?.partilhas) ? processo.linhagem.partilhas : []) {
    const chave = String(p?.company_id ?? "").trim() || String(p?.nome ?? "").trim();
    if (chave) extras.set(chave, p);
  }
  const vistos = new Set();
  const parceiros = [];
  for (const entrada of registo) {
    const id = String(entrada?.company_id ?? "").trim();
    const nome = String(entrada?.company_name ?? "").trim();
    const chave = id || nome;
    if (!chave || vistos.has(chave)) continue;
    vistos.add(chave);
    const extra = extras.get(chave);
    parceiros.push({
      id,
      nome: nome || id,
      desde: typeof entrada?.added_at === "string" ? entrada.added_at : null,
      partilhadoPor: typeof extra?.partilhado_por === "string" && extra.partilhado_por.trim()
        ? extra.partilhado_por.trim()
        : null,
      // Só o booleano estrito do servidor conta; qualquer outra coisa é «não sei».
      podeRevogar: typeof extra?.pode_revogar === "boolean" ? extra.pode_revogar : null,
    });
  }
  return parceiros;
}

/**
 * Sem `company_id` não há como revogar: o botão não se desenha. E com a cadeia, uma
 * convidada só retira os elos que abriu: se o servidor disse `pode_revogar: false`, o
 * botão não se desenha (em vez de aparecer para devolver um 403).
 */
export function sePodeRevogar(parceiro) {
  return Boolean(parceiro?.id) && parceiro?.podeRevogar !== false;
}
