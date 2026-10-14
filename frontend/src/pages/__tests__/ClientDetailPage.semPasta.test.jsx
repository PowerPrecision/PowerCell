/**
 * Ficha do Cliente — documentação e «Forçar criação de pasta» (Lote 6, ponto 4).
 *
 * Monta a PÁGINA real. O servidor devolve os ficheiros AGRUPADOS por categoria e `base_path`
 * a `null` quando não há nada no armazenamento: o botão só existe nesse caso, e a tabela tem de
 * mostrar os ficheiros agrupados (tratá-los só como lista deixava-a sempre vazia).
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));

const sessao = vi.hoisted(() => ({ user: { id: "u-1", role: "consultor" } }));
vi.mock("../../contexts/AuthContext", () => ({ useAuth: () => sessao }));

const api = vi.hoisted(() => ({
  getClient: vi.fn(),
  getClientFiles: vi.fn(),
  updateClient: vi.fn(),
  restoreClient: vi.fn(),
  forceCreateS3Folder: vi.fn(),
}));
vi.mock("../../services/api", async (original) => ({ ...(await original()), ...api }));

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

import ClientDetailPage from "../ClientDetailPage";

const CLIENTE = {
  id: "cli-1", nome: "Ana Martins", company_name: "Power Real Estate",
  contacto: { email: "ana@exemplo.pt" }, dados_pessoais: {}, processes: [],
};

function montar() {
  return render(
    <MemoryRouter initialEntries={["/cliente/cli-1"]}>
      <Routes>
        <Route path="/cliente/:id" element={<ClientDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  Object.values(toast).forEach((f) => f.mockClear());
  api.getClient.mockResolvedValue({ data: CLIENTE });
});

describe("ClientDetailPage — pasta de documentos", () => {
  it("sem nada no armazenamento (base_path null) oferece o botão", async () => {
    api.getClientFiles.mockResolvedValue({ data: { files: {}, categories: [], base_path: null } });
    montar();

    expect(await screen.findByTestId("forcar-pasta-s3-btn")).toBeInTheDocument();
    expect(screen.getByText("Sem documentação")).toBeInTheDocument();
  });

  it("carregar envia SÓ o id do cliente, avisa e volta a pedir a documentação", async () => {
    api.getClientFiles.mockResolvedValue({ data: { files: {}, categories: [], base_path: null } });
    api.forceCreateS3Folder.mockResolvedValue({ data: { success: true, created: true } });
    const u = userEvent.setup();
    montar();

    await u.click(await screen.findByTestId("forcar-pasta-s3-btn"));

    await waitFor(() => expect(api.forceCreateS3Folder).toHaveBeenCalledWith("cli-1"));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(expect.stringMatching(/pasta criada/i)));
    await waitFor(() => expect(api.getClientFiles.mock.calls.length).toBeGreaterThanOrEqual(2));
  });

  it("uma falha do servidor diz-se no sítio e a ficha não parte", async () => {
    api.getClientFiles.mockResolvedValue({ data: { files: {}, categories: [], base_path: null } });
    api.forceCreateS3Folder.mockRejectedValue({
      response: { status: 503, data: { detail: "Não foi possível criar a pasta no armazenamento." } },
    });
    const u = userEvent.setup();
    montar();

    await u.click(await screen.findByTestId("forcar-pasta-s3-btn"));

    expect(await screen.findByTestId("forcar-pasta-s3-erro")).toHaveTextContent(/não foi possível criar a pasta/i);
    expect(screen.getByText("Ana Martins", { exact: false })).toBeInTheDocument();
  });

  it("com pasta (base_path preenchido) e sem ficheiros NÃO oferece o botão (contraprova)", async () => {
    api.getClientFiles.mockResolvedValue({
      data: { files: {}, categories: [], base_path: "Documentação Clientes/cli-1" },
    });
    montar();

    await screen.findByText("Sem documentação");
    expect(screen.queryByTestId("forcar-pasta-s3-btn")).not.toBeInTheDocument();
  });

  it("os ficheiros agrupados por categoria aparecem na tabela", async () => {
    api.getClientFiles.mockResolvedValue({
      data: {
        base_path: "Documentação Clientes/cli-1",
        files: {
          "Documentos Pessoais": [{ name: "cc_ana.pdf", path: "x/cc_ana.pdf", category: "Documentos Pessoais" }],
          Financeiros: [{ name: "irs_2025.pdf", path: "x/irs_2025.pdf", category: "Financeiros" }],
        },
      },
    });
    montar();

    const tabela = await screen.findByRole("table");
    expect(within(tabela).getByText("cc_ana.pdf")).toBeInTheDocument();
    expect(within(tabela).getByText("irs_2025.pdf")).toBeInTheDocument();
    expect(screen.queryByTestId("forcar-pasta-s3-btn")).not.toBeInTheDocument();
  });
});
