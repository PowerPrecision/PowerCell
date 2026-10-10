/**
 * O separador «Emails» do processo (Bloco 2, Lote 12) — montado pela primeira vez.
 *
 * Tinha doze `fetch` crus, sem `X-Company-Id` nem `X-Active-Role`: o servidor
 * decidia pelo cargo do JWT e não pelo perfil activo. E uma lista recusada
 * (403/404) via-se como «Nenhum email encontrado», que se lê como «não há
 * emails» — o degradado que não produz erro nenhum.
 */
import { render, screen, waitFor } from "@testing-library/react";
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
