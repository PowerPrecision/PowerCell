import { describe, it, expect } from "vitest";
import { podeUsarFerramentasDeIA } from "./permissaoDeIA";

describe("podeUsarFerramentasDeIA", () => {
  it.each(["master", "admin", "ceo", "diretor"])("os altos perfis (%s) podem, mesmo sem resposta do servidor", (papel) => {
    expect(podeUsarFerramentasDeIA({ effectiveRole: papel })).toBe(true);
  });

  it.each(["consultor", "intermediario", "administrativo", "indexacao", "parceiro", undefined])(
    "%s não pode",
    (papel) => {
      expect(podeUsarFerramentasDeIA({ effectiveRole: papel })).toBe(false);
    },
  );

  it("estar atribuído NÃO abre: nem com o servidor a dizer true, o cargo operacional não passa", () => {
    // Invertido: antes, `permissaoDoServidor: true` abria a ferramenta ao atribuído.
    for (const papel of ["consultor", "intermediario", "administrativo"]) {
      expect(podeUsarFerramentasDeIA({ effectiveRole: papel, permissaoDoServidor: true })).toBe(false);
    }
  });

  it("um `false` explícito do servidor (processo fora do âmbito de rede) estreita a gestão", () => {
    expect(podeUsarFerramentasDeIA({ effectiveRole: "diretor", permissaoDoServidor: false })).toBe(false);
  });

  it("um valor que não é `false` estrito não tira o botão à gestão", () => {
    for (const valor of [undefined, null, 0, "false", true]) {
      expect(podeUsarFerramentasDeIA({ effectiveRole: "admin", permissaoDoServidor: valor })).toBe(true);
    }
  });

  it("processo fechado: ninguém, nem a gestão", () => {
    expect(
      podeUsarFerramentasDeIA({ effectiveRole: "admin", permissaoDoServidor: true, somenteLeitura: true }),
    ).toBe(false);
  });

  it("sem argumentos não rebenta e nega", () => {
    expect(podeUsarFerramentasDeIA()).toBe(false);
  });
});
