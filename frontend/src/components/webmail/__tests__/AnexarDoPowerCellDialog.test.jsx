import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getProcesses: vi.fn(),
  listDocumentsForEmailAttachment: vi.fn(),
  attachDocumentsToEmail: vi.fn(),
}));
vi.mock("../../../services/api", () => api);
const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), warning: vi.fn(), info: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

import AnexarDoPowerCellDialog, { agruparPorPasta } from "../AnexarDoPowerCellDialog";

const PASTA = "Documentação Clientes/c-1/processos/p-1";
const LISTAGEM = {
  process_id: "p-1",
  process_number: 42,
  client_name: "Rita Sousa",
  em_indexacao: 0,
  files: [
    { path: `${PASTA}/Financeiros/irs_2025.pdf`, name: "irs_2025.pdf", size: 2048, category: "Financeiros" },
    { path: `${PASTA}/Pessoais/cc_rita.pdf`, name: "cc_rita.pdf", size: 1024, category: "Pessoais" },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  api.listDocumentsForEmailAttachment.mockResolvedValue({ data: LISTAGEM });
  api.attachDocumentsToEmail.mockResolvedValue({
    data: { attachments: [{ id: "t-1", file_name: "cc_rita.pdf", file_size: 1024 }], errors: null },
  });
  api.getProcesses.mockResolvedValue({
    data: { items: [{ id: "p-1", client_name: "Rita Sousa", process_number: 42 }] },
  });
});

describe("AnexarDoPowerCellDialog", () => {
  it("com o email ligado a um processo, abre nos documentos dele e anexa os escolhidos", async () => {
    const onAnexados = vi.fn();
    const onOpenChange = vi.fn();
    render(
      <AnexarDoPowerCellDialog open processId="p-1" onAnexados={onAnexados} onOpenChange={onOpenChange} />,
    );

    const caixa = await screen.findByRole("checkbox", { name: "Anexar cc_rita.pdf" });
    expect(api.listDocumentsForEmailAttachment).toHaveBeenCalledWith("p-1");
    expect(api.getProcesses).not.toHaveBeenCalled();
    expect(screen.getByText("Rita Sousa · #42")).toBeInTheDocument();

    await userEvent.click(caixa);
    await userEvent.click(screen.getByRole("button", { name: "Anexar (1)" }));

    await waitFor(() => expect(onAnexados).toHaveBeenCalled());
    expect(api.attachDocumentsToEmail).toHaveBeenCalledWith("p-1", [`${PASTA}/Pessoais/cc_rita.pdf`]);
    expect(onAnexados).toHaveBeenCalledWith([{ id: "t-1", file_name: "cc_rita.pdf", file_size: 1024 }]);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("sem processo, pesquisa primeiro e depois mostra os documentos", async () => {
    render(<AnexarDoPowerCellDialog open onAnexados={vi.fn()} onOpenChange={vi.fn()} />);

    await userEvent.type(screen.getByRole("textbox", { name: "Pesquisar processo" }), "Rita");
    await userEvent.click(await screen.findByRole("button", { name: /Rita Sousa/ }));

    expect(await screen.findByRole("checkbox", { name: "Anexar irs_2025.pdf" })).toBeInTheDocument();
    expect(api.getProcesses).toHaveBeenCalledWith({ search: "Rita", size: 10 });
    expect(api.listDocumentsForEmailAttachment).toHaveBeenCalledWith("p-1");
  });

  it("o erro do servidor aparece como texto, não como objecto", async () => {
    api.listDocumentsForEmailAttachment.mockRejectedValue({
      response: { data: { detail: "Sem permissão para ver os documentos deste processo" } },
    });
    render(<AnexarDoPowerCellDialog open processId="p-x" onAnexados={vi.fn()} onOpenChange={vi.fn()} />);

    expect(
      await screen.findByText("Sem permissão para ver os documentos deste processo"),
    ).toBeInTheDocument();
  });

  it("sem nada escolhido, o botão Anexar está desligado", async () => {
    render(<AnexarDoPowerCellDialog open processId="p-1" onAnexados={vi.fn()} onOpenChange={vi.fn()} />);

    await screen.findByRole("checkbox", { name: "Anexar cc_rita.pdf" });
    expect(screen.getByRole("button", { name: "Anexar" })).toBeDisabled();
  });
});

describe("agruparPorPasta", () => {
  it("agrupa pela pasta e mantém a ordem do servidor", () => {
    expect(agruparPorPasta(LISTAGEM.files).map(([pasta]) => pasta)).toEqual(["Financeiros", "Pessoais"]);
    expect(agruparPorPasta([{ path: "x", name: "x" }])[0][0]).toBe("Outros");
  });
});
