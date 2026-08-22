/**
 * Pacote FH — ProtectedRoute / AuthContext usam cargo efetivo UCR.
 * Run: node --test src/App.ucr.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const dir = dirname(fileURLToPath(import.meta.url));
const appSource = readFileSync(join(dir, "App.js"), "utf8");
const authSource = readFileSync(join(dir, "contexts/AuthContext.js"), "utf8");
const webmailSource = readFileSync(join(dir, "pages/WebmailPage.jsx"), "utf8");

describe("Pacote FH frontend UCR gates", () => {
  it("ProtectedRoute gates on effectiveRole via canAccessByEffectiveRole", () => {
    assert.match(appSource, /canAccessByEffectiveRole\(effectiveRole, allowedRoles\)/);
    assert.doesNotMatch(
      appSource,
      /allowedRoles\.some\(r => hasRole\(user, r\)\)/,
    );
  });

  it("AuthContext persists UCR on /auth/active-company with role", () => {
    assert.match(authSource, /\/auth\/active-company/);
    assert.match(authSource, /company_id: companyId, role/);
    assert.doesNotMatch(authSource, /\/admin\/user-company-roles\/set-active-company/);
  });

  it("Webmail shared box uses effectiveRole not JWT hasAnyRole", () => {
    assert.match(webmailSource, /effectiveRole === "indexacao"/);
    assert.doesNotMatch(
      webmailSource,
      /hasAnyRole\(user, \['admin', 'ceo', 'diretor'\]\)/,
    );
    assert.doesNotMatch(
      webmailSource,
      /hasAnyRole\(user, \['admin', 'ceo', 'diretor', 'administrativo'\]\)/,
    );
  });
});
