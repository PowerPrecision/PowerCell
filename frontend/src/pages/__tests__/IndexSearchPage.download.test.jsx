/**
 * «Download» ao lado de «Ver documento» na pesquisa avançada (Out 2026).
 * Monta a página, a tabela e o visualizador REAIS; só se falseiam o layout e o Axios.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));
vi.mock("../../services/api", () => ({
  searchIndexAdvanced: vi.fn(),
  getIndexDocumentContent: vi.fn(),
  readBlobErrorBody: vi.fn(async (e) => (e?.response?.data && typeof e.response.data === "object" ? e.response.data : null)),
}));

import { toast } from "sonner";
import { getIndexDocumentContent, searchIndexAdvanced } from "../../services/api";
import IndexSearchPage from "../index/IndexSearchPage";

const EXTRATO = {
  document_id: "doc-extrato-1", document_type: "extrato", process_id: "proc-1", process_number: 4711,
  company_name: "Casa Alfa", period: "2026-09", needs_review: false, bank: "Caixa Geral de Depósitos",
};
const EMPREGO = {
  process_id: "proc-3", process_number: 4713, company_name: "Casa Beta", job_id: "job_abc",
  employer: { nif: "509442013", name: "Outra SA", location: "Porto" }, job_title: "Gerente",
  net_salary: 2500, contract_type: "termo_certo", period: "2026-09", needs_review: false,
  admission_date: "2021-05-03", certified_by_declaration: true, source_documents: 2,
  document_ids: ["doc-a", "doc-b"],
};
const resposta = (view, items) => ({ data: { view, items, total: items.length, page: 1, size: 25, filters: {} } });
const ficheiro = (tipo = "application/pdf", disposicao) => ({
  data: new Blob(["bytes"], { type: tipo }),
  headers: { "content-type": tipo, ...(disposicao ? { "content-disposition": disposicao } : {}) },
});

function montar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={["/index/pesquisa"]}>
        <Routes>
          <Route path="/index/pesquisa" element={<IndexSearchPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

let descargas;
beforeEach(() => {
  vi.clearAllMocks();
  descargas = [];
  URL.createObjectURL = vi.fn(() => "blob:teste");
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function click() {
    descargas.push({ href: this.href, download: this.download });
  });
});
afterEach(() => vi.restoreAllMocks());

async function pesquisar(user) {
  await user.click(screen.getByRole("button", { name: "Pesquisar" }));
  return screen.findByTestId("pesquisa-linha");
}

describe("Download na linha", () => {
  it("pede o ficheiro COM download:true e entrega-o ao browser com o nome do rótulo + extensão", async () => {
    const user = userEvent.setup();
    searchIndexAdvanced.mockResolvedValue(resposta("documents", [EXTRATO]));
    getIndexDocumentContent.mockResolvedValue(ficheiro("application/pdf"));
    montar();
    const linha = await pesquisar(user);

    await user.click(within(linha).getByTestId("download-documento"));
    await waitFor(() => expect(descargas).toHaveLength(1));
    expect(getIndexDocumentContent).toHaveBeenCalledWith("doc-extrato-1", { download: true });
    expect(descargas[0].download).toBe("Extrato · Caixa Geral de Depósitos · 2026-09.pdf");
    // um download nunca abre o diálogo de pré-visualização
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("o nome que o servidor deu (se o browser o deixar ler) vence o rótulo", async () => {
    const user = userEvent.setup();
    searchIndexAdvanced.mockResolvedValue(resposta("documents", [EXTRATO]));
    getIndexDocumentContent.mockResolvedValue(ficheiro("application/pdf", 'attachment; filename="extrato_real.pdf"'));
    montar();
    await user.click(within(await pesquisar(user)).getByTestId("download-documento"));
    await waitFor(() => expect(descargas).toHaveLength(1));
    expect(descargas[0].download).toBe("extrato_real.pdf");
  });

  it("«Ver documento» continua a pedir SEM download", async () => {
    const user = userEvent.setup();
    searchIndexAdvanced.mockResolvedValue(resposta("documents", [EXTRATO]));
    getIndexDocumentContent.mockResolvedValue(ficheiro());
    montar();
    await user.click(within(await pesquisar(user)).getByTestId("ver-documento"));
    await waitFor(() => expect(getIndexDocumentContent).toHaveBeenCalledWith("doc-extrato-1"));
    expect(descargas).toHaveLength(0);
  });

  it("o botão fica desactivado enquanto a descarga decorre (sem duplo pedido)", async () => {
    const user = userEvent.setup();
    searchIndexAdvanced.mockResolvedValue(resposta("documents", [EXTRATO]));
    let resolver;
    getIndexDocumentContent.mockReturnValue(new Promise((r) => { resolver = r; }));
    montar();
    const linha = await pesquisar(user);
    const botao = within(linha).getByTestId("download-documento");
    await user.click(botao);
    await waitFor(() => expect(botao).toBeDisabled());
    await user.click(botao);
    expect(getIndexDocumentContent).toHaveBeenCalledTimes(1);
    resolver(ficheiro());
    await waitFor(() => expect(botao).not.toBeDisabled());
    expect(descargas).toHaveLength(1);
  });

  it("uma recusa do servidor diz-se (com o motivo dele) e não guarda nada", async () => {
    const user = userEvent.setup();
    searchIndexAdvanced.mockResolvedValue(resposta("documents", [EXTRATO]));
    getIndexDocumentContent.mockRejectedValue({ response: { status: 413, data: { detail: "O ficheiro é demasiado grande para descarregar por aqui." } } });
    montar();
    await user.click(within(await pesquisar(user)).getByTestId("download-documento"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("O ficheiro é demasiado grande para descarregar por aqui."));
    expect(descargas).toHaveLength(0);
  });
});

describe("vários documentos por linha (vista por emprego)", () => {
  it("«Download (2)» descarrega os dois, em sequência, e di-lo", async () => {
    const user = userEvent.setup();
    searchIndexAdvanced.mockResolvedValue(resposta("jobs", [EMPREGO]));
    getIndexDocumentContent.mockResolvedValue(ficheiro());
    montar();
    await user.click(within(await pesquisar(user)).getByRole("button", { name: /Download de 2 documentos/ }));
    await waitFor(() => expect(descargas).toHaveLength(2));
    expect(getIndexDocumentContent.mock.calls.map((c) => c[0])).toEqual(["doc-a", "doc-b"]);
    expect(descargas.map((d) => d.download)).toEqual([
      "Documento 1 de 2 · Outra SA.pdf",
      "Documento 2 de 2 · Outra SA.pdf",
    ]);
    expect(toast.success).toHaveBeenCalledWith("2 documentos descarregados.");
  });

  it("uma falha não impede os seguintes e o aviso diz quantos falharam", async () => {
    const user = userEvent.setup();
    searchIndexAdvanced.mockResolvedValue(resposta("jobs", [EMPREGO]));
    getIndexDocumentContent
      .mockRejectedValueOnce({ response: { status: 404, data: { detail: "Ficheiro não encontrado." } } })
      .mockResolvedValueOnce(ficheiro());
    montar();
    await user.click(within(await pesquisar(user)).getByTestId("download-documento"));
    await waitFor(() => expect(descargas).toHaveLength(1));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(toast.error.mock.calls[0][0]).toMatch(/1 de 2 documentos não foram descarregados/);
  });

  it("o diálogo descarrega o documento que está a mostrar", async () => {
    const user = userEvent.setup();
    searchIndexAdvanced.mockResolvedValue(resposta("jobs", [EMPREGO]));
    getIndexDocumentContent.mockResolvedValue(ficheiro());
    montar();
    await user.click(within(await pesquisar(user)).getByTestId("ver-documento"));
    await screen.findByRole("dialog");
    await user.click(screen.getByRole("button", { name: "Documento seguinte" }));
    await waitFor(() => expect(getIndexDocumentContent).toHaveBeenCalledWith("doc-b"));
    getIndexDocumentContent.mockClear();
    await user.click(screen.getByTestId("visualizador-download"));
    await waitFor(() => expect(descargas).toHaveLength(1));
    expect(getIndexDocumentContent).toHaveBeenCalledWith("doc-b", { download: true });
  });
});

describe("sem referência não há Download", () => {
  it("uma linha sem document_ids não desenha nenhum dos dois botões", async () => {
    const user = userEvent.setup();
    searchIndexAdvanced.mockResolvedValue(resposta("jobs", [{ ...EMPREGO, document_ids: [] }]));
    montar();
    await pesquisar(user);
    expect(screen.queryByTestId("download-documento")).toBeNull();
    expect(screen.queryByTestId("ver-documento")).toBeNull();
  });
});
