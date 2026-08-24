/**
 * Unit tests for ProcessDetails hydration helpers.
 */
import {
  buildPersonalData,
  normalizeFormSlices,
  deriveProcessDetailsViewModel,
  resolveAssignedNames,
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

  // PACOTE FQ-2 — bugfix: AssignmentContextCard lia apenas consultor_names /
  // mediador_names; processos atribuídos via auto-atribuição na criação só
  // gravam os campos singulares (consultor_name / mediador_name) e
  // apareciam como "Não atribuído" apesar de terem consultor/intermediário.
  it("falls back to singular consultor_name/mediador_name when the arrays are missing", () => {
    const vm = deriveProcessDetailsViewModel(
      {
        id: "p2",
        status: "fase_1",
        consultor_name: "Ana Consultora",
        assigned_consultor_id: "u1",
        mediador_name: "Bruno Intermediário",
        assigned_mediador_id: "u2",
        financial_data: {},
        real_estate_data: {},
        titular2_data: {},
      },
      null,
    );
    expect(vm.process.consultor_names).toEqual(["Ana Consultora"]);
    expect(vm.process.mediador_names).toEqual(["Bruno Intermediário"]);
  });

  it("keeps the canonical arrays untouched when already populated", () => {
    const vm = deriveProcessDetailsViewModel(
      {
        id: "p3",
        status: "fase_1",
        consultor_names: ["Carla", "Duarte"],
        consultor_name: "Não deve aparecer",
        financial_data: {},
        real_estate_data: {},
        titular2_data: {},
      },
      null,
    );
    expect(vm.process.consultor_names).toEqual(["Carla", "Duarte"]);
  });

  it("leaves consultor_names/mediador_names undefined when nothing is assigned", () => {
    const vm = deriveProcessDetailsViewModel(
      {
        id: "p4",
        status: "fase_1",
        financial_data: {},
        real_estate_data: {},
        titular2_data: {},
      },
      null,
    );
    expect(vm.process.consultor_names).toBeUndefined();
    expect(vm.process.mediador_names).toBeUndefined();
  });
});

describe("resolveAssignedNames", () => {
  it("prefers already-resolved names over ids", () => {
    const usersById = new Map([["u1", { name: "Diana" }]]);
    expect(resolveAssignedNames(["Zeta"], ["u1"], usersById)).toEqual(["Zeta"]);
  });

  it("resolves names from ids via the users lookup when no names are available", () => {
    const usersById = new Map([
      ["u1", { name: "Diana" }],
      ["u2", { name: "Eduardo" }],
    ]);
    expect(resolveAssignedNames([], ["u1", "u2"], usersById)).toEqual(["Diana", "Eduardo"]);
  });

  it("accepts a single id string (assigned_consultor_id) instead of an array", () => {
    const usersById = new Map([["u2", { name: "Eduardo" }]]);
    expect(resolveAssignedNames(null, "u2", usersById)).toEqual(["Eduardo"]);
  });

  it("returns an empty array when there is nothing to resolve", () => {
    expect(resolveAssignedNames(null, null, new Map())).toEqual([]);
    expect(resolveAssignedNames([], [], new Map())).toEqual([]);
  });
});
