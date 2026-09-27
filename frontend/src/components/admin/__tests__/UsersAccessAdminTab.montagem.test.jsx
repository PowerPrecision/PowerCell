/**
 * O separador Utilizadores MONTADO — a cobertura que faltava (Set 2026).
 *
 * Este ficheiro nasce de um erro em PRODUÇÃO: o painel de administração
 * rebentou com uma pilha de componentes cujo frame mais interno era esta
 * própria `UsersAccessAdminTab`, apanhada por um error boundary.
 *
 * O componente tem 789 linhas e NUNCA tinha sido montado num teste — o
 * único que o mencionava (`lib/queryClient.orgAdmin.test.js`) lê o
 * código-fonte para verificar a forma da chave de cache. É a regra que
 * já está escrita no AGENTS.md a propósito do `WebmailPage`: um
 * componente só está coberto quando alguém o MONTA.
 *
 * Os logs de produção mostram o painel a ser aberto SEM que
 * `/admin/users/paginated` fosse pedido uma única vez — o render morre
 * antes de os efeitos correrem. Daí o primeiro teste ser o mais
 * estúpido possível: montar e sobreviver.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../services/api", () => ({
  getAdminUsersPaginated: vi.fn(async () => ({
    data: { users: [], total: 0 },
  })),
  getUserCompanyRoles: vi.fn(async () => ({ data: [] })),
  getCompanies: vi.fn(async () => ({ data: [] })),
  getUserRoles: vi.fn(async () => ({ data: [] })),
  assignUserRole: vi.fn(),
  createUser: vi.fn(),
  deleteUser: vi.fn(),
  deleteUserCompanyRole: vi.fn(),
  updateUser: vi.fn(),
}));

import UsersAccessAdminTab from "../UsersAccessAdminTab";
import * as api from "../../../services/api";

function montar() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <UsersAccessAdminTab />
    </QueryClientProvider>,
  );
}

describe("UsersAccessAdminTab — montagem", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("monta sem rebentar", async () => {
    montar();
    expect(await screen.findByTestId("org-admin-users-tab")).toBeTruthy();
  });

  it("pede a lista paginada ao servidor (o render chega aos efeitos)", async () => {
    // É esta asserção que os logs de produção contradizem: o painel foi
    // aberto e o pedido nunca saiu.
    montar();
    await waitFor(() => {
      expect(api.getAdminUsersPaginated).toHaveBeenCalled();
    });
  });
});

/**
 * Formas que os dados REAIS tomam e as simuladas não tomam. Cada caso
 * aqui é uma forma que a API de produção pode devolver e que o painel
 * tem de aguentar — a lista nasceu de ler os normalizadores
 * (`organizationAdmin.js`) e de perguntar, por cada `||`, o que
 * acontece quando nenhum dos lados existe.
 */
describe("UsersAccessAdminTab — formas de dados de produção", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const CASOS = [
    ["utilizador sem nome nem email", { users: [{ id: "u1" }], total: 1 }, [], []],
    ["utilizador sem id", { users: [{ name: "Sem Id" }], total: 1 }, [], []],
    [
      "UCR sem nome de empresa (só company_id)",
      { users: [{ id: "u1", name: "A", email: "a@p.pt" }], total: 1 },
      [{ id: "r1", user_id: "u1", company_id: "cmp-1", role: "consultor" }],
      [],
    ],
    [
      "UCR sem cargo nenhum",
      { users: [{ id: "u1", name: "A", email: "a@p.pt" }], total: 1 },
      [{ id: "r1", user_id: "u1", company_id: "cmp-1" }],
      [],
    ],
    [
      "UCR com company aninhada em objecto",
      { users: [{ id: "u1", name: "A", email: "a@p.pt" }], total: 1 },
      [{ id: "r1", user_id: "u1", company: { id: "cmp-1", name: "Power" }, role: "diretor" }],
      [{ id: "cmp-1", name: "Power" }],
    ],
    [
      "empresa sem id",
      { users: [{ id: "u1", name: "A", email: "a@p.pt" }], total: 1 },
      [],
      [{ name: "Empresa Sem Id" }],
    ],
    [
      "dois UCR com o mesmo id (chave repetida)",
      { users: [{ id: "u1", name: "A", email: "a@p.pt" }], total: 1 },
      [
        { id: "r1", user_id: "u1", company_id: "cmp-1", role: "consultor" },
        { id: "r1", user_id: "u1", company_id: "cmp-2", role: "consultor" },
      ],
      [],
    ],
    [
      "total incoerente com a página (total 0 com utilizadores)",
      { users: [{ id: "u1", name: "A", email: "a@p.pt" }], total: 0 },
      [],
      [],
    ],
    [
      "payload aninhado em vez de array",
      { users: [{ id: "u1", name: "A", email: "a@p.pt" }], total: 1 },
      { roles: [{ id: "r1", user_id: "u1", company_id: "cmp-1", role: "ceo" }] },
      { companies: [{ id: "cmp-1", name: "Power" }] },
    ],
  ];

  it.each(CASOS)("aguenta: %s", async (_nome, pagina, papeis, empresas) => {
    api.getAdminUsersPaginated.mockResolvedValue({ data: pagina });
    api.getUserCompanyRoles.mockResolvedValue({ data: papeis });
    api.getCompanies.mockResolvedValue({ data: empresas });

    montar();

    expect(await screen.findByTestId("org-admin-users-tab")).toBeTruthy();
    await waitFor(() => {
      expect(api.getAdminUsersPaginated).toHaveBeenCalled();
    });
  });

  it("um erro do servidor não derruba o painel", async () => {
    api.getAdminUsersPaginated.mockRejectedValue(new Error("500"));
    api.getUserCompanyRoles.mockRejectedValue(new Error("500"));
    api.getCompanies.mockRejectedValue(new Error("500"));

    montar();

    expect(await screen.findByTestId("org-admin-users-tab")).toBeTruthy();
  });
});
