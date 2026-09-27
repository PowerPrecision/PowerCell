/**
 * Contas de paginação — ponto 11 (Lote 5, Secção B).
 *
 * O caso que se erra sempre: uma página fora do intervalo. Com o
 * utilizador na página 5, apertar a pesquisa até sobrar uma página faz
 * o pedido à página 5 devolver VAZIO — e uma lista vazia parece "não há
 * resultados", não "estás na página errada". É a mesma confusão do
 * ponto 13 (erro disfarçado de lista vazia) noutra forma.
 */
import { describe, expect, it } from "vitest";

import { calcularPaginacao } from "./paginacao";

describe("calcularPaginacao — contas básicas", () => {
  it("25 itens em páginas de 10 dão 3 páginas", () => {
    const p = calcularPaginacao({ total: 25, page: 1, size: 10 });
    expect(p.totalPaginas).toBe(3);
    expect(p.primeiro).toBe(1);
    expect(p.ultimo).toBe(10);
  });

  it("a última página mostra só o que resta", () => {
    const p = calcularPaginacao({ total: 25, page: 3, size: 10 });
    expect(p.primeiro).toBe(21);
    expect(p.ultimo).toBe(25);
    expect(p.temSeguinte).toBe(false);
  });

  it("um total exacto não cria uma página a mais", () => {
    const p = calcularPaginacao({ total: 20, page: 1, size: 10 });
    expect(p.totalPaginas).toBe(2);
  });
});

describe("calcularPaginacao — os limites", () => {
  it("zero itens é UMA página vazia, não zero", () => {
    // "Página 1 de 0" não quer dizer nada.
    const p = calcularPaginacao({ total: 0, page: 1, size: 10 });
    expect(p.totalPaginas).toBe(1);
    expect(p.primeiro).toBe(0);
    expect(p.ultimo).toBe(0);
    expect(p.temSeguinte).toBe(false);
  });

  it("uma página fora do intervalo é DITA e corrigida", () => {
    const p = calcularPaginacao({ total: 5, page: 5, size: 10 });
    expect(p.foraDoIntervalo).toBe(true);
    expect(p.paginaActual).toBe(1);
  });

  it("uma página dentro do intervalo não se queixa", () => {
    // Contraprova: se `foraDoIntervalo` fosse sempre verdadeiro, a
    // página voltava ao início a cada navegação.
    const p = calcularPaginacao({ total: 25, page: 2, size: 10 });
    expect(p.foraDoIntervalo).toBe(false);
    expect(p.paginaActual).toBe(2);
  });

  it("a primeira página não tem anterior", () => {
    expect(calcularPaginacao({ total: 25, page: 1, size: 10 }).temAnterior).toBe(false);
  });
});

describe("calcularPaginacao — entradas inválidas", () => {
  it("sem argumentos não rebenta", () => {
    const p = calcularPaginacao();
    expect(p.paginaActual).toBe(1);
    expect(p.totalPaginas).toBe(1);
  });

  it("valores absurdos são aparados", () => {
    const p = calcularPaginacao({ total: -5, page: 0, size: 0 });
    expect(p.paginaActual).toBe(1);
    expect(p.totalPaginas).toBe(1);
    expect(p.primeiro).toBe(0);
  });

  it("texto em vez de número cai nas omissões", () => {
    const p = calcularPaginacao({ total: "muitos", page: "x", size: "y" });
    expect(p.paginaActual).toBe(1);
    expect(p.totalPaginas).toBe(1);
  });
});
