/**
 * Pacote DW — helpers do painel de Organização.
 * Run: node --test src/utils/organizationAdmin.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  normalizeCompaniesPayload,
  normalizeRolesPayload,
  groupRolesByUserId,
  isCompanyActive,
  isUserActive,
  generateTempPassword,
} from "./organizationAdmin.js";

describe("normalizeCompaniesPayload", () => {
  it("aceita { companies: [...] }", () => {
    const list = normalizeCompaniesPayload({ companies: [{ id: "1" }] });
    assert.equal(list.length, 1);
    assert.equal(list[0].id, "1");
  });

  it("aceita array puro e payloads axios { data: { companies } }", () => {
    assert.equal(normalizeCompaniesPayload([{ id: "a" }]).length, 1);
    assert.equal(
      normalizeCompaniesPayload({ data: { companies: [{ id: "b" }] } })[0].id,
      "b",
    );
  });
});

describe("normalizeRolesPayload / groupRolesByUserId", () => {
  it("lê { roles: [...] }", () => {
    const roles = normalizeRolesPayload({
      roles: [{ id: "r1", user_id: "u1", role: "diretor" }],
    });
    assert.equal(roles.length, 1);
  });

  it("agrupa por user_id", () => {
    const grouped = groupRolesByUserId([
      { user_id: "u1", company_name: "A", role: "diretor" },
      { user_id: "u1", company_name: "B", role: "consultor" },
      { user_id: "u2", company_name: "A", role: "ceo" },
    ]);
    assert.equal(grouped.u1.length, 2);
    assert.equal(grouped.u2.length, 1);
  });
});

describe("isCompanyActive", () => {
  it("trata ausência de is_active como activa", () => {
    assert.equal(isCompanyActive({}), true);
    assert.equal(isCompanyActive({ is_active: true }), true);
    assert.equal(isCompanyActive({ is_active: false }), false);
  });
});

describe("isUserActive", () => {
  it("trata ausência de is_active como activo", () => {
    assert.equal(isUserActive({}), true);
    assert.equal(isUserActive({ is_active: true }), true);
    assert.equal(isUserActive({ is_active: false }), false);
  });
});

describe("generateTempPassword", () => {
  it("gera password com maiúscula, minúscula, dígito e símbolo", () => {
    const password = generateTempPassword();
    assert.equal(password.length, 12);
    assert.match(password, /[A-Z]/);
    assert.match(password, /[a-z]/);
    assert.match(password, /[0-9]/);
    assert.match(password, /[!@#$%^&*]/);
  });
});
