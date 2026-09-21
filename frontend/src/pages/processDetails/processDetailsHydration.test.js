/**
 * Unit tests for ProcessDetails hydration helpers.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  buildPersonalData,
  normalizeFormSlices,
  deriveProcessDetailsViewModel,
  resolveAssignedNames,
} from "./processDetailsHydration.js";

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
    assert.strictEqual(personalData.nome_completo, "Ana");
    assert.strictEqual(personalData.email, "a@x.com");
    assert.strictEqual(personalData.nif, "123");
    assert.strictEqual(personalData.nif_hash, undefined);
    assert.strictEqual(resolvedEmail, "a@x.com");
  });

  it("falls back to process personal_data", () => {
    const { personalData } = buildPersonalData(
      { personal_data: { nome_completo: "Bob", email_hash: "h" } },
      null,
    );
    assert.strictEqual(personalData.nome_completo, "Bob");
    assert.strictEqual(personalData.email_hash, undefined);
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
    assert.strictEqual(out.personalData.sexo, "M");
    assert.strictEqual(out.personalData.estado_civil, "casado");
    assert.strictEqual(out.financialData.employment_type, "efetivo");
    assert.strictEqual(out.realEstateData.tipo_imovel, "apartamento");
    assert.strictEqual(out.titular2Data.estado_civil, "solteiro");
    assert.strictEqual(out.processPatch.client_email, "e@x.com");
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
    assert.strictEqual(vm.clientId, "c1");
    assert.strictEqual(vm.process.client_email, "a@x.com");
    assert.strictEqual(vm.process.client_phone, "900");
    assert.deepStrictEqual(vm.creditData, { bank: "x" });
    assert.strictEqual(vm.status, "fase_1");
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
    assert.deepStrictEqual(vm.process.consultor_names, ["Ana Consultora"]);
    assert.deepStrictEqual(vm.process.mediador_names, ["Bruno Intermediário"]);
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
    assert.deepStrictEqual(vm.process.consultor_names, ["Carla", "Duarte"]);
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
    assert.strictEqual(vm.process.consultor_names, undefined);
    assert.strictEqual(vm.process.mediador_names, undefined);
  });
});

describe("resolveAssignedNames", () => {
  it("prefers already-resolved names over ids", () => {
    const usersById = new Map([["u1", { name: "Diana" }]]);
    assert.deepStrictEqual(resolveAssignedNames(["Zeta"], ["u1"], usersById), ["Zeta"]);
  });

  it("resolves names from ids via the users lookup when no names are available", () => {
    const usersById = new Map([
      ["u1", { name: "Diana" }],
      ["u2", { name: "Eduardo" }],
    ]);
    assert.deepStrictEqual(resolveAssignedNames([], ["u1", "u2"], usersById), ["Diana", "Eduardo"]);
  });

  it("accepts a single id string (assigned_consultor_id) instead of an array", () => {
    const usersById = new Map([["u2", { name: "Eduardo" }]]);
    assert.deepStrictEqual(resolveAssignedNames(null, "u2", usersById), ["Eduardo"]);
  });

  it("returns an empty array when there is nothing to resolve", () => {
    assert.deepStrictEqual(resolveAssignedNames(null, null, new Map()), []);
    assert.deepStrictEqual(resolveAssignedNames([], [], new Map()), []);
  });
});
