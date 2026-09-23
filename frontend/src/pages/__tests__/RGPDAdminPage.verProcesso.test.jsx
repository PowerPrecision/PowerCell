/**
 * "Ver Processo" nos detalhes do RGPD levava ao Login.
 *
 * O CAMINHO ERA `/processes/${id}` — plural. As rotas declaradas em
 * `App.js` são `/process/:id` e `/processo/:id`; `/processes/:id` não
 * existe. E o catch-all é
 * `<Route path="*" element={<Navigate to="/login" replace />} />`, pelo que
 * QUALQUER caminho desconhecido termina no Login.
 *
 * Como o botão abre num separador novo (`window.open(..., "_blank")`), a
 * SPA arranca do zero e o sintoma parecia perda de sessão. Não era: a
 * sessão estava intacta, o caminho é que não existia. Um "s" a mais.
 *
 * O `process_id` também não era `undefined`: é o id canónico — o backend
 * resolve o processo com `find_one({"id": request["process_id"]})` — e o
 * botão só aparece quando o processo foi encontrado (`{process && …}`).
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ViewModal } from "../RGPDAdminPage";

const AQUI = dirname(fileURLToPath(import.meta.url));
const APP = readFileSync(join(AQUI, "..", "..", "App.js"), "utf8");

const rgpd = (overrides = {}) => ({
  id: "rgpd-1",
  process_id: "proc-abc-123",
  client_email: "ana@exemplo.pt",
  status: "signed",
  ...overrides,
});

const processo = { id: "proc-abc-123", client_name: "Ana Martins", process_number: 12 };

const props = (overrides = {}) => ({
  open: true,
  onClose: vi.fn(),
  rgpd: rgpd(),
  process: processo,
  ...overrides,
});

let abrir;

beforeEach(() => {
  abrir = vi.fn();
  vi.stubGlobal("open", abrir);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ViewModal — botão 'Ver Processo'", () => {
  it("abre o processo, não o Login", async () => {
    const utilizador = userEvent.setup();
    render(<ViewModal {...props()} />);

    await utilizador.click(screen.getByRole("button", { name: /Ver Processo/ }));

    expect(abrir).toHaveBeenCalledWith("/process/proc-abc-123", "_blank");
  });

  it("NÃO usa o caminho plural que não existe", async () => {
    // É este o erro concreto que punha o utilizador no Login.
    const utilizador = userEvent.setup();
    render(<ViewModal {...props()} />);

    await utilizador.click(screen.getByRole("button", { name: /Ver Processo/ }));

    const [caminho] = abrir.mock.calls[0];
    expect(caminho).not.toMatch(/^\/processes\//);
  });

  it("leva o id do processo, não o número", async () => {
    // `/process/:id` espera o uuid. O número do processo daria 404 → Login.
    const utilizador = userEvent.setup();
    render(<ViewModal {...props()} />);

    await utilizador.click(screen.getByRole("button", { name: /Ver Processo/ }));

    expect(abrir.mock.calls[0][0]).toContain("proc-abc-123");
    expect(abrir.mock.calls[0][0]).not.toContain("/12");
  });

  it("sem processo encontrado, o botão não existe", () => {
    // Um botão que levasse a `/process/undefined` também acabaria no Login.
    render(<ViewModal {...props({ process: null })} />);

    expect(screen.queryByRole("button", { name: /Ver Processo/ })).not.toBeInTheDocument();
  });
});

describe("Guarda: o caminho tem de existir no App.js", () => {
  it("a rota /process/:id está declarada", () => {
    // Se alguém renomear a rota, este teste cai junto com o anterior e diz
    // porquê — em vez de o utilizador descobrir no Login.
    expect(APP).toMatch(/path="\/process\/:id"/);
  });

  it("o catch-all continua a mandar para o Login", () => {
    // É esta regra que transforma um caminho errado num ecrã de sessão
    // expirada. Enquanto existir, um typo de rota é sempre este sintoma.
    expect(APP).toMatch(/path="\*"[\s\S]{0,80}Navigate to="\/login"/);
  });

  it("nenhum ecrã navega para /processes/ (rota inexistente)", () => {
    // Guarda de classe: apanha o mesmo erro em qualquer outro sítio.
    const FONTE = readFileSync(join(AQUI, "..", "RGPDAdminPage.js"), "utf8");
    const codigo = FONTE.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:])\/\/.*$/gm, "$1");

    expect(codigo).not.toMatch(/["'`]\/processes\//);
  });
});
