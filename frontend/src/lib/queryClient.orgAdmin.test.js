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
    // Ponto 11 — a PÁGINA entra na chave. Sem ela o TanStack servia a
    // página anterior enquanto o pedido novo não chegava.
    assert.match(queryClientSource, /companies:\s*\(search,\s*page\)\s*=>/);
    assert.match(queryClientSource, /users:\s*\(\)\s*=>/);
    assert.match(
      queryClientSource,
      /usersPaginated:\s*\(search,\s*page,\s*companyId\)\s*=>/,
    );
    assert.match(queryClientSource, /ucrs:\s*\(\)\s*=>/);
    assert.match(queryClientSource, /ucrByUser:\s*\(userId\)\s*=>/);
  });

  it("CompaniesAdminTab and UsersAccessAdminTab use queryKeys.orgAdmin", () => {
    assert.match(companiesTabSource, /queryKeys\.orgAdmin\.companies\(/);
    assert.match(companiesTabSource, /queryKeys\.orgAdmin\.companiesAll\(/);
    assert.doesNotMatch(companiesTabSource, /\["org-admin-companies"/);
    assert.match(usersTabSource, /queryKeys\.orgAdmin\.users\(/);
    assert.match(usersTabSource, /queryKeys\.orgAdmin\.ucrs\(/);
    // ERA `companies("")` — e essa asserção CRISTALIZAVA o defeito: é a mesma
    // chave que `companies("", 1)` do separador Empresas, que lá escreve
    // `{empresas, total}` em vez de um array. Os dois separadores vivem no
    // mesmo QueryClient e o segundo a montar recebia a forma do primeiro:
    // `TypeError: companies is not iterable` em produção.
    //
    // Chave própria para o selector, e a guarda passou a afirmar as DUAS
    // coisas — que a nova é usada e que a antiga não voltou.
    assert.match(queryClientSource, /companiesSelector:\s*\(\)\s*=>/);
    assert.match(usersTabSource, /queryKeys\.orgAdmin\.companiesSelector\(\)/);
    assert.doesNotMatch(
      usersTabSource,
      /queryKeys\.orgAdmin\.companies\(/,
      "o selector não pode voltar a partilhar a chave da lista paginada",
    );
    // E a chave própria tem de DESCENDER de `companiesAll()`, senão a
    // invalidação por prefixo do CRUD de empresas deixa de a refrescar.
    assert.match(
      queryClientSource,
      /companiesSelector:\s*\(\)\s*=>\s*\[\.\.\.queryKeys\.orgAdmin\.companiesAll\(\)/,
    );
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
