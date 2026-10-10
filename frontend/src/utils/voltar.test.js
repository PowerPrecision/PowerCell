import { describe, expect, it } from "vitest";

import { destinoDoVoltar } from "./voltar";

describe("destinoDoVoltar", () => {
  it("com história dentro da app recua (a listagem volta com os filtros do URL)", () => {
    expect(destinoDoVoltar({ origem: "/processos?search=ana", primeiraEntrada: false })).toBe(-1);
  });

  it("por omissão assume que há história", () => {
    expect(destinoDoVoltar({ origem: "/processos?search=ana" })).toBe(-1);
    expect(destinoDoVoltar()).toBe(-1);
  });

  it("sem história (separador novo) vai para a listagem de origem, com a pesquisa", () => {
    expect(destinoDoVoltar({ origem: "/processos?search=ana&page=3", primeiraEntrada: true }))
      .toBe("/processos?search=ana&page=3");
  });

  it("sem história e sem origem recua (como antes)", () => {
    expect(destinoDoVoltar({ primeiraEntrada: true })).toBe(-1);
    expect(destinoDoVoltar({ origem: "", primeiraEntrada: true })).toBe(-1);
  });

  it("uma origem que não é um caminho da app nunca é seguida", () => {
    for (const mau of ["https://mau.exemplo/x", "//mau.exemplo/x", "javascript:alert(1)", 42, null]) {
      expect(destinoDoVoltar({ origem: mau, primeiraEntrada: true })).toBe(-1);
    }
  });
});
