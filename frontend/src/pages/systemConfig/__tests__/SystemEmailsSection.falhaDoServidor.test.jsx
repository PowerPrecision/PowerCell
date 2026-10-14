/**
 * «Emails do Sistema» — testar um remetente com o servidor a falhar (Lote 6, ponto 5).
 *
 * O `502` ao testar o SMTP de uma empresa deixava o resultado em `success: undefined` e sem
 * mensagem (o corpo é HTML, o `.json()` falhava e o `catch` engolia): um teste falhado que não
 * diz nada. Agora diz que o servidor não respondeu — e o ecrã continua utilizável.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import SystemEmailsSection from "../SystemEmailsSection";

const CONFIG = [{
  purpose: "DOCUMENTS", host: "smtp.domus.pt", port: 465, user: "geral@domus.pt",
  from_name: "Domus", from_email: "geral@domus.pt", is_active: true,
}];

function resposta({ ok = true, status = 200, corpo = null, html = false }) {
  return {
    ok, status,
    json: html ? () => Promise.reject(new SyntaxError("Unexpected token <")) : () => Promise.resolve(corpo),
  };
}

function ligar({ teste }) {
  globalThis.fetch = vi.fn((url) => {
    const endereco = String(url);
    if (endereco.endsWith("/system-emails")) return Promise.resolve(resposta({ corpo: CONFIG }));
    if (endereco.endsWith("/DOCUMENTS/test")) return typeof teste === "function" ? teste() : Promise.resolve(teste);
    return Promise.resolve(resposta({ corpo: {} }));
  });
}

async function testarODocumentos() {
  const u = userEvent.setup();
  render(<SystemEmailsSection token="t" />);
  await u.click(await screen.findByRole("button", { name: /Testar/i }));
}

const original = globalThis.fetch;
beforeEach(() => vi.clearAllMocks());
afterEach(() => { globalThis.fetch = original; });

describe("SystemEmailsSection — testar o remetente", () => {
  it("502 com corpo HTML: diz que o servidor não respondeu, em vez de um resultado mudo", async () => {
    ligar({ teste: resposta({ ok: false, status: 502, html: true }) });
    await testarODocumentos();

    expect(await screen.findByText(/servidor não respondeu \(erro 502\)/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Testar/i })).toBeEnabled();
  });

  it("ligação cortada: diz que não há ligação ao servidor", async () => {
    ligar({ teste: () => Promise.reject(new TypeError("Failed to fetch")) });
    await testarODocumentos();

    // `TypeError: Failed to fetch` é a forma do `fetch` (sem `response`): trata-se como rede.
    expect(await screen.findByText(/sem ligação ao servidor/i)).toBeInTheDocument();
  });

  it("falha da aplicação (success:false) mostra a mensagem do servidor", async () => {
    ligar({ teste: resposta({ corpo: { success: false, message: "Autenticação SMTP recusada." } }) });
    await testarODocumentos();

    expect(await screen.findByText("Autenticação SMTP recusada.")).toBeInTheDocument();
  });
});
