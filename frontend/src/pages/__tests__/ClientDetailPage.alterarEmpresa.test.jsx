/**
 * Ficha do Cliente — «Alterar Empresa» (só Master) — Lote 6, Out 2026.
 *
 * Monta a PÁGINA real: o botão só existe para a conta Master, o diálogo lista os PROCESSOS do
 * cliente (é o processo que transita, não o cliente), pede o destino e a password, e o erro
 * (password errada) diz-se no diálogo sem o fechar. A transferência não mexe no S3 — e o ecrã di-lo.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));

const sessao = vi.hoisted(() => ({ user: { id: "u-master", role: "master" } }));
vi.mock("../../contexts/AuthContext", () => ({ useAuth: () => sessao }));

const api = vi.hoisted(() => ({
  getClient: vi.fn(),
  getClientFiles: vi.fn(() => Promise.resolve({ data: { files: [] } })),
  updateClient: vi.fn(),
  restoreClient: vi.fn(),
  getAllCompanies: vi.fn(),
  previewTransferClientCompany: vi.fn(),
  transferClientCompany: vi.fn(),
}));
vi.mock("../../services/api", async (original) => ({ ...(await original()), ...api }));

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

import ClientDetailPage from "../ClientDetailPage";

const CLIENTE = {
  id: "cli-1", nome: "Ana Martins", company_name: "Power Real Estate",
  contacto: { email: "ana@exemplo.pt" }, dados_pessoais: {}, processes: [],
};
const EMPRESAS = [
  { id: "cmp-power", name: "Power Real Estate" },
  { id: "cmp-domus", name: "Domus" },
  { id: "cmp-precision", name: "Precision Crédito" },
];
const P1 = { id: "p1", process_number: 11, status: "novo", company_name: "Power Real Estate", terminado: false, ja_no_destino: false };
const P2 = { id: "p2", process_number: 22, status: "docs", company_name: "Power Real Estate", terminado: false, ja_no_destino: false };

function montar() {
  return render(
    <MemoryRouter initialEntries={["/cliente/cli-1"]}>
      <Routes>
        <Route path="/cliente/:id" element={<ClientDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

async function abrirDialogo(u) {
  await u.click(await screen.findByRole("button", { name: /Alterar Empresa/i }));
  return screen.findByTestId("transferir-cliente-dialog");
}

beforeEach(() => {
  sessao.user = { id: "u-master", role: "master" };
  Object.values(api).forEach((f) => f.mockReset?.());
  api.getClient.mockResolvedValue({ data: CLIENTE });
  api.getClientFiles.mockResolvedValue({ data: { files: [] } });
  api.getAllCompanies.mockResolvedValue(EMPRESAS);
  api.previewTransferClientCompany.mockResolvedValue({ data: { processos: [P1, P2] } });
  toast.success.mockClear();
});

describe("ClientDetailPage — Alterar Empresa (processos)", () => {
  it("o Master vê o botão", async () => {
    montar();
    expect(await screen.findByRole("button", { name: /Alterar Empresa/i })).toBeInTheDocument();
  });

  it.each(["admin", "ceo", "diretor", "consultor"])("%s não vê o botão (contraprova)", async (papel) => {
    sessao.user = { id: "u-x", role: papel };
    montar();
    await screen.findByText("Editar Cliente");
    expect(screen.queryByRole("button", { name: /Alterar Empresa/i })).not.toBeInTheDocument();
    expect(screen.queryByTestId("transferir-cliente-dialog")).not.toBeInTheDocument();
  });

  it("o diálogo diz que o cliente NÃO muda e que o S3 não se mexe", async () => {
    const u = userEvent.setup();
    montar();
    const dialogo = await abrirDialogo(u);

    expect(within(dialogo).getByText(/não muda/i)).toBeInTheDocument();
    expect(within(dialogo).getByText(/não são movidos/i)).toBeInTheDocument();
    const nomes = (await within(dialogo).findAllByRole("option")).map((o) => o.textContent);
    expect(nomes).toContain("Domus");
    // A empresa de origem passa a ser oferecida: o cliente pode ter processos em várias empresas.
    expect(nomes).toContain("Power Real Estate");
  });

  it("lista os processos do cliente para escolher", async () => {
    const u = userEvent.setup();
    montar();
    const dialogo = await abrirDialogo(u);

    const lista = await within(dialogo).findByTestId("transferir-cliente-processos");
    expect(within(lista).getByRole("checkbox", { name: /#11/ })).not.toBeChecked();
    expect(within(lista).getByRole("checkbox", { name: /#22/ })).not.toBeChecked();
  });

  it("transferir envia cliente, destino, PROCESSOS escolhidos e password; avisa e recarrega a ficha", async () => {
    api.transferClientCompany.mockResolvedValue({
      data: { transferido: true, empresa: { company_name: "Domus" }, processos_transferidos: 1 },
    });
    const u = userEvent.setup();
    montar();
    const dialogo = await abrirDialogo(u);

    await u.selectOptions(await within(dialogo).findByTestId("transferir-cliente-empresa"), "cmp-domus");
    await u.click(await within(dialogo).findByRole("checkbox", { name: /#22/ }));
    await u.type(within(dialogo).getByTestId("transferir-cliente-password"), "Segredo-Certo-9!");
    await u.click(within(dialogo).getByRole("button", { name: /Transferir processos/i }));

    await waitFor(() => expect(api.transferClientCompany).toHaveBeenCalledTimes(1));
    expect(api.transferClientCompany).toHaveBeenCalledWith("cli-1", "cmp-domus", ["p2"], "Segredo-Certo-9!");
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(expect.stringContaining("Domus")));
    await waitFor(() => expect(api.getClient.mock.calls.length).toBeGreaterThanOrEqual(2));
    await waitFor(() => expect(screen.queryByTestId("transferir-cliente-dialog")).not.toBeInTheDocument());
  });

  it("com um só processo, ele já vem escolhido", async () => {
    api.previewTransferClientCompany.mockResolvedValue({ data: { processos: [P1] } });
    api.transferClientCompany.mockResolvedValue({
      data: { transferido: true, empresa: { company_name: "Domus" }, processos_transferidos: 1 },
    });
    const u = userEvent.setup();
    montar();
    const dialogo = await abrirDialogo(u);

    expect(await within(dialogo).findByRole("checkbox", { name: /#11/ })).toBeChecked();
    await u.selectOptions(within(dialogo).getByTestId("transferir-cliente-empresa"), "cmp-domus");
    await u.type(within(dialogo).getByTestId("transferir-cliente-password"), "Segredo-Certo-9!");
    await u.click(within(dialogo).getByRole("button", { name: /Transferir processos/i }));

    await waitFor(() =>
      expect(api.transferClientCompany).toHaveBeenCalledWith("cli-1", "cmp-domus", ["p1"], "Segredo-Certo-9!"));
  });

  it("sem nenhum processo escolhido o botão está desactivado e não sai pedido", async () => {
    const u = userEvent.setup();
    montar();
    const dialogo = await abrirDialogo(u);
    await within(dialogo).findByTestId("transferir-cliente-processos");

    await u.selectOptions(within(dialogo).getByTestId("transferir-cliente-empresa"), "cmp-domus");
    await u.type(within(dialogo).getByTestId("transferir-cliente-password"), "x");

    expect(within(dialogo).getByRole("button", { name: /Transferir processos/i })).toBeDisabled();
    expect(api.transferClientCompany).not.toHaveBeenCalled();
  });

  it("sem empresa escolhida não sai pedido e diz-se no diálogo", async () => {
    api.previewTransferClientCompany.mockResolvedValue({ data: { processos: [P1] } });
    const u = userEvent.setup();
    montar();
    const dialogo = await abrirDialogo(u);
    await within(dialogo).findByRole("checkbox", { name: /#11/ });

    await u.type(within(dialogo).getByTestId("transferir-cliente-password"), "x");
    await u.click(within(dialogo).getByRole("button", { name: /Transferir processos/i }));

    expect(await within(dialogo).findByRole("alert")).toHaveTextContent(/empresa de destino/i);
    expect(api.transferClientCompany).not.toHaveBeenCalled();
  });

  it("password errada: o erro diz-se no diálogo, que NÃO fecha", async () => {
    api.previewTransferClientCompany.mockResolvedValue({ data: { processos: [P1] } });
    api.transferClientCompany.mockRejectedValue({
      response: { status: 403, data: { detail: "Password incorrecta." } },
    });
    const u = userEvent.setup();
    montar();
    const dialogo = await abrirDialogo(u);

    await u.selectOptions(await within(dialogo).findByTestId("transferir-cliente-empresa"), "cmp-domus");
    await within(dialogo).findByRole("checkbox", { name: /#11/ });
    await u.type(within(dialogo).getByTestId("transferir-cliente-password"), "errada");
    await u.click(within(dialogo).getByRole("button", { name: /Transferir processos/i }));

    expect(await within(dialogo).findByTestId("transferir-cliente-erro")).toHaveTextContent("Password incorrecta.");
    expect(screen.getByTestId("transferir-cliente-dialog")).toBeInTheDocument();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("um processo que já está no destino não se pode escolher e diz-se", async () => {
    const u = userEvent.setup();
    montar();
    const dialogo = await abrirDialogo(u);
    await within(dialogo).findByTestId("transferir-cliente-processos");

    api.previewTransferClientCompany.mockResolvedValue({
      data: { processos: [P1, { ...P2, ja_no_destino: true }] },
    });
    await u.selectOptions(within(dialogo).getByTestId("transferir-cliente-empresa"), "cmp-domus");

    expect(await within(dialogo).findByTestId("transferir-processo-ja-no-destino-p2")).toBeInTheDocument();
    expect(within(dialogo).getByRole("checkbox", { name: /#22/ })).toBeDisabled();
    expect(within(dialogo).getByRole("checkbox", { name: /#11/ })).toBeEnabled();
    expect(api.previewTransferClientCompany).toHaveBeenLastCalledWith("cli-1", "cmp-domus");
  });

  it("cliente sem processos: diz-se e não se pode confirmar", async () => {
    api.previewTransferClientCompany.mockResolvedValue({ data: { processos: [] } });
    const u = userEvent.setup();
    montar();
    const dialogo = await abrirDialogo(u);

    expect(await within(dialogo).findByTestId("transferir-cliente-sem-processos")).toBeInTheDocument();
    expect(within(dialogo).getByRole("button", { name: /Transferir processos/i })).toBeDisabled();
  });

  it("a lista de processos falhou: diz-se, em vez de um diálogo que parece vazio", async () => {
    api.previewTransferClientCompany.mockRejectedValue(new Error("rede"));
    const u = userEvent.setup();
    montar();
    const dialogo = await abrirDialogo(u);

    expect(await within(dialogo).findByTestId("transferir-cliente-processos-falhou")).toBeInTheDocument();
    expect(within(dialogo).getByRole("button", { name: /Transferir processos/i })).toBeDisabled();
  });
});
