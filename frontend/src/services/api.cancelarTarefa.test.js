/**
 * Guarda sobre `services/api.js`: cancelar uma tarefa em background fala por Axios com
 * `skipErrorToast` — quem cancela diz o MOTIVO da recusa (400 «já terminou», 404) com o
 * `utils/cancelarTarefa.js`; o toast global por cima duplicava o 400 e o 404 não tinha nenhum.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const fonte = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "api.js"), "utf8");

describe("api.js — cancelBackgroundTask", () => {
  it("é um DELETE ao caminho certo, com skipErrorToast, sem fetch cru", () => {
    const inicio = fonte.indexOf("export const cancelBackgroundTask");
    expect(inicio).toBeGreaterThan(-1);
    const codigo = fonte.slice(inicio, fonte.indexOf(";", inicio) + 1);
    expect(codigo).toContain("api.delete(`/tasks/${taskId}/cancel`");
    expect(codigo).toContain("skipErrorToast: true");
    expect(codigo).not.toContain("fetch(");
  });
});
