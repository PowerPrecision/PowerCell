import { describe, expect, it } from "vitest";

import { HREF_DA_SUPERVISAO_DO_INDEX, redeTemIndex, retirarModuloIndex } from "./capacidadesDaRede";

const NAV = {
  main: [{ label: "Dashboard", href: "/staff" }],
  groups: [
    { id: "g1", items: [{ label: "Supervisão do Index", href: "/index" }, { label: "Calendário", href: "/calendario" }] },
    { id: "g2", items: [{ label: "Pesquisa Avançada", href: "/index/pesquisa" }] },
  ],
};

describe("redeTemIndex — só um false ESTRITO nega o módulo", () => {
  it("false nega", () => {
    expect(redeTemIndex({ capabilities: { has_index: false } })).toBe(false);
  });

  it.each([
    [undefined],
    [{}],
    [{ capabilities: {} }],
    [{ capabilities: { has_index: true } }],
    [{ capabilities: { has_index: null } }],
    [{ capabilities: { has_index: 0 } }],
    [{ capabilities: { has_index: "false" } }],
  ])("sem contrato claro (%j) o módulo fica à vista", (user) => {
    expect(redeTemIndex(user)).toBe(true);
  });
});

describe("retirarModuloIndex", () => {
  it("rede com Index: o mesmo objecto, intacto", () => {
    expect(retirarModuloIndex(NAV, { capabilities: { has_index: true } })).toBe(NAV);
  });

  it("rede sem Index: sai a supervisão — e SÓ ela", () => {
    const r = retirarModuloIndex(NAV, { capabilities: { has_index: false } });
    expect(r.groups[0].items.map((i) => i.href)).toEqual(["/calendario"]);
    expect(r.groups[1].items.map((i) => i.href)).toEqual(["/index/pesquisa"]);
    expect(r.main).toEqual(NAV.main);
  });

  it("não muda o original", () => {
    retirarModuloIndex(NAV, { capabilities: { has_index: false } });
    expect(NAV.groups[0].items.map((i) => i.href)).toContain(HREF_DA_SUPERVISAO_DO_INDEX);
  });

  it("um menu inválido não rebenta", () => {
    expect(retirarModuloIndex(undefined, { capabilities: { has_index: false } })).toBeUndefined();
    expect(retirarModuloIndex({}, { capabilities: { has_index: false } })).toEqual({});
  });
});
