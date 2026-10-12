/**
 * Mudar a REDE de uma empresa redesenha quem vê os dados de quem: pede a password actual.
 *
 * O servidor é a parede (400/403 sem a password certa). Aqui prova-se o ecrã: o pedido NÃO sai
 * do formulário quando a rede muda — só do diálogo, com a password —, e reenviar a mesma rede
 * (o formulário manda o objecto inteiro) não incomoda ninguém.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../services/api", () => ({
  getCompanies: vi.fn(),
  createCompany: vi.fn(),
  updateCompany: vi.fn(),
  testCompanyEmailConnection: vi.fn(),
}));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("sonner", () => ({ toast }));

import CompaniesAdminTab from "../CompaniesAdminTab";
import * as api from "../../../services/api";

const EMPRESAS = [
  { id: "c1", name: "Power Real Estate", nif: "", network_id: "grupo_power", is_active: true },
  { id: "c2", name: "Ilha", nif: "", network_id: "", is_active: true },
  // Gravada à mão com um espaço à direita: a mesma rede, para o utilizador.
  { id: "c3", name: "Com espaço", nif: "", network_id: "grupo_x ", is_active: true },
];
const erro = (status, detail) => Object.assign(new Error("x"), { response: { status, data: { detail } } });

function montar(props = { isMaster: true }) {
  api.getCompanies.mockResolvedValue({ data: { companies: EMPRESAS, total: 3 } });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <CompaniesAdminTab {...props} />
    </QueryClientProvider>,
  );
}

async function editarRede(id, rede) {
  fireEvent.click(await screen.findByTestId(`btn-edit-company-${id}`));
  const campoRede = await screen.findByTestId("company-network-input");
  fireEvent.change(campoRede, { target: { value: rede } });
  fireEvent.submit(campoRede.closest("form"));
}

const campoPassword = () => screen.findByLabelText(/a sua password actual/i);
const botaoConfirmar = () => screen.getByTestId("mudar-rede-confirmar");

describe("CompaniesAdminTab — mudar a rede pede a password", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.updateCompany.mockResolvedValue({ data: {} });
  });

  it("mudar a rede abre o diálogo e o pedido NÃO sai do formulário", async () => {
    montar();
    await editarRede("c1", "grupo_domus");
    expect(await screen.findByTestId("mudar-rede-dialog")).toBeTruthy();
    expect(screen.getByTestId("mudar-rede-dialog")).toHaveTextContent("grupo_power");
    expect(screen.getByTestId("mudar-rede-dialog")).toHaveTextContent("grupo_domus");
    expect(api.updateCompany).not.toHaveBeenCalled();
  });

  it("com a password, o pedido sai UMA vez com a password como 3.º argumento", async () => {
    const user = userEvent.setup();
    montar();
    await editarRede("c1", "grupo_domus");
    await user.type(await campoPassword(), "Segredo-1!");
    await user.click(botaoConfirmar());

    await waitFor(() => expect(api.updateCompany).toHaveBeenCalledTimes(1));
    const [id, payload, opcoes] = api.updateCompany.mock.calls[0];
    expect(id).toBe("c1");
    expect(payload.network_id).toBe("grupo_domus");
    expect("confirm_password" in payload).toBe(false);
    expect(opcoes).toEqual({ password: "Segredo-1!" });
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Empresa atualizada."));
    await waitFor(() => expect(screen.queryByTestId("mudar-rede-dialog")).toBeNull());
    expect(screen.queryByTestId("company-form-dialog")).toBeNull();
  });

  it("password errada: o erro diz-se no diálogo, o diálogo fica e o formulário não fecha", async () => {
    const user = userEvent.setup();
    api.updateCompany.mockRejectedValue(erro(403, "Password incorrecta."));
    montar();
    await editarRede("c1", "grupo_domus");
    await user.type(await campoPassword(), "errada");
    await user.click(botaoConfirmar());

    const alerta = await screen.findByTestId("mudar-rede-erro");
    expect(alerta).toHaveAttribute("data-tipo", "password_errada");
    expect(alerta).toHaveTextContent("Password incorrecta.");
    expect(screen.getByTestId("mudar-rede-dialog")).toBeTruthy();
    expect(screen.getByTestId("company-form-dialog")).toBeTruthy();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("cancelar não grava nada e deixa o formulário aberto", async () => {
    const user = userEvent.setup();
    montar();
    await editarRede("c1", "grupo_domus");
    const dialogo = await screen.findByTestId("mudar-rede-dialog");
    await user.click(within(dialogo).getByRole("button", { name: /cancelar/i }));
    expect(api.updateCompany).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByTestId("mudar-rede-dialog")).toBeNull());
    expect(screen.getByTestId("company-form-dialog")).toBeTruthy();
  });

  it("reenviar a MESMA rede não pede password (o formulário manda o objecto inteiro)", async () => {
    montar();
    fireEvent.click(await screen.findByTestId("btn-edit-company-c1"));
    const nome = await screen.findByTestId("company-name-input");
    fireEvent.change(nome, { target: { value: "Power SA" } });
    fireEvent.submit(nome.closest("form"));
    await waitFor(() => expect(api.updateCompany).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId("mudar-rede-dialog")).toBeNull();
    expect(api.updateCompany.mock.calls[0]).toHaveLength(2);
  });

  it("um espaço à direita não é uma mudança de rede", async () => {
    montar();
    await editarRede("c3", "grupo_x");
    await waitFor(() => expect(api.updateCompany).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(screen.queryByTestId("mudar-rede-dialog")).toBeNull();
  });

  it("isolar uma empresa (rede → vazio) também pede password", async () => {
    montar();
    await editarRede("c1", "");
    expect(await screen.findByTestId("mudar-rede-dialog")).toHaveTextContent(/empresa isolada/i);
    expect(api.updateCompany).not.toHaveBeenCalled();
  });

  it("dar uma rede a uma empresa isolada pede password", async () => {
    montar();
    await editarRede("c2", "grupo_power");
    expect(await screen.findByTestId("mudar-rede-dialog")).toBeTruthy();
    expect(api.updateCompany).not.toHaveBeenCalled();
  });

  it("criar uma empresa com rede não pede password (não há fronteira a redesenhar)", async () => {
    api.createCompany.mockResolvedValue({ data: {} });
    montar();
    fireEvent.click(await screen.findByTestId("btn-new-company"));
    const nome = await screen.findByTestId("company-name-input");
    fireEvent.change(nome, { target: { value: "Nova" } });
    fireEvent.change(screen.getByTestId("company-network-input"), { target: { value: "grupo_x" } });
    fireEvent.submit(nome.closest("form"));
    await waitFor(() => expect(api.createCompany).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId("mudar-rede-dialog")).toBeNull();
  });
});
