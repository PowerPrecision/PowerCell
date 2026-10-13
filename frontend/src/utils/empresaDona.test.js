import { describe, it, expect } from "vitest";
import { etiquetaDaEmpresaDona } from "./empresaDona";

describe("etiquetaDaEmpresaDona", () => {
  it("devolve o nome e o título da empresa dona", () => {
    const e = etiquetaDaEmpresaDona({ company_name: "Power Real Estate", e_de_outra_rede: false });
    expect(e.nome).toBe("Power Real Estate");
    expect(e.partilhado).toBe(false);
    expect(e.titulo).toBe("Empresa dona do processo: Power Real Estate");
  });

  it("marca como partilhado só com e_de_outra_rede === true", () => {
    expect(etiquetaDaEmpresaDona({ company_name: "Domus", e_de_outra_rede: true }).partilhado).toBe(true);
    for (const valor of [undefined, null, "true", 1, "sim"]) {
      expect(etiquetaDaEmpresaDona({ company_name: "Domus", e_de_outra_rede: valor }).partilhado).toBe(false);
    }
  });

  it("sem nome não há etiqueta", () => {
    for (const v of [null, undefined, {}, { company_name: "" }, { company_name: "   " }, { company_name: 5 }, "x", []]) {
      expect(etiquetaDaEmpresaDona(v)).toBeNull();
    }
  });

  it("apara o nome", () => {
    expect(etiquetaDaEmpresaDona({ company_name: "  Domus " }).nome).toBe("Domus");
  });
});
