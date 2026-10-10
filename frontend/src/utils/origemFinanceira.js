/**
 * Origem financeira de um processo — regras puras do cartão (Bloco 4, ponto 7).
 *
 * O cliente ou veio directamente à empresa (lead ORGÂNICA) ou foi angariado
 * por um utilizador específico (lead de ANGARIAÇÃO). Visível e editável só
 * pela gestão. O servidor é a parede (403 a quem não pode); isto só decide
 * se o cartão se desenha e traduz o formulário no pedido.
 */

export const TIPO_ORGANICA = "organica";
export const TIPO_ANGARIACAO = "angariacao";

export const ROTULOS_DA_ORIGEM = {
  [TIPO_ORGANICA]: "Veio diretamente à empresa",
  [TIPO_ANGARIACAO]: "Foi angariado por um utilizador específico",
};

/** Perfis que o servidor admite (a casa dona é validada lá). */
export const PAPEIS_DE_GESTAO = ["master", "admin", "ceo", "diretor"];

export function podeGerirOrigemFinanceira(papel) {
  return PAPEIS_DE_GESTAO.includes(String(papel || "").trim().toLowerCase());
}

/**
 * O pedido do formulário, ou a mensagem do que falta.
 * `organica` descarta o angariador (o servidor faz o mesmo; aqui evita-se
 * enviar um id que o utilizador já deixou de ver no ecrã).
 *
 * @returns {{ok: true, corpo: object} | {ok: false, erro: string}}
 */
export function montarPedido(tipo, angariadorId) {
  if (tipo === TIPO_ORGANICA) return { ok: true, corpo: { tipo: TIPO_ORGANICA } };
  if (tipo === TIPO_ANGARIACAO) {
    const id = String(angariadorId ?? "").trim();
    if (!id) return { ok: false, erro: "Escolha o utilizador que angariou o cliente." };
    return { ok: true, corpo: { tipo: TIPO_ANGARIACAO, angariador_id: id } };
  }
  return { ok: false, erro: "Escolha a origem do cliente." };
}

/**
 * Candidatos a angariador. `Array.isArray` e nunca `|| []` (§ 27.38).
 * @returns {Array<{id: string, nome: string, papel: string|null}>}
 */
export function candidatosValidos(resposta) {
  const lista = resposta?.candidatos;
  if (!Array.isArray(lista)) return [];
  return lista
    .filter((c) => c && typeof c.id === "string" && c.id)
    .map((c) => ({ id: c.id, nome: String(c.nome || c.id), papel: c.papel ?? null }));
}

/** Frase do estado actual — a que o cartão mostra antes de se editar. */
export function resumoDaOrigem(origem) {
  if (!origem?.definida) return "Ainda não definida";
  if (origem.tipo === TIPO_ANGARIACAO) {
    const nome = origem.angariador?.nome;
    return nome ? `Angariado por ${nome}` : ROTULOS_DA_ORIGEM[TIPO_ANGARIACAO];
  }
  return ROTULOS_DA_ORIGEM[origem.tipo] || "Ainda não definida";
}
