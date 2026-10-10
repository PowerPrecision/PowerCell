/**
 * Empresas: criar e mudar a REDE é do Master (adenda de RBAC).
 *
 * Criar um inquilino e decidir quem vê os dados de quem são decisões globais.
 * O servidor recusa (403/404) a quem não é Master; isto prova o lado do ecrã:
 * o Admin e o CEO editam a SUA empresa mas não vêem o botão «Nova Empresa»
 * nem o campo da rede — e, sobretudo, o pedido de actualização NÃO leva
 * `network_id` (o campo que, mudado, dava a um CEO a leitura de outra rede).
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../services/api", () => ({
  getCompanies: vi.fn(),
  createCompany: vi.fn(),
  updateCompany: vi.fn(),
  testCompanyEmailConnection: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import CompaniesAdminTab from "../CompaniesAdminTab";
import * as api from "../../../services/api";

const EMPRESAS = [
  { id: "c1", name: "Power Real Estate", nif: "", network_id: "grupo_power", is_active: true },
];

function montar(props) {
  api.getCompanies.mockResolvedValue({ data: { companies: EMPRESAS, total: 1 } });
  api.updateCompany.mockResolvedValue({ data: {} });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <CompaniesAdminTab {...props} />
    </QueryClientProvider>,
  );
}

describe("CompaniesAdminTab — o que só o Master faz", () => {
  beforeEach(() => vi.clearAllMocks());

  it("o Master vê «Nova Empresa»", async () => {
    montar({ isMaster: true });
    expect(await screen.findByTestId("btn-new-company")).toBeTruthy();
  });

  it("por omissão (sem a prop) o botão NÃO aparece — esquecer a prop esconde, não expõe", async () => {
    montar({});
    await screen.findByTestId("btn-edit-company-c1");
    expect(screen.queryByTestId("btn-new-company")).toBeNull();
  });

  it("o Admin edita a sua empresa mas não vê o campo da rede", async () => {
    montar({ isMaster: false });
    fireEvent.click(await screen.findByTestId("btn-edit-company-c1"));
    await screen.findByTestId("company-name-input");
    expect(screen.queryByTestId("company-network-input")).toBeNull();
  });

  it("o Master vê o campo da rede ao editar", async () => {
    montar({ isMaster: true });
    fireEvent.click(await screen.findByTestId("btn-edit-company-c1"));
    expect(await screen.findByTestId("company-network-input")).toBeTruthy();
  });

  it("o pedido de um Admin NÃO leva network_id; o do Master leva", async () => {
    for (const [isMaster, leva] of [[false, false], [true, true]]) {
      vi.clearAllMocks();
      const { unmount } = montar({ isMaster });
      fireEvent.click(await screen.findByTestId("btn-edit-company-c1"));
      const nome = await screen.findByTestId("company-name-input");
      fireEvent.change(nome, { target: { value: "Power SA" } });
      fireEvent.submit(nome.closest("form"));
      await waitFor(() => expect(api.updateCompany).toHaveBeenCalled());
      const corpo = api.updateCompany.mock.calls[0][1];
      expect("network_id" in corpo, `isMaster=${isMaster}`).toBe(leva);
      expect(corpo.name).toBe("Power SA");
      unmount();
    }
  });
});
