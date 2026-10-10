/**
 * Para onde vai o «Voltar» de uma página de detalhe.
 *
 * O caminho normal é recuar na história do browser: a listagem de onde se veio
 * está lá, com os filtros no URL (`?search=…&status=…&page=3`), e é isso que
 * devolve a pesquisa intacta. Só quando NÃO há história dentro da aplicação
 * (o detalhe foi aberto num separador novo ou por link directo) é que vale a
 * listagem de origem guardada no contexto de navegação — e só se existir.
 *
 * Como se sabe que não há história: o React Router dá à PRIMEIRA entrada da
 * sessão a chave `"default"` (`location.key`). Não se lê `window.history`:
 * não existe num `MemoryRouter` e, pior, daria a mesma resposta nos testes e
 * em produção só por acaso.
 */

/** A chave que o React Router atribui à primeira entrada de uma sessão. */
export const CHAVE_DA_PRIMEIRA_ENTRADA = "default";

/**
 * @param {Object} [args]
 * @param {string} [args.origem] — listagem de origem (`/processos?search=ana`)
 * @param {boolean} [args.primeiraEntrada] — esta é a primeira entrada da história?
 * @returns {number|string} — `-1` (recuar) ou o caminho da listagem de origem
 */
export function destinoDoVoltar({ origem, primeiraEntrada = false } = {}) {
  if (!primeiraEntrada) return -1;
  return typeof origem === "string" && origem.startsWith("/") && !origem.startsWith("//")
    ? origem
    : -1;
}
