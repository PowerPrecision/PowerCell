/**
 * O separador «Emails» do processo (Bloco 2, Lote 12) — montado pela primeira vez.
 *
 * Tinha doze `fetch` crus, sem `X-Company-Id` nem `X-Active-Role`: o servidor
 * decidia pelo cargo do JWT e não pelo perfil activo. E uma lista recusada
 * (403/404) via-se como «Nenhum email encontrado», que se lê como «não há
 * emails» — o degradado que não produz erro nenhum.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import fs from "node:fs";
import path from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getProcessEmails: vi.fn(),
  getEmailStats: vi.fn(),
  getMonitoredEmails: vi.fn(),
  getEmailTemplates: vi.fn(),
  createEmail: vi.fn(),
  deleteEmail: vi.fn(),
  syncProcessEmails: vi.fn(),
  addMonitoredEmail: vi.fn(),
  removeMonitoredEmail: vi.fn(),
  applyEmailTemplate: vi.fn(),
  markEmail: vi.fn(),
  unmarkEmail: vi.fn(),
  searchEmailsToAssociate: vi.fn(),
  associateEmailToProcess: vi.fn(),
  disassociateEmailFromProcess: vi.fn(),
  getProcessEmailSyncStatus: vi.fn(),
  downloadWebmailAttachment: vi.fn(),
  readBlobErrorBody: vi.fn(async () => ({})),
}));
vi.mock("../../services/api", () => api);
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() } }));
vi.mock("../EmailViewerModal", () => ({ default: () => null }));

import EmailHistoryPanel from "../EmailHistoryPanel";

const EMAILS = [
  {
    id: "e1", subject: "Documentos do crédito", from_email: "joana@x.pt", to_emails: ["geral@p.pt"],
    direction: "received", sent_at: "2026-10-01T10:00:00Z", is_read: true, attachments: [],
  },
];
const STATS = { total: 41, sent: 10, received: 31, unread: 4, important: 2, starred: 1 };

const montar = () => render(<EmailHistoryPanel processId="p-1" clientEmail="joana@x.pt" clientName="Joana" token="t" />);

beforeEach(() => {
  vi.clearAllMocks();
  api.getProcessEmails.mockResolvedValue({ data: EMAILS });
  api.getEmailStats.mockResolvedValue({ data: STATS });
  api.getMonitoredEmails.mockResolvedValue({ data: { monitored_emails: [] } });
  api.getEmailTemplates.mockResolvedValue({ data: [] });
});

describe("EmailHistoryPanel", () => {
  it("lista os emails do processo", async () => {
    montar();
    expect(await screen.findByText("Documentos do crédito")).toBeInTheDocument();
    expect(api.getProcessEmails).toHaveBeenCalledWith("p-1", null, { skipErrorToast: true });
  });

  it("um 403 diz-se, em vez de parecer «sem emails»", async () => {
    api.getProcessEmails.mockRejectedValue({ response: { status: 403 } });
    montar();

    expect(await screen.findByTestId("emails-acesso-negado")).toHaveTextContent(/Não tem permissão/);
    expect(screen.queryByText("Nenhum email encontrado")).not.toBeInTheDocument();
  });

  it("um 404 (processo fora do âmbito) também", async () => {
    api.getProcessEmails.mockRejectedValue({ response: { status: 404 } });
    montar();
    expect(await screen.findByTestId("emails-acesso-negado")).toBeInTheDocument();
  });

  it("um erro de rede NÃO se faz passar por falta de permissão", async () => {
    api.getProcessEmails.mockRejectedValue(new Error("rede"));
    montar();
    await waitFor(() => expect(api.getProcessEmails).toHaveBeenCalled());
    await screen.findByText("Nenhum email encontrado");
    expect(screen.queryByTestId("emails-acesso-negado")).not.toBeInTheDocument();
  });

  it("se as estatísticas falham, a lista aparece na mesma", async () => {
    api.getEmailStats.mockRejectedValue({ response: { status: 500 } });
    montar();
    expect(await screen.findByText("Documentos do crédito")).toBeInTheDocument();
    expect(screen.queryByTestId("emails-acesso-negado")).not.toBeInTheDocument();
  });

  it("uma resposta que não é lista não rebenta", async () => {
    api.getProcessEmails.mockResolvedValue({ data: { erro: "x" } });
    montar();
    expect(await screen.findByText("Nenhum email encontrado")).toBeInTheDocument();
  });
});

describe("EmailHistoryPanel — sem registo manual de emails (Lote 7.2)", () => {
  it("não há botão «Novo» nem diálogo «Registar Email Enviado» (os enviados ficam na BD pelo envio real)", async () => {
    montar();
    await screen.findByText("Documentos do crédito");

    expect(screen.queryByRole("button", { name: /novo email|^novo$/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/registar email (enviado|recebido)/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /registar email/i })).not.toBeInTheDocument();
  });

  it("contraprova: o painel continua a oferecer as acções que ficam (sincronizar, associar, emails monitorizados)", async () => {
    montar();
    await screen.findByText("Documentos do crédito");

    expect(screen.getByRole("button", { name: /sync/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /associar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^emails$/i })).toBeInTheDocument();
  });

  it("a escrita manual saiu do componente (não há `createEmail` nem estado do diálogo)", () => {
    const codigo = fs.readFileSync(
      path.resolve(process.cwd(), "src/components/EmailHistoryPanel.js"), "utf-8",
    ).replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
    expect(codigo).not.toMatch(/createEmail/);
    expect(codigo).not.toMatch(/isCreateDialogOpen/);
    expect(codigo).not.toMatch(/Registar Email/);
    expect(codigo).toContain("getProcessEmails(");
  });
});

describe("EmailHistoryPanel — transporte", () => {
  const fonte = fs.readFileSync(
    path.resolve(process.cwd(), "src/components/EmailHistoryPanel.js"),
    "utf-8",
  ).replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

  it("nenhum `fetch` cru (perdia X-Company-Id e X-Active-Role)", () => {
    expect(fonte).not.toMatch(/\bfetch\(/);
    expect(fonte).not.toMatch(/API_URL/);
  });

  it("contraprova: o leitor leu mesmo o ficheiro", () => {
    expect(fonte).toContain("getProcessEmails(");
    expect(fonte.length).toBeGreaterThan(5000);
  });

  it("os anexos descarregam pelo endpoint de streaming, não pelo legado", () => {
    expect(fonte).toContain("downloadWebmailAttachment(");
    expect(fonte).not.toMatch(/\/attachments\/\$\{/);
  });
});


describe("EmailHistoryPanel — Desassociar (QA-8)", () => {
  async function abrirMenu() {
    montar();
    await screen.findByText("Documentos do crédito");
    await userEvent.click(screen.getByRole("button", { name: /acções do email/i }));
    return screen.findByRole("menuitem", { name: /desassociar/i });
  }

  it("o menu oferece «Desassociar» e ele retira o email do processo e refaz a lista", async () => {
    api.disassociateEmailFromProcess.mockResolvedValue({ data: { success: true } });
    const item = await abrirMenu();
    await userEvent.click(item);

    await waitFor(() => expect(api.disassociateEmailFromProcess).toHaveBeenCalledWith("e1"));
    // refaz a lista: o email sai da vista do processo
    await waitFor(() => expect(api.getProcessEmails.mock.calls.length).toBeGreaterThan(1));
  });

  it("uma recusa do servidor diz-se e não refaz a lista", async () => {
    api.disassociateEmailFromProcess.mockRejectedValue({ response: { data: { detail: "Processo fechado" } } });
    const item = await abrirMenu();
    const chamadasAntes = api.getProcessEmails.mock.calls.length;
    await userEvent.click(item);

    await waitFor(() => expect(api.disassociateEmailFromProcess).toHaveBeenCalled());
    expect(api.getProcessEmails.mock.calls.length).toBe(chamadasAntes);
  });
});
