/**
 * O modal de envio de documentação fala SÓ pelo cliente Axios (Lote 7.3).
 *
 * Cinco pedidos eram `fetch` cru (configuração dos destinatários, documentos, preview, novo balcão):
 * perdiam `X-Company-Id` e `X-Active-Role`, e o servidor decidia a empresa e a conta de envio sem o
 * contexto activo — o incidente de 2026-09-21 e o Strict Context Switching do Lote 7.1. O teste monta
 * o componente REAL e afirma que cada pedido sai pela função do `services/api` (o único sítio onde o
 * interceptor injecta o contexto) e que o `fetch` global nunca é chamado.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import fs from "node:fs";
import path from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  default: { post: vi.fn() },
  getDocumentRecipients: vi.fn(),
  getProcessDocumentsForSending: vi.fn(),
  previewDocumentationEmail: vi.fn(),
  createUserBranch: vi.fn(),
}));
vi.mock("../../services/api", () => api);
vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("../ui/SmartRichEditor", () => ({ default: () => <div data-testid="editor" /> }));

import SendDocumentationModal from "../SendDocumentationModal";

const CONFIG = {
  enabled: true,
  recipients: [{ id: "r1", name: "BCP Alvalade", email: "alvalade@bcp.pt", active: true }],
  default_to_emails: ["geral@precision.pt"],
  email_template: "",
};
const DOCS = [{ id: "d1", original_name: "IRS 2025.pdf", s3_path: "k/irs.pdf", category: "IRS" }];

const montar = () => render(
  <SendDocumentationModal open onOpenChange={() => {}} processId="p-1" process={{}} token="t" user={{ role: "consultor" }} />,
);

beforeEach(() => {
  vi.clearAllMocks();
  globalThis.fetch = vi.fn(() => { throw new Error("fetch cru não devia ser usado"); });
  api.getDocumentRecipients.mockResolvedValue({ data: CONFIG });
  api.getProcessDocumentsForSending.mockResolvedValue({ data: { documents: DOCS } });
  api.previewDocumentationEmail.mockResolvedValue({ data: { success: true, html: "<p>Olá</p>", subject: "Documentação" } });
});

describe("SendDocumentationModal — transporte", () => {
  it("carrega destinatários, documentos e preview pelas funções do cliente Axios", async () => {
    montar();

    expect(await screen.findByText("IRS 2025.pdf")).toBeInTheDocument();
    expect(await screen.findByText("geral@precision.pt")).toBeInTheDocument();
    expect(api.getDocumentRecipients).toHaveBeenCalledTimes(1);
    expect(api.getProcessDocumentsForSending).toHaveBeenCalledWith("p-1");
    await waitFor(() => expect(api.previewDocumentationEmail).toHaveBeenCalledWith("p-1"));
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("os TO configurados vêm pré-seleccionados e os documentos NÃO (excepto o RGPD assinado)", async () => {
    montar();
    await screen.findByText("IRS 2025.pdf");

    const caixas = screen.getAllByRole("checkbox");
    // 1 documento (IRS) + 1 balcão BCC + 1 TO
    const marcadas = caixas.filter((c) => c.getAttribute("aria-checked") === "true" || c.dataset.state === "checked");
    expect(marcadas).toHaveLength(1);
    expect(marcadas[0].closest("label")).toHaveTextContent("geral@precision.pt");
  });

  it("uma falha na configuração não impede de listar os documentos", async () => {
    api.getDocumentRecipients.mockRejectedValue({ response: { status: 500 } });
    montar();
    // sem `config.enabled` o modal não desenha; o que se afirma é que o pedido dos documentos foi feito
    await waitFor(() => expect(api.getProcessDocumentsForSending).toHaveBeenCalled());
  });

  it("guardar um balcão novo vai por `createUserBranch` e refaz a leitura", async () => {
    api.createUserBranch.mockResolvedValue({ data: { id: "b9", name: "BPI Chiado", email: "chiado@bpi.pt" } });
    montar();
    await screen.findByText("IRS 2025.pdf");

    fireEvent.click(screen.getByRole("button", { name: /adicionar novo balcão/i }));
    fireEvent.change(screen.getByPlaceholderText("Ex: BCP Alvalade"), { target: { value: "BPI Chiado" } });
    fireEvent.change(screen.getByPlaceholderText("balcao@banco.pt"), { target: { value: "chiado@bpi.pt" } });
    fireEvent.click(screen.getByRole("button", { name: /guardar para mim/i }));

    await waitFor(() => expect(api.createUserBranch).toHaveBeenCalledWith({ name: "BPI Chiado", email: "chiado@bpi.pt" }));
    await waitFor(() => expect(api.getDocumentRecipients).toHaveBeenCalledTimes(2));
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});

describe("SendDocumentationModal — guarda sobre o código", () => {
  const fonte = fs.readFileSync(path.resolve(process.cwd(), "src/components/SendDocumentationModal.js"), "utf-8")
    .replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");

  it("nenhum `fetch` cru nem URL do backend", () => {
    expect(fonte).not.toMatch(/\bfetch\(/);
    expect(fonte).not.toMatch(/API_URL/);
  });

  it("contraprova: o leitor leu o ficheiro", () => {
    expect(fonte).toContain("getDocumentRecipients(");
    expect(fonte).toContain("api.post(");
  });
});
