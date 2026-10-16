import { describe, expect, it } from "vitest";

import { destinoDoResultado, etiquetaDaEmpresa, exigeTrocaDeEmpresa } from "./pesquisaGlobalEmpresa";

const DE_OUTRA = { id: "c1", empresa: { company_id: "cmp-precision", company_name: "Precision Crédito", e_de_outra_rede: true } };
const DA_MINHA = { id: "c2", empresa: { company_id: "cmp-domus", company_name: "Domus", e_de_outra_rede: false } };

describe("etiquetaDaEmpresa", () => {
  it("devolve o nome que o servidor mandou", () => {
    expect(etiquetaDaEmpresa(DE_OUTRA)).toBe("Precision Crédito");
    expect(etiquetaDaEmpresa(DA_MINHA)).toBe("Domus");
  });

  it.each([[undefined], [null], [{}], [{ empresa: null }], [{ empresa: {} }], [{ empresa: { company_name: "  " } }], [{ empresa: { company_name: 7 } }]])(
    "sem nome utilizável não inventa uma etiqueta (%j)",
    (dados) => {
      expect(etiquetaDaEmpresa(dados)).toBeNull();
    },
  );
});

describe("exigeTrocaDeEmpresa", () => {
  it("só quando o servidor o afirma e diz para que empresa", () => {
    expect(exigeTrocaDeEmpresa(DE_OUTRA)).toBe(true);
    expect(exigeTrocaDeEmpresa(DA_MINHA)).toBe(false);
  });

  it("um campo em falta nunca vira «trocar de empresa»", () => {
    expect(exigeTrocaDeEmpresa({ empresa: { e_de_outra_rede: true } })).toBe(false);
    expect(exigeTrocaDeEmpresa({ empresa: { e_de_outra_rede: "true", company_id: "x" } })).toBe(false);
    expect(exigeTrocaDeEmpresa({})).toBe(false);
    expect(exigeTrocaDeEmpresa(null)).toBe(false);
  });
});

describe("destinoDoResultado", () => {
  it("processo, cliente e tarefa", () => {
    expect(destinoDoResultado("process", { id: "p1" })).toBe("/processo/p1");
    expect(destinoDoResultado("client", { id: "c1" })).toBe("/cliente/c1");
    expect(destinoDoResultado("task", { id: "t1" })).toBe("/pendentes");
  });

  it("um cliente vai SEMPRE para a ficha, mesmo com processo", () => {
    expect(destinoDoResultado("client", { id: "c1", has_process: true, first_process_id: "p9" })).toBe("/cliente/c1");
  });

  it("sem id ou com tipo desconhecido não há destino", () => {
    expect(destinoDoResultado("process", {})).toBeNull();
    expect(destinoDoResultado("client", null)).toBeNull();
    expect(destinoDoResultado("outro", { id: "x" })).toBeNull();
  });
});
