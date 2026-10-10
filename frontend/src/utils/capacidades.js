/**
 * Capacidades do perfil ACTIVO — o fim dos botões fantasma (Lote 6, ponto 3).
 *
 * O QUE ESTAVA MAL
 * ================
 * O backend tem um registo canónico de capacidades por cargo
 * (`models/permissions.ROLE_CAPABILITY_DEFAULTS`) e lá está escrito que o
 * perfil `indexacao` NÃO cria processos. O ecrã não o consultava: o botão
 * "Novo Processo" aparecia a todos, e quem não podia descobria pelo erro.
 *
 * O `hasPermission` do `roleUtils` existia, mas lia `user.role` — o cargo do
 * JWT — enquanto a porta do servidor usa o cargo EFECTIVO. Quem tem perfil
 * base de consultor e entra COMO diretor era avaliado como consultor: **as
 * duas respostas erradas**, menos botões num sentido e mais no outro. É a
 * forma do `history._is_stealth_user` e do botão de eliminar cliente.
 *
 * A DECISÃO QUE PARECE AO CONTRÁRIO
 * =================================
 * Quando o contrato NÃO vem (sessão antiga, `/auth/me` de uma versão
 * anterior), isto **deixa passar**. Um gate de UI que falha fechado esconde
 * TODOS os botões a TODOS os utilizadores no dia de um deploy desalinhado — e
 * um ecrã sem botões não produz erro nenhum, ninguém sabe porquê, e parece
 * que a aplicação está partida.
 *
 * Isto não é a parede: a parede é o `require_roles`/`exigir_capacidade` do
 * servidor, que falha FECHADO. Aqui o objectivo é não oferecer o que não se
 * pode fazer; falhar aberto devolve apenas o comportamento anterior.
 */

/** Cargos com bypass total (iguais aos `SUPER_ADMIN_ROLES` do backend). */
export const PAPEIS_COM_BYPASS = ["master", "admin", "ceo"];

/** As capacidades que os ecrãs deste lote consultam. */
export const CRIAR_PROCESSO = "PROCESS_CREATE";
export const EDITAR_PROCESSO = "PROCESS_EDIT";
export const ELIMINAR_PROCESSO = "PROCESS_DELETE";
export const EXPORTAR_PROCESSO = "PROCESS_EXPORT";
export const CRIAR_CLIENTE = "CLIENT_CREATE";
export const ELIMINAR_CLIENTE = "CLIENT_DELETE";

/**
 * Explicações no ecrã, por capacidade. Um cadeado sem motivo manda o
 * utilizador perguntar a alguém; com motivo, resolve-se sozinho.
 */
export const MOTIVOS = {
  [CRIAR_PROCESSO]: "O perfil activo não cria processos.",
  [EDITAR_PROCESSO]: "O perfil activo não edita processos.",
  [ELIMINAR_PROCESSO]: "O perfil activo não elimina processos.",
  [EXPORTAR_PROCESSO]: "O perfil activo não exporta processos.",
  [CRIAR_CLIENTE]: "O perfil activo não cria clientes.",
  [ELIMINAR_CLIENTE]: "O perfil activo não elimina clientes.",
};

const normalizar = (valor) => String(valor ?? "").trim().toLowerCase();

/**
 * O mapa de capacidades para um papel, ou `null` quando não há contrato.
 *
 * `null` e não `{}`: "não sei" e "sei que não tem nenhuma" são respostas
 * diferentes, e tratá-las como a mesma é o que esconderia todos os botões.
 */
export const capacidadesDoPapel = (user, papel) => {
  const porPapel = user?.capabilities_por_papel;
  const nome = normalizar(papel);
  if (porPapel && nome && porPapel[nome]) return porPapel[nome];
  // Recurso para sessões anteriores a este lote: o mapa plano do cargo base.
  const planas =
    user?.permissions?.effective_capabilities || user?.permissions?.capabilities;
  if (planas && Object.keys(planas).length > 0) return planas;
  return null;
};

/**
 * O utilizador, com o perfil indicado, pode executar esta acção?
 *
 * @param {object} user - utilizador do `AuthContext`
 * @param {string} capacidade - ex. `PROCESS_CREATE`
 * @param {string} papel - o perfil ACTIVO (`effectiveRole`), não `user.role`
 */
export const podeFazer = (user, capacidade, papel) => {
  if (!user || !capacidade) return false;
  const nome = normalizar(papel) || normalizar(user.role);
  if (PAPEIS_COM_BYPASS.includes(nome)) return true;
  const capacidades = capacidadesDoPapel(user, nome);
  if (capacidades === null) return true; // sem contrato não se esconde nada
  if (!(capacidade in capacidades)) return false; // conhecido e ausente = não
  return Boolean(capacidades[capacidade]);
};

/** O texto do cadeado. Nunca vazio: um cadeado mudo não ensina nada. */
export const motivoDoBloqueio = (capacidade) =>
  MOTIVOS[capacidade] || "O perfil activo não tem permissão para esta acção.";
