/**
 * Que empresa mostra o ecrã das Configurações — a PÁGINA montada.
 *
 * Bloco 1, ponto 3. O ADMIN configura todas as empresas do CRM e o CEO só
 * as dele; quem decide é o servidor (`GET /system-config/companies` já vem
 * filtrado) e o ecrã só escolhe de entre o que vier.
 *
 * A forma dos dados é a REAL (`{companies, total}` e `{config, fields}`) e
 * os valores do fixture são diferentes das omissões.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const auth = { effectiveCompanyId: null, user: { id: "u1", name: "A", role: "admin" } };
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ token: "t", ...auth }),
}));

const apiMock = vi.hoisted(() => ({
  getSystemConfigCompanies: vi.fn(),
  getSystemConfig: vi.fn(async () => ({ data: { config: {} } })),
  updateSystemConfigSection: vi.fn(async () => ({ data: {} })),
}));
vi.mock("../../services/api", () => apiMock);

import SystemConfigPage from "../SystemConfigPage";

const LISTA_ADMIN = {
  companies: [
    { company_id: "default", company_name: "Global (Padrão)" },
    { company_id: "cmp-power", company_name: "Power Real Estate" },
    { company_id: "cmp-domus", company_name: "Domus" },
  ],
  total: 3,
};

const RESPOSTA = {
  config: { storage: { provider: "s3" } },
  fields: {
    storage: {
      title: "Armazenamento",
      description: "Provedor de ficheiros",
      fields: [{ key: "provider", label: "Provedor", type: "text" }],
    },
  },
};

let urlsPedidos;

function montar() {
  return render(
    <MemoryRouter initialEntries={["/configuracoes?tab=storage"]}>
      <SystemConfigPage embedded />
    </MemoryRouter>,
  );
}

describe("SystemConfigPage — a empresa cuja configuração se mostra", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    urlsPedidos = [];
    auth.effectiveCompanyId = null;
    auth.user = { id: "u1", name: "A", role: "admin" };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url) => {
        urlsPedidos.push(String(url));
        return { ok: true, json: async () => RESPOSTA };
      }),
    );
  });

  const pedidosDeConfig = () => urlsPedidos.filter((u) => /\/api\/system-config\?company_id=/.test(u));

  it("o ADMIN vê o selector com TODAS as empresas do CRM", async () => {
    apiMock.getSystemConfigCompanies.mockResolvedValue({ data: LISTA_ADMIN });
    montar();

    const seletor = await screen.findByRole("combobox", { name: /empresa/i });
    const opcoes = Array.from(seletor.querySelectorAll("option")).map((o) => o.value);
    expect(opcoes).toEqual(["default", "cmp-power", "cmp-domus"]);
  });

  it("escolher outra empresa pede a configuração DESSA empresa", async () => {
    apiMock.getSystemConfigCompanies.mockResolvedValue({ data: LISTA_ADMIN });
    montar();

    const seletor = await screen.findByRole("combobox", { name: /empresa/i });
    await waitFor(() => expect(pedidosDeConfig().length).toBeGreaterThan(0));
    fireEvent.change(seletor, { target: { value: "cmp-domus" } });

    await waitFor(() =>
      expect(pedidosDeConfig().some((u) => u.includes("company_id=cmp-domus"))).toBe(true),
    );
  });

  it("um CEO com uma só empresa NÃO vê selector", async () => {
    auth.user = { id: "u2", name: "C", role: "ceo" };
    auth.effectiveCompanyId = "cmp-power";
    apiMock.getSystemConfigCompanies.mockResolvedValue({
      data: {
        companies: [
          { company_id: "default", company_name: "Global (Padrão)" },
        ],
        total: 1,
      },
    });
    montar();

    await screen.findByTestId("config-section-generica");
    expect(screen.queryByRole("combobox", { name: /empresa/i })).toBeNull();
  });

  it("o CEO da ilha abre na empresa DELE e nunca pede a global (era um 403 e um toast)", async () => {
    auth.user = { id: "u3", name: "D", role: "ceo" };
    auth.effectiveCompanyId = null;
    apiMock.getSystemConfigCompanies.mockResolvedValue({
      data: { companies: [{ company_id: "cmp-domus", company_name: "Domus" }], total: 1 },
    });
    montar();

    await waitFor(() => expect(pedidosDeConfig().length).toBeGreaterThan(0));
    expect(pedidosDeConfig().every((u) => u.includes("company_id=cmp-domus"))).toBe(true);
    expect(pedidosDeConfig().some((u) => u.includes("company_id=default"))).toBe(false);
  });

  describe("a configuração GLOBAL é exclusiva do administrador", () => {
    const SECCOES_GLOBAIS = ["nav-dashboard-slas", "nav-mandatory-documents", "nav-maintenance", "nav-portal", "nav-changelog"];

    it("o ADMIN vê as secções dedicadas (globais) na navegação", async () => {
      apiMock.getSystemConfigCompanies.mockResolvedValue({ data: LISTA_ADMIN });
      montar();
      await screen.findByTestId("config-section-generica");
      for (const id of SECCOES_GLOBAIS) {
        expect(screen.getByTestId(id), id).toBeTruthy();
      }
    });

    it("o CEO NÃO vê nenhuma — nem nos chips nem na barra lateral", async () => {
      auth.user = { id: "u2", name: "C", role: "ceo" };
      auth.effectiveCompanyId = "cmp-power";
      apiMock.getSystemConfigCompanies.mockResolvedValue({
        data: { companies: [{ company_id: "cmp-power", company_name: "Power" }], total: 1 },
      });
      montar();
      await screen.findByTestId("config-section-generica");
      for (const id of SECCOES_GLOBAIS) {
        expect(screen.queryByTestId(id), id).toBeNull();
        expect(screen.queryByTestId(id.replace("nav-", "chip-")), id).toBeNull();
      }
    });

    it("um ?tab= antigo para uma secção global diz-se ao CEO, em vez de abrir um ecrã de erros", async () => {
      auth.user = { id: "u2", name: "C", role: "ceo" };
      auth.effectiveCompanyId = "cmp-power";
      apiMock.getSystemConfigCompanies.mockResolvedValue({
        data: { companies: [{ company_id: "cmp-power", company_name: "Power" }], total: 1 },
      });
      render(
        <MemoryRouter initialEntries={["/configuracoes?tab=dashboard_slas"]}>
          <SystemConfigPage embedded />
        </MemoryRouter>,
      );
      expect(await screen.findByTestId("config-seccao-reservada")).toBeTruthy();
      expect(screen.queryByTestId("sla-thresholds-section")).toBeNull();
    });
  });

  it("espera pela lista ANTES do primeiro pedido de configuração", async () => {
    let libertar;
    apiMock.getSystemConfigCompanies.mockReturnValue(
      new Promise((resolve) => {
        libertar = () => resolve({ data: LISTA_ADMIN });
      }),
    );
    montar();

    // A lista ainda não chegou: nenhum pedido de configuração pode ter saído.
    await new Promise((r) => setTimeout(r, 30));
    expect(pedidosDeConfig()).toEqual([]);

    libertar();
    await waitFor(() => expect(pedidosDeConfig().length).toBeGreaterThan(0));
  });

  it("sem lista (pedido falhado) o ecrã funciona como sempre", async () => {
    apiMock.getSystemConfigCompanies.mockRejectedValue(new Error("rede"));
    auth.effectiveCompanyId = "cmp-power";
    montar();

    await screen.findByTestId("config-section-generica");
    expect(pedidosDeConfig().some((u) => u.includes("company_id=cmp-power"))).toBe(true);
    expect(screen.queryByRole("combobox", { name: /empresa/i })).toBeNull();
  });
});
