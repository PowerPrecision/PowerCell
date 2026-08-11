/**
 * Unit tests for ProcessDetails hydration helpers.
 */
import {
  buildPersonalData,
  normalizeFormSlices,
  deriveProcessDetailsViewModel,
} from "../../pages/processDetails/processDetailsHydration";

describe("buildPersonalData", () => {
  it("prefers client as source of truth", () => {
    const { personalData, resolvedEmail } = buildPersonalData(
      { client_name: "Proc", client_email: "p@x.com" },
      {
        nome: "Ana",
        contacto: { email: "a@x.com", telefone: "91" },
        dados_pessoais: { nif: "123", nif_hash: "x" },
      },
    );
    expect(personalData.nome_completo).toBe("Ana");
    expect(personalData.email).toBe("a@x.com");
    expect(personalData.nif).toBe("123");
    expect(personalData.nif_hash).toBeUndefined();
    expect(resolvedEmail).toBe("a@x.com");
  });

  it("falls back to process personal_data", () => {
    const { personalData } = buildPersonalData(
      { personal_data: { nome_completo: "Bob", email_hash: "h" } },
      null,
    );
    expect(personalData.nome_completo).toBe("Bob");
    expect(personalData.email_hash).toBeUndefined();
  });
});

describe("normalizeFormSlices", () => {
  it("maps display labels to internal keys", () => {
    const out = normalizeFormSlices(
      {
        personal_data: { sexo: "Masculino", email: "e@x.com" },
        financial_data: { employment_type: "Efetivo" },
        real_estate_data: { tipo_imovel: "Apartamento" },
        titular2_data: { estado_civil: "Solteiro(a)" },
      },
      { sexo: "Masculino", estado_civil: "Casado(a)" },
      { employment_type: "Efetivo" },
      { tipo_imovel: "Apartamento" },
      { estado_civil: "Solteiro(a)" },
    );
    expect(out.personalData.sexo).toBe("M");
    expect(out.personalData.estado_civil).toBe("casado");
    expect(out.financialData.employment_type).toBe("efetivo");
    expect(out.realEstateData.tipo_imovel).toBe("apartamento");
    expect(out.titular2Data.estado_civil).toBe("solteiro");
    expect(out.processPatch.client_email).toBe("e@x.com");
  });
});

describe("deriveProcessDetailsViewModel", () => {
  it("merges client contacts into process when missing", () => {
    const vm = deriveProcessDetailsViewModel(
      {
        id: "p1",
        client_id: "c1",
        status: "fase_1",
        client_email: "",
        client_phone: "",
        financial_data: {},
        real_estate_data: {},
        credit_data: { bank: "x" },
        titular2_data: {},
      },
      {
        nome: "Ana",
        contacto: { email: "a@x.com", telefone: "900" },
        dados_pessoais: {},
      },
    );
    expect(vm.clientId).toBe("c1");
    expect(vm.process.client_email).toBe("a@x.com");
    expect(vm.process.client_phone).toBe("900");
    expect(vm.creditData).toEqual({ bank: "x" });
    expect(vm.status).toBe("fase_1");
  });
});
