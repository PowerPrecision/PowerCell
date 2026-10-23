/**
 * Capacidades da REDE da empresa em vigor (caso Domus, Out 2026).
 *
 * O `/auth/me` devolve `capabilities: { has_index }`, calculada pelo servidor a partir da equipa da rede
 * (`network_triage.capacidades_da_rede`): uma rede «tem Index» quando tem pelo menos um indexador activo.
 * É uma pergunta sobre a REDE e não sobre o perfil — por isso o Master também a vê respondida: com a
 * Domus escolhida no cabeçalho, «Supervisão do Index» não faz sentido, e uma fila vazia a convidar a
 * esperar processos que nunca lá chegam é pior do que não ter o item.
 *
 * Falha ABERTA: sem o campo (sessão anterior ao deploy) ou com algo que não seja um `false` estrito, o
 * módulo fica à vista. Esconder um menu por falta de contrato esconde-o a todos sem erro nenhum; a parede é
 * o servidor.
 */

/** O módulo Index está ao dispor desta rede? Só um `false` ESTRITO o nega. */
export function redeTemIndex(user) {
  return user?.capabilities?.has_index !== false;
}

/** Ligação do módulo Index que se esconde quando a rede não o tem. */
export const HREF_DA_SUPERVISAO_DO_INDEX = "/index";

/**
 * Tira do menu a supervisão do Index quando a rede não tem o módulo. Devolve o MESMO objecto se não há nada a
 * tirar (não força renders) e um novo, sem mexer no original, quando há.
 */
export function retirarModuloIndex(navData, user) {
  if (!navData || redeTemIndex(user)) return navData;
  const sem = (itens) =>
    Array.isArray(itens) ? itens.filter((i) => i?.href !== HREF_DA_SUPERVISAO_DO_INDEX) : itens;
  const grupos = Array.isArray(navData.groups)
    ? navData.groups.map((g) => ({ ...g, items: sem(g.items) }))
    : navData.groups;
  return { ...navData, main: sem(navData.main), groups: grupos };
}
