/**
 * QA-8 (6, 7): o corpo do email faz scroll e cada anexo pode ir directamente para os documentos
 * do processo aberto.
 *
 * Scroll: o corpo estava num `ScrollArea` com `flex-1`; o Radix corta a Root e o viewport nunca
 * transborda (FRONTEND_GUIDELINES § 27.14), logo um email comprido ficava cortado. O jsdom não
 * calcula alturas — afirma-se a REGRA (contentor nativo com `overflow-y-auto` e `min-h-0`) e que o
 * corpo não está dentro de um `ScrollArea`.
 * Guardar: sai pelo mesmo endpoint do «Arquivar no Processo» do Webmail (validação, Index/IA,
 * histórico), com o `process_id` do processo aberto — nunca o de um campo do email.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  sendWebmailEmail: vi.fn(),
  cancelEmailSend: vi.fn(),
  downloadEmailAttachment: vi.fn(),
  getEmailAttachmentPreview: vi.fn(),
  archiveEmailAttachment: vi.fn(),
}));
vi.mock("../../services/api", () => api);
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
const auth = vi.hoisted(() => ({ atual: { effectiveRole: "consultor" } }));
vi.mock("../../contexts/AuthContext", () => ({ useAuthOpcional: () => auth.atual }));

import EmailViewerModal from "../EmailViewerModal";

const EMAIL = {
  id: "e1", subject: "Documentos", from_email: "cliente@x.pt", to_emails: ["geral@p.pt"],
  body: "Linha\n".repeat(400), direction: "received", process_id: "p-7", sent_at: "2026-10-01T10:00:00Z",
  attachments: [{ id: "a1", filename: "IRS 2025.pdf", content_type: "application/pdf", size: 1000 }],
};

const montar = (props = {}) => render(
  <EmailViewerModal isOpen onClose={() => {}} emails={[EMAIL]} selectedEmailId="e1" token="t" clientName="Joana" {...props} />,
);

beforeEach(() => {
  vi.clearAllMocks();
  auth.atual = { effectiveRole: "consultor" };
});

describe("EmailViewerModal — scroll do corpo", () => {
  it("o corpo vive num contentor com overflow-y-auto e min-h-0, fora de qualquer ScrollArea", async () => {
    montar();
    const corpo = await screen.findByTestId("corpo-do-email");
    expect(corpo.className).toMatch(/overflow-y-auto/);
    expect(corpo.className).toMatch(/min-h-0/);
    expect(corpo.className).toMatch(/flex-1/);
    expect(corpo.closest("[data-radix-scroll-area-viewport]")).toBeNull();
    expect(corpo.closest("[data-radix-scroll-area-root], [data-orientation]")).toBeNull();
    // a coluna que o contém também pode encolher (senão o flex cresce com o conteúdo)
    expect(corpo.parentElement.className).toMatch(/min-h-0/);
    expect(corpo).toHaveTextContent("Linha");
  });
});

describe("EmailViewerModal — Guardar nos Documentos do Processo", () => {
  const botao = () => screen.queryByRole("button", { name: /guardar ir?s? ?2025\.pdf nos documentos do processo|guardar .* nos documentos do processo/i });

  it("no contexto de um processo, envia o anexo para o processo aberto", async () => {
    api.archiveEmailAttachment.mockResolvedValue({ data: { success: true, intake: { fila_ia: false } } });
    montar({ processId: "p-1" });
    fireEvent.click(await screen.findByRole("button", { name: /guardar irs 2025\.pdf nos documentos do processo/i }));

    await waitFor(() => expect(api.archiveEmailAttachment).toHaveBeenCalledTimes(1));
    expect(api.archiveEmailAttachment).toHaveBeenCalledWith(
      "e1", "a1", { process_id: "p-1", category: "Outros" },
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
  });

  it("uma recusa do servidor diz-se com o motivo dele", async () => {
    api.archiveEmailAttachment.mockRejectedValue({ response: { data: { detail: "Processo fechado: reabra-o primeiro" } } });
    montar({ processId: "p-1" });
    fireEvent.click(await screen.findByRole("button", { name: /nos documentos do processo/i }));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Processo fechado: reabra-o primeiro"));
  });

  it("sem processo (Webmail) não há botão", async () => {
    montar();
    await screen.findByTestId("corpo-do-email");
    expect(botao()).toBeNull();
  });

  it("um perfil que não arquiva (parceiro) não vê o botão", async () => {
    auth.atual = { effectiveRole: "parceiro" };
    montar({ processId: "p-1" });
    await screen.findByTestId("corpo-do-email");
    expect(botao()).toBeNull();
  });

  it("fora de um AuthProvider falha fechado (sem botão)", async () => {
    auth.atual = null;
    montar({ processId: "p-1" });
    await screen.findByTestId("corpo-do-email");
    expect(botao()).toBeNull();
  });
});
