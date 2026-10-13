/**
 * Os dois sítios que enviam o magic link por email mostram a falha por
 * `mostrarFalhaDoEnvioDeEmail` (que troca o toast «retry agendado» por um de erro).
 *
 * Guarda sobre a FONTE (sem comentários: a explicação do defeito antigo não pode fazê-la falhar),
 * com contraprova: o `catch` de cada chamador tem mesmo a chamada. O comportamento do próprio
 * módulo está em `falhaNoEnvioDeEmail.test.js` e `TasksContext.emailFalhado.test.jsx`.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const AQUI = dirname(fileURLToPath(import.meta.url));
const semComentarios = (fonte) =>
  fonte.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");
const ler = (...p) => semComentarios(readFileSync(join(AQUI, "..", ...p), "utf8"));

const CHAMADORES = {
  "pages/ProcessDetails.js": ler("pages", "ProcessDetails.js"),
  "components/kanban/ProcessDetailsModal.jsx": ler("components", "kanban", "ProcessDetailsModal.jsx"),
};

describe.each(Object.entries(CHAMADORES))("%s", (_nome, fonte) => {
  it("importa o módulo", () => {
    expect(fonte).toMatch(/import \{ mostrarFalhaDoEnvioDeEmail \} from ['"][./]+utils\/falhaNoEnvioDeEmail['"]/);
  });

  it("o catch de sendMagicLinkEmail mostra a falha por ele", () => {
    const depoisDoEnvio = fonte.slice(fonte.indexOf("await sendMagicLinkEmail("));
    const catchDele = depoisDoEnvio.slice(depoisDoEnvio.indexOf("catch"), depoisDoEnvio.indexOf("catch") + 400);
    expect(catchDele).toContain("mostrarFalhaDoEnvioDeEmail(");
  });

  it("não deixou o aviso à mão, só para o 404 (o defeito antigo)", () => {
    const depoisDoEnvio = fonte.slice(fonte.indexOf("await sendMagicLinkEmail("));
    const catchDele = depoisDoEnvio.slice(depoisDoEnvio.indexOf("catch"), depoisDoEnvio.indexOf("catch") + 400);
    expect(catchDele).not.toContain("status === 404");
  });
});

describe("TasksContext", () => {
  it("regista os toasts de email e respeita os já substituídos", () => {
    const fonte = ler("contexts", "TasksContext.js");
    expect(fonte).toContain("registarToastDeEmail(id)");
    expect(fonte).toContain("toastDeEmailFoiSubstituido(id)");
    expect(fonte).toContain("esquecerToastDeEmail(id)");
  });
});
