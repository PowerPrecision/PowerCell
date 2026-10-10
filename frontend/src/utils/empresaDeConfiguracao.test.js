import { describe, expect, it } from "vitest";

import {
  EMPRESA_GLOBAL,
  deveMostrarSeletorDeEmpresa,
  empresaEmVigor,
  normalizarEmpresas,
} from "./empresaDeConfiguracao";

const ADMIN = [
  { company_id: "default", company_name: "Global (Padrão)" },
  { company_id: "cmp-power", company_name: "Power Real Estate" },
  { company_id: "cmp-domus", company_name: "Domus" },
];
const CEO_DA_ILHA = [{ company_id: "cmp-domus", company_name: "Domus" }];

describe("normalizarEmpresas", () => {
  it("lê a forma REAL do servidor ({companies, total})", () => {
    expect(normalizarEmpresas({ companies: ADMIN, total: 3 })).toEqual(ADMIN);
  });

  it.each([undefined, null, {}, { companies: null }, { companies: {} }, []])(
    "uma forma inesperada (%j) dá lista vazia — Array.isArray, nunca `|| []`",
    (forma) => {
      expect(normalizarEmpresas(forma)).toEqual([]);
    },
  );

  it("descarta entradas sem id e duplicados; o nome cai para o id", () => {
    const res = normalizarEmpresas({
      companies: [
        { company_id: "a", company_name: "A" },
        { company_id: "a", company_name: "outra A" },
        { company_name: "sem id" },
        { company_id: "b" },
      ],
    });
    expect(res).toEqual([
      { company_id: "a", company_name: "A" },
      { company_id: "b", company_name: "b" },
    ]);
  });
});

describe("deveMostrarSeletorDeEmpresa", () => {
  it("só com mais do que uma empresa", () => {
    expect(deveMostrarSeletorDeEmpresa(ADMIN)).toBe(true);
    expect(deveMostrarSeletorDeEmpresa(CEO_DA_ILHA)).toBe(false);
    expect(deveMostrarSeletorDeEmpresa([])).toBe(false);
    expect(deveMostrarSeletorDeEmpresa(undefined)).toBe(false);
  });
});

describe("empresaEmVigor", () => {
  it("a escolha explícita vence a empresa activa", () => {
    expect(
      empresaEmVigor({ escolhida: "cmp-domus", activa: "cmp-power", empresas: ADMIN }),
    ).toBe("cmp-domus");
  });

  it("uma escolha que já não está na lista é ignorada", () => {
    expect(
      empresaEmVigor({ escolhida: "cmp-fora", activa: "cmp-power", empresas: ADMIN }),
    ).toBe("cmp-power");
  });

  it("a activa vence a omissão", () => {
    expect(empresaEmVigor({ escolhida: null, activa: "cmp-power", empresas: ADMIN })).toBe("cmp-power");
  });

  it("sem empresa activa vale a global, quando o servidor a oferece", () => {
    expect(empresaEmVigor({ escolhida: null, activa: null, empresas: ADMIN })).toBe(EMPRESA_GLOBAL);
  });

  it("o CEO da ilha NÃO tem a global: abre na empresa dele, não num 403", () => {
    expect(empresaEmVigor({ escolhida: null, activa: null, empresas: CEO_DA_ILHA })).toBe("cmp-domus");
    expect(empresaEmVigor({ escolhida: null, activa: "default", empresas: CEO_DA_ILHA })).toBe("cmp-domus");
  });

  it("sem lista (pedido falhado) fica o comportamento de sempre", () => {
    expect(empresaEmVigor({ escolhida: null, activa: "cmp-power", empresas: [] })).toBe("cmp-power");
    expect(empresaEmVigor({ escolhida: null, activa: null, empresas: [] })).toBe(EMPRESA_GLOBAL);
    expect(empresaEmVigor({ escolhida: "x", activa: null, empresas: undefined })).toBe(EMPRESA_GLOBAL);
  });
});
