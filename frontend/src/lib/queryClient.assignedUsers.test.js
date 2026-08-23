/**
 * Pacote FK — query keys de staff para atribuição.
 * Run: node --test src/lib/queryClient.assignedUsers.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const dir = dirname(fileURLToPath(import.meta.url));
const queryClientSource = readFileSync(join(dir, "queryClient.js"), "utf8");
const hookSource = readFileSync(
  join(dir, "../hooks/queries/useUsersQuery.js"),
  "utf8",
);
const processFiltersSource = readFileSync(
  join(dir, "../components/filters/ProcessFilters.jsx"),
  "utf8",
);
const clientFiltersSource = readFileSync(
  join(dir, "../components/filters/ClientFilters.jsx"),
  "utf8",
);

describe("Pacote FK filter query keys", () => {
  it("defines users.forAssignment in the official factory", () => {
    assert.match(queryClientSource, /forAssignment:\s*\(\)\s*=>/);
    assert.match(queryClientSource, /for_assignment:\s*true/);
  });

  it("useAssignmentUsersQuery calls GET /users with forAssignment", () => {
    assert.match(hookSource, /useAssignmentUsersQuery/);
    assert.match(hookSource, /queryKeys\.users\.forAssignment\(\)/);
    assert.match(hookSource, /forAssignment:\s*true/);
  });

  it("ProcessFilters exposes assigned-user dropdown and reset", () => {
    assert.match(processFiltersSource, /process-assigned-user-filter/);
    assert.match(processFiltersSource, /Limpar Filtros/);
    assert.match(processFiltersSource, /Atribuído a|Todos os utilizadores/);
  });

  it("ProcessFilters supports multi-select AND/OR assigned users", () => {
    assert.match(processFiltersSource, /process-assigned-logic/);
    assert.match(processFiltersSource, /ToggleGroup/);
    assert.match(processFiltersSource, /assignedUserIds/);
    assert.match(processFiltersSource, /assignedLogic/);
    assert.match(processFiltersSource, />\s*E\s*</);
    assert.match(processFiltersSource, />\s*OU\s*</);
  });

  it("ClientFilters is independent of process assignment fields", () => {
    assert.match(clientFiltersSource, /client-fonte-filter/);
    assert.match(clientFiltersSource, /client-tipo-filter/);
    assert.match(clientFiltersSource, /client-status-filter/);
    assert.match(clientFiltersSource, /Limpar Filtros/);
    assert.doesNotMatch(clientFiltersSource, /assignment_filter|indexacao_filter|assigned_consultor/);
  });
});
