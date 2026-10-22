/**
 * Para onde leva um clique num processo, conforme o PERFIL ACTIVO (Out 2026).
 *
 * O Index não trabalha no detalhe comercial do processo: o seu trabalho é a bancada (`/index/:id`) — documentos,
 * metadados profissionais, matriz de verificação. Com a fusão dos menus, «Os Meus Processos» é a única lista da
 * equipa, e um clique de um indexador abre direto a bancada. Todos os outros perfis continuam no detalhe.
 *
 * Decide-se pelo perfil EFECTIVO (quem entra como Index com outro perfil de base também trabalha a bancada):
 * `user.role` daria a resposta errada a quem troca de chapéu.
 */
export const PAPEL_DA_BANCADA = "indexacao";

export function destinoDoProcesso(papel, processId) {
  const id = encodeURIComponent(String(processId ?? ""));
  return String(papel || "").toLowerCase() === PAPEL_DA_BANCADA ? `/index/${id}` : `/process/${id}`;
}

/** O clique abre a bancada (e não o detalhe)? Quem navega com estado de contexto (setas Anterior/Seguinte) precisa de saber. */
export const abreABancada = (papel) => String(papel || "").toLowerCase() === PAPEL_DA_BANCADA;
