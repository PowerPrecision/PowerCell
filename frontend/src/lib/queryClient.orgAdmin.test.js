/**
 * Pacote FJ — query keys org-admin vivem na factory oficial.
 * Run: node --test src/lib/queryClient.orgAdmin.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const dir = dirname(fileURLToPath(import.meta.url));
const queryClientSource = readFileSync(join(dir, "queryClient.js"), "utf8");
const companiesTabSource = readFileSync(
  join(dir, "../components/admin/CompaniesAdminTab.jsx"),
  "utf8",
);
const usersTabSource = readFileSync(
  join(dir, "../components/admin/UsersAccessAdminTab.jsx"),
  "utf8",
);
const systemAdminSource = readFileSync(
  join(dir, "../pages/SystemAdminPanel.jsx"),
  "utf8",
);

describe("Pacote FJ org-admin query factory", () => {
  it("defines orgAdmin keys in the official factory", () => {
    assert.match(queryClientSource, /orgAdmin:\s*\{/);
    assert.match(queryClientSource, /companiesAll:\s*\(\)\s*=>/);
    assert.match(queryClientSource, /companies:\s*\(search\)\s*=>/);
    assert.match(queryClientSource, /users:\s*\(\)\s*=>/);
    assert.match(queryClientSource, /ucrs:\s*\(\)\s*=>/);
    assert.match(queryClientSource, /ucrByUser:\s*\(userId\)\s*=>/);
  });

  it("CompaniesAdminTab and UsersAccessAdminTab use queryKeys.orgAdmin", () => {
    assert.match(companiesTabSource, /queryKeys\.orgAdmin\.companies\(/);
    assert.match(companiesTabSource, /queryKeys\.orgAdmin\.companiesAll\(/);
    assert.doesNotMatch(companiesTabSource, /\["org-admin-companies"/);
    assert.match(usersTabSource, /queryKeys\.orgAdmin\.users\(/);
    assert.match(usersTabSource, /queryKeys\.orgAdmin\.ucrs\(/);
    assert.match(usersTabSource, /queryKeys\.orgAdmin\.companies\(""\)/);
    assert.doesNotMatch(usersTabSource, /USERS_QUERY_KEY/);
    assert.doesNotMatch(usersTabSource, /UCR_QUERY_KEY/);
  });

  it("SystemAdminPanel uses CompaniesAdminTab and obsolete page is gone", () => {
    assert.match(systemAdminSource, /import CompaniesAdminTab from/);
    assert.doesNotMatch(systemAdminSource, /CompaniesManagementPage/);
    assert.equal(
      existsSync(join(dir, "../pages/CompaniesManagementPage.jsx")),
      false,
    );
  });
});
