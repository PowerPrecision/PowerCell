import { describe, it, expect } from "vitest";
import { podeUsarFerramentasDeIA } from "./permissaoDeIA";

describe("podeUsarFerramentasDeIA", () => {
  it.each(["master", "admin", "ceo", "diretor"])("a gestão (%s) pode, mesmo sem resposta do servidor", (papel) => {
    expect(podeUsarFerramentasDeIA({ effectiveRole: papel })).toBe(true);
  });

  it.each(["consultor", "intermediario", "administrativo", "indexacao", undefined])(
    "%s sem a permissão do servidor não pode",
    (papel) => {
      expect(podeUsarFerramentasDeIA({ effectiveRole: papel })).toBe(false);
    },
  );

  it("o atribuído (servidor diz true) pode, seja qual for o cargo", () => {
    expect(
      podeUsarFerramentasDeIA({ effectiveRole: "intermediario", permissaoDoServidor: true }),
    ).toBe(true);
  });

  it("só o `true` ESTRITO abre: texto, 1 e objecto não contam", () => {
    for (const valor of ["true", 1, {}, [], "sim"]) {
      expect(
        podeUsarFerramentasDeIA({ effectiveRole: "consultor", permissaoDoServidor: valor }),
      ).toBe(false);
    }
  });

  it("`false` do servidor não tira a ferramenta à gestão (OU, nunca E)", () => {
    expect(
      podeUsarFerramentasDeIA({ effectiveRole: "diretor", permissaoDoServidor: false }),
    ).toBe(true);
  });

  it("processo fechado: ninguém, nem a gestão nem o atribuído", () => {
    expect(
      podeUsarFerramentasDeIA({ effectiveRole: "admin", permissaoDoServidor: true, somenteLeitura: true }),
    ).toBe(false);
  });

  it("sem argumentos não rebenta e nega", () => {
    expect(podeUsarFerramentasDeIA()).toBe(false);
  });
});
