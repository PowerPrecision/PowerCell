/**
 * Pacote DP — mapeamento de perfis / UCRs para Área Pessoal e Header.
 * Run: node --test src/utils/userProfiles.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  buildProfileRoleTabs,
  buildUserProfileItems,
  collectUserRoles,
  getUserCompanyRecords,
} from "./userProfiles.js";

describe("getUserCompanyRecords", () => {
  it("lê companies, company_roles ou user_company_roles", () => {
    assert.deepEqual(getUserCompanyRecords({ companies: [{ role: "consultor" }] }).length, 1);
    assert.deepEqual(getUserCompanyRecords({ company_roles: [{ role: "diretor" }] }).length, 1);
    assert.deepEqual(getUserCompanyRecords({ user_company_roles: [{ role: "ceo" }] }).length, 1);
    assert.deepEqual(getUserCompanyRecords({}), []);
  });
});

describe("buildUserProfileItems", () => {
  it("mapeia UCRs com company_id camelCase e não descarta default", () => {
    const items = buildUserProfileItems({
      role: "consultor",
      companies: [
        { role: "Consultor", companyId: "default", companyName: "Power" },
        { role: "intermediario", company_id: "c2", company_name: "Precision" },
      ],
    });
    assert.equal(items.length, 2);
    assert.equal(items[0].role, "consultor");
    assert.equal(items[0].company_id, "default");
    assert.equal(items[1].role, "intermediario");
  });

  it("cai para additional_roles quando companies está vazio (bug Área Pessoal)", () => {
    const items = buildUserProfileItems({
      role: "consultor",
      additional_roles: ["intermediario", "diretor"],
      company: "Power Real Estate",
    });
    assert.equal(items.length, 3);
    assert.deepEqual(
      items.map((i) => i.role),
      ["consultor", "intermediario", "diretor"]
    );
    assert.ok(items.every((i) => i.company_id === "Power Real Estate"));
  });
});

describe("buildProfileRoleTabs", () => {
  it("gera uma tab ProfileRoleTab por perfil válido", () => {
    const tabs = buildProfileRoleTabs({
      role: "consultor",
      additional_roles: ["intermediario"],
      company: "Power",
    });
    assert.equal(tabs.length, 2);
    assert.equal(tabs[0].role, "consultor");
    assert.equal(tabs[0].companyId, "Power");
    assert.match(tabs[0].label, /Consultor/);
    assert.equal(tabs[1].role, "intermediario");
    assert.ok(tabs[0].id);
    assert.ok(tabs[1].id);
    assert.notEqual(tabs[0].id, tabs[1].id);
    assert.deepEqual(tabs[0].roleData, {
      display_name: "",
      professional_phone: "",
      job_title: "",
      signature: "",
    });
  });

  it("passa role_data do UCR para a tab", () => {
    const tabs = buildProfileRoleTabs({
      role: "consultor",
      companies: [{
        role: "consultor",
        company_id: "c1",
        company_name: "Power",
        display_name: "Ana Power",
        professional_phone: "910000000",
        job_title: "Consultora",
        signature: "<p>Ana</p>",
      }],
    });
    assert.equal(tabs[0].roleData.display_name, "Ana Power");
    assert.equal(tabs[0].roleData.professional_phone, "910000000");
    assert.equal(tabs[0].roleData.job_title, "Consultora");
    assert.equal(tabs[0].roleData.signature, "<p>Ana</p>");
  });
});

describe("collectUserRoles", () => {
  it("inclui roles só presentes em UCRs", () => {
    const roles = collectUserRoles({
      role: "consultor",
      additional_roles: [],
      companies: [{ role: "intermediario", company_id: "c1" }],
    });
    assert.ok(roles.includes("consultor"));
    assert.ok(roles.includes("intermediario"));
  });
});
