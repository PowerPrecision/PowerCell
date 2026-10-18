/**
 * Definições da empresa vs. definições globais do sistema, separadas à vista (QA-6).
 *
 * O Master via numa só lista as categorias DA EMPRESA e as secções GLOBAIS (manutenção, portal,
 * SLAs…), e não sabia se estava a mexer na sua empresa ou no sistema inteiro. Hoje há dois
 * grupos com título, e o conteúdo diz o âmbito.
 */
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

let papel = "master";
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    token: "t",
    user: { id: "u1", name: "Utilizador", role: papel },
    effectiveCompanyId: "emp-domus",
  }),
}));

vi.mock("../../services/api", () => ({
  getSystemConfigCompanies: vi.fn(async () => ({
    data: { companies: [{ company_id: "emp-domus", company_name: "Domus" }], total: 1 },
  })),
  getSystemConfig: vi.fn(async () => ({ data: { config: {} } })),
  updateSystemConfigSection: vi.fn(async () => ({ data: {} })),
}));

import SystemConfigPage from "../SystemConfigPage";

const RESPOSTA = {
  config: { storage: { provider: "s3" }, dashboard_slas: { enabled: true, novo: 7, analise: 15, aprovado: 30 } },
  fields: {
    storage: { title: "Armazenamento", description: "d", fields: [{ key: "provider", label: "Provedor", type: "text" }] },
  },
};

const montar = (tab = "storage") =>
  render(
    <MemoryRouter initialEntries={[`/configuracoes?tab=${tab}`]}>
      <SystemConfigPage embedded />
    </MemoryRouter>,
  );

beforeEach(() => {
  papel = "master";
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => RESPOSTA })));
});

describe("Definições: empresa vs. sistema", () => {
  it("o Master vê dois grupos, com a empresa em vigor nomeada e o global marcado «Só Master»", async () => {
    montar();
    const empresa = await screen.findByTestId("grupo-empresa");
    expect(empresa).toHaveTextContent("Definições da empresa");
    const global = screen.getByTestId("grupo-global");
    expect(global).toHaveTextContent("Sistema (global)");
    expect(global).toHaveTextContent("Só Master");
    expect(screen.getAllByText("Domus").length).toBeGreaterThan(0);
  });

  it("as secções globais vivem DENTRO do grupo global e as da empresa fora dele", async () => {
    montar();
    const global = await screen.findByTestId("grupo-global");
    expect(within(global).getByTestId("nav-dashboard-slas")).toBeInTheDocument();
    expect(within(global).getByTestId("nav-maintenance")).toBeInTheDocument();
    expect(within(global).queryByText("Armazenamento")).not.toBeInTheDocument();
  });

  it("uma categoria da empresa diz de que empresa é; uma secção global diz que é de todas", async () => {
    const { unmount } = montar("storage");
    expect(await screen.findByTestId("ambito-empresa")).toHaveTextContent("Domus");
    expect(screen.queryByTestId("ambito-global")).not.toBeInTheDocument();
    unmount();

    montar("dashboard_slas");
    expect(await screen.findByTestId("ambito-global")).toHaveTextContent(/todas as empresas/i);
    expect(screen.queryByTestId("ambito-empresa")).not.toBeInTheDocument();
  });

  it("quem não é Master não vê o grupo global", async () => {
    papel = "ceo";
    montar();
    await screen.findByTestId("grupo-empresa");
    expect(screen.queryByTestId("grupo-global")).not.toBeInTheDocument();
    expect(screen.queryByTestId("chips-globais")).not.toBeInTheDocument();
  });

  it("no telemóvel os chips globais também ficam num grupo à parte", async () => {
    montar();
    const chips = await screen.findByTestId("chips-globais");
    expect(chips).toHaveTextContent("Sistema (global)");
    expect(within(chips).getByTestId("chip-dashboard-slas")).toBeInTheDocument();
  });
});
