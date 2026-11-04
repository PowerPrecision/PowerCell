/**
 * Responder a partir do visualizador do processo (Flavio, 2026-11-04, pergunta 10a).
 *
 * Havia aqui uma caixa de resposta própria: texto simples, sem anexos nem Cc, sem
 * In-Reply-To (o fio partia-se) e a responder ao remetente mesmo quando o email tinha
 * sido enviado por nós. Agora «Responder» e «Responder a todos» entregam o email a quem
 * monta o visualizador, que abre o compositor do Webmail.
 */
import { fireEvent, render, screen } from "@testing-library/react";
import fs from "node:fs";
import path from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  downloadEmailAttachment: vi.fn(),
  getEmailAttachmentPreview: vi.fn(),
  archiveEmailAttachment: vi.fn(),
}));
vi.mock("../../services/api", () => api);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import EmailViewerModal from "../EmailViewerModal";

const EMAIL = {
  id: "e1", subject: "Documentos", from_email: "cliente@x.pt", to_emails: ["geral@p.pt"],
  body: "Olá", direction: "received", process_id: "p-7", sent_at: "2026-10-01T10:00:00Z", attachments: [],
};

const montar = (extra = {}) => render(
  <EmailViewerModal isOpen onClose={() => {}} emails={[EMAIL]} selectedEmailId="e1" token="t" clientName="Joana" {...extra} />,
);

beforeEach(() => vi.clearAllMocks());

describe("EmailViewerModal — responder abre o compositor do Webmail", () => {
  it("«Responder» entrega o email com o modo reply", async () => {
    const onReply = vi.fn();
    montar({ onReply });
    fireEvent.click(await screen.findByRole("button", { name: /^responder$/i }));
    expect(onReply).toHaveBeenCalledWith("reply", expect.objectContaining({ id: "e1" }));
  });

  it("«Responder a todos» entrega o modo reply_all", async () => {
    const onReply = vi.fn();
    montar({ onReply });
    fireEvent.click(await screen.findByRole("button", { name: /responder a todos/i }));
    expect(onReply).toHaveBeenCalledWith("reply_all", expect.objectContaining({ id: "e1" }));
  });

  it("não há caixa de resposta própria", async () => {
    montar({ onReply: vi.fn() });
    fireEvent.click(await screen.findByRole("button", { name: /^responder$/i }));
    expect(screen.queryByPlaceholderText(/escreva a sua resposta/i)).not.toBeInTheDocument();
  });

  it("sem `onReply` (Index) não há botões de responder", async () => {
    montar();
    await screen.findAllByText("Documentos");
    expect(screen.queryByRole("button", { name: /responder/i })).not.toBeInTheDocument();
  });

  it("o visualizador já não envia nada sozinho", () => {
    const fonte = fs.readFileSync(path.resolve(process.cwd(), "src/components/EmailViewerModal.js"), "utf8");
    expect(fonte).not.toMatch(/sendWebmailEmail|cancelEmailSend|fetch\(/);
  });
});
