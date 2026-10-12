/**
 * Guarda sobre o código de `services/api.js`: «Repor ao Modelo» fala com o servidor SÓ por
 * Axios e com `skipErrorToast` — o diálogo mostra o erro no sítio (password errada, bloqueio,
 * processos em fases em uso); um toast global por cima escondia o motivo.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const fonte = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "api.js"), "utf8");

function linhaDe(nome) {
  const inicio = fonte.indexOf(`export const ${nome}`);
  expect(inicio, `${nome} existe`).toBeGreaterThan(-1);
  return fonte.slice(inicio, fonte.indexOf(";", inicio) + 1);
}

describe("api.js — repor ao modelo", () => {
  it.each([
    ["reporWorkflowAoModelo", "/admin/workflow-statuses/reset-to-model"],
    ["reporFormularioAoModelo", "/admin/form-config/reset-to-model"],
  ])("%s é um POST ao caminho certo, com a password no corpo e skipErrorToast", (nome, caminho) => {
    const codigo = linhaDe(nome);
    expect(codigo).toContain(`api.post("${caminho}"`);
    expect(codigo).toContain("{ password }");
    expect(codigo).toContain("skipErrorToast: true");
    expect(codigo).not.toContain("fetch(");
  });
});
