/**
 * Controlo de histórico — regras puras do ecrã (Bloco 1, ponto 4).
 *
 * O servidor é a parede (só o ADMIN escreve; `indexacao` nunca se liga). Isto
 * só traduz o que ele devolve para o que se mostra, e garante duas coisas
 * que um ecrã honesto tem de garantir:
 *
 * 1. **Pessoa vence perfil** — o estado de uma pessoa tem TRÊS valores
 *    (segue o perfil / sempre ativo / desligado) e não dois: um interruptor
 *    binário não distingue «não decidi» de «decidi ligado», e é essa
 *    diferença que faz a pessoa voltar a seguir o perfil quando o perfil
 *    muda.
 * 2. **O que está bloqueado diz-se**: a Indexação aparece com o motivo, não
 *    escondida — um perfil que desaparece da lista lê-se como esquecimento.
 */

export const SEGUIR_PERFIL = "perfil";
export const SEMPRE_ATIVO = "ativo";
export const DESLIGADO = "desligado";

export const OPCOES_DE_PESSOA = [
  { value: SEGUIR_PERFIL, label: "Segue o perfil" },
  { value: SEMPRE_ATIVO, label: "Sempre ativo" },
  { value: DESLIGADO, label: "Desligado" },
];

/** Normaliza `GET /admin/history-tracking`. */
export function normalizarPerfis(data) {
  const lista = Array.isArray(data?.perfis) ? data.perfis : [];
  return lista
    .filter((p) => p && typeof p.role === "string" && p.role)
    .map((p) => ({
      role: p.role,
      enabled: p.enabled === true,
      locked: p.locked === true,
      motivo: typeof p.motivo === "string" ? p.motivo : null,
    }));
}

/** Normaliza `GET /admin/history-tracking/users`. */
export function normalizarUtilizadores(data) {
  const lista = Array.isArray(data?.utilizadores) ? data.utilizadores : [];
  return {
    utilizadores: lista
      .filter((u) => u && typeof u.id === "string" && u.id)
      .map((u) => ({
        id: u.id,
        name: u.name || u.email || u.id,
        email: u.email || "",
        role: u.role || "",
        is_active: u.is_active !== false,
        track_history: typeof u.track_history === "boolean" ? u.track_history : null,
        efectivo: u.efectivo === true,
        bloqueado: u.bloqueado === true,
      })),
    total: Number.isFinite(data?.total) ? data.total : lista.length,
  };
}

/** `track_history` do servidor (`true | false | null`) → valor do selector. */
export function valorDaPessoa(trackHistory) {
  if (trackHistory === true) return SEMPRE_ATIVO;
  if (trackHistory === false) return DESLIGADO;
  return SEGUIR_PERFIL;
}

/** Valor do selector → `enabled` do pedido (`true | false | null`). */
export function enabledDoPedido(valor) {
  if (valor === SEMPRE_ATIVO) return true;
  if (valor === DESLIGADO) return false;
  return null;
}

/** O que o utilizador realmente vai ter, em palavras. */
export function descricaoDoEstado(utilizador) {
  if (utilizador.bloqueado) return "Sempre silencioso (Indexação)";
  return utilizador.efectivo ? "Regista no histórico" : "Não regista no histórico";
}
