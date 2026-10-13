/**
 * Ficha do Cliente — «Alterar Empresa» (só Master) — Lote 2, Out 2026.
 *
 * Monta a PÁGINA real: o botão só existe para a conta Master, o diálogo pede a empresa de
 * destino E a password, e o erro (password errada) diz-se no diálogo sem o fechar. A
 * transferência não mexe no S3 — e o ecrã di-lo.
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
  getCompanies: vi.fn(),
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
  api.getCompanies.mockResolvedValue({ data: { companies: EMPRESAS, total: 3 } });
  toast.success.mockClear();
});

describe("ClientDetailPage — Alterar Empresa", () => {
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

  it("o diálogo diz que o S3 não se mexe e não oferece a empresa de origem", async () => {
    const u = userEvent.setup();
    montar();
    const dialogo = await abrirDialogo(u);

    expect(within(dialogo).getByText(/não são movidos/i)).toBeInTheDocument();
    const opcoes = await within(dialogo).findAllByRole("option");
    const nomes = opcoes.map((o) => o.textContent);
    expect(nomes).toContain("Domus");
    expect(nomes).toContain("Precision Crédito");
    expect(nomes).not.toContain("Power Real Estate");
  });

  it("transferir envia cliente, empresa de destino e password; avisa e recarrega a ficha", async () => {
    api.transferClientCompany.mockResolvedValue({
      data: { transferido: true, empresa: { company_name: "Domus" }, processos_transferidos: 1 },
    });
    const u = userEvent.setup();
    montar();
    const dialogo = await abrirDialogo(u);

    await u.selectOptions(await within(dialogo).findByTestId("transferir-cliente-empresa"), "cmp-domus");
    await u.type(within(dialogo).getByTestId("transferir-cliente-password"), "Segredo-Certo-9!");
    await u.click(within(dialogo).getByRole("button", { name: /Transferir cliente/i }));

    await waitFor(() => expect(api.transferClientCompany).toHaveBeenCalledTimes(1));
    expect(api.transferClientCompany).toHaveBeenCalledWith("cli-1", "cmp-domus", "Segredo-Certo-9!");
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(expect.stringContaining("Domus")));
    await waitFor(() => expect(api.getClient.mock.calls.length).toBeGreaterThanOrEqual(2));
    await waitFor(() => expect(screen.queryByTestId("transferir-cliente-dialog")).not.toBeInTheDocument());
  });

  it("sem empresa escolhida não sai pedido e diz-se no diálogo", async () => {
    const u = userEvent.setup();
    montar();
    const dialogo = await abrirDialogo(u);

    await u.type(within(dialogo).getByTestId("transferir-cliente-password"), "x");
    await u.click(within(dialogo).getByRole("button", { name: /Transferir cliente/i }));

    expect(await within(dialogo).findByRole("alert")).toHaveTextContent(/empresa de destino/i);
    expect(api.transferClientCompany).not.toHaveBeenCalled();
  });

  it("password errada: o erro diz-se no diálogo, que NÃO fecha", async () => {
    api.transferClientCompany.mockRejectedValue({
      response: { status: 403, data: { detail: "Password incorrecta." } },
    });
    const u = userEvent.setup();
    montar();
    const dialogo = await abrirDialogo(u);

    await u.selectOptions(await within(dialogo).findByTestId("transferir-cliente-empresa"), "cmp-domus");
    await u.type(within(dialogo).getByTestId("transferir-cliente-password"), "errada");
    await u.click(within(dialogo).getByRole("button", { name: /Transferir cliente/i }));

    expect(await within(dialogo).findByTestId("transferir-cliente-erro")).toHaveTextContent("Password incorrecta.");
    expect(screen.getByTestId("transferir-cliente-dialog")).toBeInTheDocument();
    expect(toast.success).not.toHaveBeenCalled();
  });
});
