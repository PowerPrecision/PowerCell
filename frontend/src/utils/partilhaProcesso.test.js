import { describe, expect, it } from "vitest";

import { parceirosDoProcesso, podeRevogarPartilha, sePodeRevogar } from "./partilhaProcesso";

describe("podeRevogarPartilha", () => {
  it.each(["admin", "ceo", "diretor", " Diretor "])("%s pode", (papel) => {
    expect(podeRevogarPartilha(papel)).toBe(true);
  });
  it.each(["consultor", "intermediario", "administrativo", "indexacao", "parceiro", "", null, undefined])(
    "%s não pode",
    (papel) => {
      expect(podeRevogarPartilha(papel)).toBe(false);
    },
  );
});

describe("parceirosDoProcesso", () => {
  it("lê a forma REAL do registo", () => {
    const res = parceirosDoProcesso({
      partner_companies: [
        { company_id: "cmp-domus", company_name: "Domus", network_id: "grupo_domus", added_at: "2026-10-09T10:00:00Z", added_by: "u1" },
      ],
    });
    expect(res).toEqual([{ id: "cmp-domus", nome: "Domus", desde: "2026-10-09T10:00:00Z" }]);
  });

  it.each([undefined, null, {}, { partner_companies: null }, { partner_companies: {} }, { partner_companies: [] }])(
    "forma inesperada (%j) → sem parceiros (Array.isArray, nunca `|| []`)",
    (processo) => {
      expect(parceirosDoProcesso(processo)).toEqual([]);
    },
  );

  it("descarta entradas vazias e repetidas; o nome cai para o id", () => {
    const res = parceirosDoProcesso({
      partner_companies: [
        { company_id: "a", company_name: "A" },
        { company_id: "a", company_name: "outra A" },
        {},
        { company_id: "b" },
        { company_name: "Só nome" },
      ],
    });
    expect(res.map((p) => p.nome)).toEqual(["A", "b", "Só nome"]);
  });

  it("sem company_id não há como revogar", () => {
    expect(sePodeRevogar({ id: "x", nome: "X" })).toBe(true);
    expect(sePodeRevogar({ id: "", nome: "Só nome" })).toBe(false);
  });
});
