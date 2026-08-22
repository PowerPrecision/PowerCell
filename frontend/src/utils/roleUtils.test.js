/**
 * Pacote DT — filtro de staff para atribuições.
 * Run: node --test src/utils/roleUtils.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  ASSIGNMENT_STAFF_ROLES,
  CONSULTOR_ASSIGNMENT_ROLES,
  EXCLUDED_ASSIGNMENT_ROLES,
  ROLE_LABELS,
  ROLE_SHORT_LABELS,
  UCR_ASSIGNABLE_ROLES,
  filterAssignmentStaff,
  isAssignmentEligibleUser,
  canAccessOrgAdmin,
  canAccessByEffectiveRole,
  hasNoClientPortfolio,
  NO_CLIENT_PORTFOLIO_ROLES,
} from "./roleUtils.js";

describe("assignment staff constants", () => {
  it("allows consultor, intermediario, diretor and ceo", () => {
    for (const role of ["consultor", "intermediario", "diretor", "ceo"]) {
      assert.ok(ASSIGNMENT_STAFF_ROLES.includes(role), role);
    }
  });

  it("excludes admin and indexacao from assignment lists", () => {
    assert.ok(EXCLUDED_ASSIGNMENT_ROLES.includes("admin"));
    assert.ok(EXCLUDED_ASSIGNMENT_ROLES.includes("indexacao"));
    assert.equal(CONSULTOR_ASSIGNMENT_ROLES.includes("admin"), false);
  });
});

describe("isAssignmentEligibleUser / filterAssignmentStaff", () => {
  it("keeps consultor diretor ceo intermediario", () => {
    assert.equal(isAssignmentEligibleUser({ role: "consultor" }), true);
    assert.equal(isAssignmentEligibleUser({ role: "diretor" }), true);
    assert.equal(isAssignmentEligibleUser({ role: "ceo" }), true);
    assert.equal(isAssignmentEligibleUser({ role: "intermediario" }), true);
  });

  it("drops admin and indexacao even with extra consultor role", () => {
    assert.equal(isAssignmentEligibleUser({ role: "admin" }), false);
    assert.equal(
      isAssignmentEligibleUser({ role: "admin", additional_roles: ["consultor"] }),
      false,
    );
    assert.equal(isAssignmentEligibleUser({ role: "indexacao" }), false);
    assert.equal(isAssignmentEligibleUser({ role: "index" }), false);
  });

  it("filters a mixed staff list", () => {
    const filtered = filterAssignmentStaff([
      { id: "a", role: "admin", name: "Admin" },
      { id: "i", role: "indexacao", name: "Index" },
      { id: "c", role: "consultor", name: "Ana" },
      { id: "p", role: "parceiro", name: "Parceiro" },
    ]);
    assert.deepEqual(filtered.map((u) => u.id), ["c"]);
  });
});

describe("Pacote DW — org admin + UCR roles", () => {
  it("UCR_ASSIGNABLE_ROLES includes Index, administrativo and parceiro", () => {
    assert.deepEqual(UCR_ASSIGNABLE_ROLES, [
      "admin",
      "ceo",
      "diretor",
      "administrativo",
      "consultor",
      "intermediario",
      "indexacao",
      "parceiro",
    ]);
  });

  it("does not use the non-canonical Adm. label for administrativo", () => {
    assert.equal(ROLE_SHORT_LABELS.admin, "Admin");
    assert.equal(ROLE_SHORT_LABELS.administrativo, "Administrativo");
    assert.equal(ROLE_SHORT_LABELS.parceiro, "Parceiro");
    assert.notEqual(ROLE_SHORT_LABELS.administrativo, ROLE_SHORT_LABELS.admin);
    assert.equal(ROLE_LABELS.admin, "Administrador do Sistema");
    assert.equal(ROLE_LABELS.administrativo, "Apoio Administrativo");
    assert.equal(ROLE_LABELS.parceiro, "Parceiro");
    assert.equal(UCR_ASSIGNABLE_ROLES.includes("adm"), false);
  });

  it("canAccessByEffectiveRole ignores JWT additional_roles (Pacote FH / C3)", () => {
    assert.equal(canAccessByEffectiveRole("admin", ["admin", "ceo"]), true);
    assert.equal(canAccessByEffectiveRole("CEO", ["admin", "ceo"]), true);
    assert.equal(canAccessByEffectiveRole("consultor", ["admin", "ceo"]), false);
    assert.equal(canAccessByEffectiveRole("consultor", ["consultor", "intermediario"]), true);
    assert.equal(canAccessByEffectiveRole("indexacao", ["admin", "indexacao"]), true);
    assert.equal(canAccessByEffectiveRole(null, ["admin"]), false);
    assert.equal(canAccessByEffectiveRole("consultor", []), true);
  });

  it("canAccessOrgAdmin only when activeRole is admin or ceo", () => {
    assert.equal(canAccessOrgAdmin("admin"), true);
    assert.equal(canAccessOrgAdmin("CEO"), true);
    assert.equal(canAccessOrgAdmin("diretor"), false);
    assert.equal(canAccessOrgAdmin("consultor"), false);
    assert.equal(canAccessOrgAdmin(null), false);
  });

  it("hasNoClientPortfolio for admin, ceo and indexacao", () => {
    assert.deepEqual(NO_CLIENT_PORTFOLIO_ROLES, ["admin", "ceo", "indexacao"]);
    assert.equal(hasNoClientPortfolio("admin"), true);
    assert.equal(hasNoClientPortfolio("CEO"), true);
    assert.equal(hasNoClientPortfolio("indexacao"), true);
    assert.equal(hasNoClientPortfolio("consultor"), false);
    assert.equal(hasNoClientPortfolio("diretor"), false);
    assert.equal(hasNoClientPortfolio("intermediario"), false);
    assert.equal(hasNoClientPortfolio(null), false);
  });
});
