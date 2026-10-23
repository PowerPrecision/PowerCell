import { describe, expect, it } from "vitest";

import { nomeLivre, nomesLivresDoLote } from "./nomesDeFicheiro";

describe("nomeLivre — nunca sobrepor um ficheiro do dossier", () => {
  it("um nome livre fica como está", () => {
    expect(nomeLivre("recibo.pdf", ["outro.pdf"])).toBe("recibo.pdf");
    expect(nomeLivre("recibo.pdf", [])).toBe("recibo.pdf");
    expect(nomeLivre("recibo.pdf", undefined)).toBe("recibo.pdf");
  });

  it("um nome ocupado ganha (2) antes da extensão", () => {
    expect(nomeLivre("recibo.pdf", ["recibo.pdf"])).toBe("recibo (2).pdf");
  });

  it("não distingue maiúsculas nem espaços à volta", () => {
    expect(nomeLivre("Recibo.PDF", [" recibo.pdf "])).toBe("Recibo (2).PDF");
  });

  it("salta os números já usados", () => {
    expect(nomeLivre("recibo.pdf", ["recibo.pdf", "recibo (2).pdf", "recibo (3).pdf"])).toBe("recibo (4).pdf");
  });

  it("um nome sem extensão e um que começa por ponto não rebentam", () => {
    expect(nomeLivre("recibo", ["recibo"])).toBe("recibo (2)");
    expect(nomeLivre(".oculto", [".oculto"])).toBe(".oculto (2)");
  });

  it("só a última extensão conta", () => {
    expect(nomeLivre("a.b.pdf", ["a.b.pdf"])).toBe("a.b (2).pdf");
  });
});

describe("nomesLivresDoLote — também não pisam os do próprio lote", () => {
  it("dois ficheiros com o mesmo nome no mesmo lote ficam diferentes", () => {
    expect(nomesLivresDoLote(["a.pdf", "a.pdf", "a.pdf"], [])).toEqual(["a.pdf", "a (2).pdf", "a (3).pdf"]);
  });

  it("conta os existentes e os do lote", () => {
    expect(nomesLivresDoLote(["a.pdf", "b.pdf", "a.pdf"], ["a.pdf"])).toEqual(["a (2).pdf", "b.pdf", "a (3).pdf"]);
  });

  it("devolve uma lista da mesma dimensão e aceita vazio", () => {
    expect(nomesLivresDoLote([], ["x"])).toEqual([]);
    expect(nomesLivresDoLote(undefined, undefined)).toEqual([]);
  });
});
