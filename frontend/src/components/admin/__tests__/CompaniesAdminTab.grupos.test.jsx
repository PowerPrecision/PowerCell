/**
 * O separador Empresas MONTADO, e os chips de grupo (Lote 4, ponto 5).
 *
 * Como a `UsersAccessAdminTab` antes dele, este separador nunca tinha
 * sido montado num teste. A primeira asserção é por isso a mais
 * estúpida: montar e sobreviver.
 *
 * A FORMA DOS DADOS É A REAL. `GET /admin/companies` devolve
 * `{companies: [...], total: N}` (`CompanyListResponse`) e cada linha
 * passa por `CompanyResponse`, um modelo Pydantic — que, por sorte,
 * declara `network_id`. Foi verificado no modelo antes de escrever este
 * ecrã: um campo ausente do modelo é DESCARTADO em silêncio na resposta,
 * e teria dado o chip sempre a dizer "Sem grupo" com um mock a passar.
 * É a armadilha do `{config, fields}` dos SLAs e do `doc_id` do Lote 3.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../services/api", () => ({
  getCompanies: vi.fn(),
  createCompany: vi.fn(),
  updateCompany: vi.fn(),
  testCompanyEmailConnection: vi.fn(),
}));

import CompaniesAdminTab from "../CompaniesAdminTab";
import * as api from "../../../services/api";

const EMPRESAS = [
  { id: "c1", name: "Power Real Estate", nif: "500000001", network_id: "grupo_power_precision" },
  { id: "c2", name: "Precision Credit", nif: "500000002", network_id: "grupo_power_precision" },
  { id: "c3", name: "Domus Imobiliária", nif: "500000003", network_id: "domus" },
  { id: "c4", name: "Entidade Nova", nif: "500000004", network_id: null },
];

function responder(empresas) {
  api.getCompanies.mockResolvedValue({
    data: { companies: empresas, total: empresas.length },
  });
}

function montar() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <CompaniesAdminTab />
    </QueryClientProvider>,
  );
}

describe("CompaniesAdminTab — montagem e chips de grupo", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    responder(EMPRESAS);
  });

  it("monta e lista as empresas", async () => {
    montar();
    expect(await screen.findByText("Power Real Estate")).toBeTruthy();
    expect(api.getCompanies).toHaveBeenCalled();
  });

  it("mostra o grupo como chip, legível", async () => {
    montar();
    await screen.findByText("Power Real Estate");
    // Duas empresas na mesma rede → dois chips com o mesmo rótulo.
    expect(screen.getAllByText("Power Precision")).toHaveLength(2);
    // O nome da empresa é "Domus Imobiliária" e o do grupo "Domus": a
    // consulta é pelo chip, não pelo texto, senão o teste passava com o
    // nome da empresa a fazer-se passar pela etiqueta do grupo.
    expect(screen.getByTestId("chip-rede-domus").textContent).toBe("Domus");
  });

  it("o chip leva o slug CRU no title — é o valor que decide o isolamento", async () => {
    montar();
    await screen.findByTestId("chip-rede-domus");
    const chips = screen.getAllByTestId("chip-rede-grupo_power_precision");
    expect(chips).toHaveLength(2);
    expect(chips[0].getAttribute("title")).toContain("grupo_power_precision");
  });

  it("uma empresa SEM rede diz que é uma ilha", async () => {
    montar();
    const chip = await screen.findByTestId("chip-rede-sem-grupo");
    expect(chip.textContent).toContain("Sem grupo");
    // O estado mais consequente do ecrã não pode ser um campo em branco.
    expect(chip.getAttribute("title")).toContain("ilha");
  });

  it("DOIS slugs com o mesmo rótulo mostram-se crus", async () => {
    // O cenário da gralha: `grupo_power` em vez de
    // `grupo_power_precision` cria uma rede nova de uma empresa só e
    // quebra o isolamento ao contrário. Se o chip embelezasse os dois
    // para "Power", o administrador via um grupo onde há dois.
    responder([
      { id: "c1", name: "Power A", network_id: "grupo_power" },
      { id: "c2", name: "Power B", network_id: "grupo-power" },
    ]);
    montar();
    await screen.findByText("Power A");
    expect(screen.queryByText("Power")).toBeNull();
    expect(screen.getByText("grupo_power")).toBeTruthy();
    expect(screen.getByText("grupo-power")).toBeTruthy();
  });

  it("a coluna existe no cabeçalho da tabela", async () => {
    montar();
    await screen.findByTestId("chip-rede-domus");
    expect(
      screen.getByRole("columnheader", { name: "Grupo" }),
    ).toBeTruthy();
  });

  it("não rebenta com uma resposta vazia", async () => {
    responder([]);
    montar();
    await waitFor(() => {
      expect(screen.getByText("Nenhuma empresa")).toBeTruthy();
    });
  });
});
