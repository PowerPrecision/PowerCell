import { describe, it, expect } from "vitest";
import { etiquetaDaEmpresa, textoDaOpcaoDeUtilizador } from "./empresaDoUtilizador";

describe("etiquetaDaEmpresa", () => {
  it("usa a etiqueta que o servidor calculou", () => {
    expect(etiquetaDaEmpresa({ empresa_etiqueta: "Power · Precision" })).toBe("Power · Precision");
  });

  it("sem etiqueta junta a lista de nomes", () => {
    expect(etiquetaDaEmpresa({ empresas: ["Domus", "Precision"] })).toBe("Domus · Precision");
  });

  it("a etiqueta do servidor vence a lista", () => {
    expect(
      etiquetaDaEmpresa({ empresa_etiqueta: "Power", empresas: ["Outra"] }),
    ).toBe("Power");
  });

  it("NÃO infere a empresa do campo legado `company` (é um nome, não uma resposta do servidor)", () => {
    expect(etiquetaDaEmpresa({ company: "Power", name: "Ana" })).toBe("");
  });

  it.each([undefined, null, {}, { empresa_etiqueta: "  " }, { empresas: [] }, { empresas: [null, " "] }])(
    "sem dados (%j) devolve vazio e não rebenta",
    (valor) => {
      expect(etiquetaDaEmpresa(valor)).toBe("");
    },
  );
});

describe("textoDaOpcaoDeUtilizador", () => {
  it("«Nome (perfil) — Empresa»", () => {
    expect(
      textoDaOpcaoDeUtilizador({ name: "Ana", role: "consultor", empresa_etiqueta: "Precision" }),
    ).toBe("Ana (consultor) — Precision");
  });

  it("sem empresa fica como era", () => {
    expect(textoDaOpcaoDeUtilizador({ name: "Ana", role: "consultor" })).toBe("Ana (consultor)");
  });

  it("sem perfil quando se pede", () => {
    expect(
      textoDaOpcaoDeUtilizador({ name: "Rui", role: "parceiro", empresa_etiqueta: "Domus" }, { comPapel: false }),
    ).toBe("Rui — Domus");
  });
});
