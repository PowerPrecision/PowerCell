/**
 * paginacao — contas de páginas, em bruto.
 *
 * Ponto 11 (Lote 5, Secção B). As duas listagens do painel de
 * administração precisam das mesmas contas, e essas contas têm um caso
 * que se erra sempre: uma página fora do intervalo. Se o utilizador
 * estiver na página 5 e apertar a pesquisa até sobrar uma página, o
 * pedido à página 5 devolve VAZIO — e uma lista vazia parece "não há
 * resultados", não "estás na página errada".
 *
 * @module utils/paginacao
 */

/**
 * @param {object} [entrada]
 * @param {number} [entrada.total] - Itens no âmbito, não na página.
 * @param {number} [entrada.page]
 * @param {number} [entrada.size]
 * @returns {{paginaActual: number, totalPaginas: number, primeiro: number,
 *   ultimo: number, temAnterior: boolean, temSeguinte: boolean,
 *   foraDoIntervalo: boolean}}
 */
export function calcularPaginacao({ total, page, size } = {}) {
  const itens = Math.max(0, Number(total) || 0);
  const tamanho = Math.max(1, Number(size) || 25);
  const pedida = Math.max(1, Number(page) || 1);

  // Zero itens é UMA página vazia, não zero páginas: "Página 1 de 0"
  // não quer dizer nada.
  const totalPaginas = Math.max(1, Math.ceil(itens / tamanho));
  const paginaActual = Math.min(pedida, totalPaginas);

  const primeiro = itens === 0 ? 0 : (paginaActual - 1) * tamanho + 1;
  const ultimo = Math.min(paginaActual * tamanho, itens);

  return {
    paginaActual,
    totalPaginas,
    primeiro,
    ultimo,
    temAnterior: paginaActual > 1,
    temSeguinte: paginaActual < totalPaginas,
    // Quem chama usa isto para voltar à página 1 em vez de mostrar uma
    // lista vazia que parece "sem resultados".
    foraDoIntervalo: pedida > totalPaginas,
  };
}
