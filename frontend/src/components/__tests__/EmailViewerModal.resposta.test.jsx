/**
 * Responder a um email pelo visualizador (Lote 7.2): a resposta vai pelo cliente Axios.
 *
 * Era um `fetch` cru que só levava o `X-Company-Id` lido à mão do sessionStorage e perdia o
 * `X-Active-Role`: o servidor escolhia conta e assinatura sem saber o perfil activo — a
 * família do incidente de 2026-09-21. O teste monta o componente REAL e afirma os parâmetros
 * que SAEM (o que o `sendWebmailEmail` recebe), não o resultado.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import fs from "node:fs";
import path from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  sendWebmailEmail: vi.fn(),
  cancelEmailSend: vi.fn(),
}));
vi.mock("../../services/api", () => api);
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

import EmailViewerModal from "../EmailViewerModal";

const EMAIL = {
  id: "e1", subject: "Documentos", from_email: "cliente@x.pt", to_emails: ["geral@p.pt"],
  body: "Olá", direction: "received", process_id: "p-7", sent_at: "2026-10-01T10:00:00Z", attachments: [],
};

const montar = () => render(
  <EmailViewerModal isOpen onClose={() => {}} emails={[EMAIL]} selectedEmailId="e1" token="t" clientName="Joana" />,
);

beforeEach(() => {
  vi.clearAllMocks();
  globalThis.fetch = vi.fn(() => { throw new Error("fetch cru não devia ser usado para enviar"); });
});

describe("EmailViewerModal — responder", () => {
  async function responder(texto = "Obrigado!") {
    montar();
    fireEvent.click((await screen.findAllByRole("button", { name: /responder/i }))[0]);
    fireEvent.change(await screen.findByPlaceholderText(/escreva a sua resposta/i), { target: { value: texto } });
    fireEvent.click(screen.getByRole("button", { name: /enviar/i }));
  }

  it("envia pelo cliente Axios, com o processo e a conta pessoal", async () => {
    api.sendWebmailEmail.mockResolvedValue({ data: { success: true } });
    await responder();

    await waitFor(() => expect(api.sendWebmailEmail).toHaveBeenCalledTimes(1));
    const [payload, conta] = api.sendWebmailEmail.mock.calls[0];
    expect(conta).toBe("personal");
    expect(payload).toMatchObject({
      to_emails: ["cliente@x.pt"], body: "Obrigado!", process_id: "p-7", from_box: "personal",
    });
    expect(payload.subject).toMatch(/^RE: Documentos/);
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("o motivo do servidor chega ao utilizador (403 de configuração em falta)", async () => {
    api.sendWebmailEmail.mockRejectedValue({ response: { data: { detail: "Configuração de email pessoal não encontrada." } } });
    await responder();

    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(toast.error.mock.calls[0][0]).toBe("Configuração de email pessoal não encontrada.");
  });

  it("«Desfazer» cancela pelo cliente Axios e repõe a caixa de resposta", async () => {
    api.sendWebmailEmail.mockResolvedValue({ data: { queued: true, send_id: "s-1", undo_window_seconds: 10 } });
    api.cancelEmailSend.mockResolvedValue({ data: {} });
    await responder();

    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    const desfazer = toast.success.mock.calls[0][1].action.onClick;
    await act(async () => { await desfazer(); });

    expect(api.cancelEmailSend).toHaveBeenCalledWith("s-1");
    await waitFor(() => expect(toast.success.mock.calls.at(-1)[0]).toMatch(/envio cancelado/i));
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});

describe("EmailViewerModal — transporte do envio", () => {
  it("nenhum `fetch` para /emails/send nem /cancel-send", () => {
    const fonte = fs.readFileSync(path.resolve(process.cwd(), "src/components/EmailViewerModal.js"), "utf-8")
      .replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
    expect(fonte).not.toMatch(/emails\/send/);
    expect(fonte).not.toMatch(/cancel-send/);
    expect(fonte).toContain("sendWebmailEmail(");
  });
});
