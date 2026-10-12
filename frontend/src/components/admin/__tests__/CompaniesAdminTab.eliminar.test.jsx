/**
 * Eliminar uma empresa: só o Master vê o botão, e o pedido só sai do diálogo, com a password actual.
 * O servidor valida (400/403/429) e recusa se houver utilizadores que só tenham esta empresa — a
 * recusa lê-se no próprio diálogo.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../services/api", () => ({
  getCompanies: vi.fn(),
  createCompany: vi.fn(),
  updateCompany: vi.fn(),
  deleteCompany: vi.fn(),
  testCompanyEmailConnection: vi.fn(),
}));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("sonner", () => ({ toast }));

import CompaniesAdminTab from "../CompaniesAdminTab";
import * as api from "../../../services/api";

const EMPRESAS = [
  { id: "c1", name: "Power Real Estate", network_id: "grupo_power", is_active: true },
  { id: "c2", name: "Ilha Lda", network_id: "", is_active: true },
];
const erro = (status, detail) => Object.assign(new Error("x"), { response: { status, data: { detail } } });

function montar(props = { isMaster: true }) {
  api.getCompanies.mockResolvedValue({ data: { companies: EMPRESAS, total: 2 } });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <CompaniesAdminTab {...props} />
    </QueryClientProvider>,
  );
}

const campoPassword = () => screen.findByLabelText(/a sua password actual/i);

describe("CompaniesAdminTab — eliminar empresa", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.deleteCompany.mockResolvedValue({ data: { detail: "Empresa eliminada com sucesso" } });
  });

  it("só o Master vê o botão de eliminar (e esquecer a prop esconde, não expõe)", async () => {
    const { unmount } = montar({ isMaster: true });
    expect(await screen.findByTestId("btn-delete-company-c1")).toBeTruthy();
    expect(screen.getByTestId("btn-delete-company-c2")).toBeTruthy();
    unmount();
    montar({ isMaster: false });
    await screen.findByTestId("btn-edit-company-c1");
    expect(screen.queryByTestId("btn-delete-company-c1")).toBeNull();
    expect(screen.queryByTestId("eliminar-empresa-dialog")).toBeNull();
  });

  it("clicar abre o diálogo com o nome e NÃO elimina", async () => {
    const user = userEvent.setup();
    montar();
    await user.click(await screen.findByTestId("btn-delete-company-c1"));
    expect(await screen.findByTestId("eliminar-empresa-dialog")).toHaveTextContent("Power Real Estate");
    expect(api.deleteCompany).not.toHaveBeenCalled();
  });

  it("com a password, elimina UMA vez a empresa certa, anuncia e volta a listar", async () => {
    const user = userEvent.setup();
    montar();
    await user.click(await screen.findByTestId("btn-delete-company-c2"));
    await user.type(await campoPassword(), "Segredo-1!");
    await user.click(screen.getByTestId("eliminar-empresa-confirmar"));

    await waitFor(() => expect(api.deleteCompany).toHaveBeenCalledTimes(1));
    expect(api.deleteCompany).toHaveBeenCalledWith("c2", "Segredo-1!");
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Empresa "Ilha Lda" eliminada.'));
    await waitFor(() => expect(api.getCompanies.mock.calls.length).toBeGreaterThan(1));
    await waitFor(() => expect(screen.queryByTestId("eliminar-empresa-dialog")).toBeNull());
  });

  it("password errada: erro no diálogo, a empresa não é anunciada como eliminada", async () => {
    const user = userEvent.setup();
    api.deleteCompany.mockRejectedValue(erro(403, "Password incorrecta."));
    montar();
    await user.click(await screen.findByTestId("btn-delete-company-c1"));
    await user.type(await campoPassword(), "errada");
    await user.click(screen.getByTestId("eliminar-empresa-confirmar"));

    expect(await screen.findByTestId("eliminar-empresa-erro")).toHaveAttribute("data-tipo", "password_errada");
    expect(screen.getByTestId("eliminar-empresa-dialog")).toBeTruthy();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("a recusa do servidor (utilizadores só desta empresa) lê-se no diálogo, com quem são", async () => {
    const user = userEvent.setup();
    api.deleteCompany.mockRejectedValue(
      erro(400, "Não é possível eliminar: 1 utilizador(es) têm apenas esta empresa: Rui (rui@x.pt). Atribua outra empresa a estes utilizadores primeiro."),
    );
    montar();
    await user.click(await screen.findByTestId("btn-delete-company-c1"));
    await user.type(await campoPassword(), "Segredo-1!");
    await user.click(screen.getByTestId("eliminar-empresa-confirmar"));

    const alerta = await screen.findByTestId("eliminar-empresa-erro");
    expect(alerta).toHaveTextContent("rui@x.pt");
    expect(alerta).toHaveAttribute("data-tipo", "recusado");
    expect(screen.getByTestId("eliminar-empresa-dialog")).toBeTruthy();
  });

  it("cancelar não elimina nada", async () => {
    const user = userEvent.setup();
    montar();
    await user.click(await screen.findByTestId("btn-delete-company-c1"));
    const dialogo = await screen.findByTestId("eliminar-empresa-dialog");
    await user.click(within(dialogo).getByRole("button", { name: /cancelar/i }));
    expect(api.deleteCompany).not.toHaveBeenCalled();
  });
});
