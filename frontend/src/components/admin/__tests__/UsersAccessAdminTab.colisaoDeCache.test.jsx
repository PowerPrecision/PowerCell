/**
 * `TypeError: companies is not iterable` — DUAS queries, UMA chave, formas
 * incompatíveis (erro de produção, Set 2026).
 *
 * O Sentry apontou para este `useMemo`:
 *
 *     ve=f.useMemo(()=>{const a={};for(const d of H)...
 *     // companyNameById: const map = {}; for (const company of companies)
 *
 * `companies` não era iterável. Não porque a query deste separador devolva
 * algo estranho — `normalizeCompaniesPayload` devolve SEMPRE um array — mas
 * porque o valor em cache foi escrito por OUTRO componente:
 *
 *   CompaniesAdminTab   chave `companies(pesquisa, pagina)` → {empresas, total}
 *   UsersAccessAdminTab chave `companies("")`               → array
 *
 * e `companies(search, page)` = [...companiesAll(), search ?? '', page ?? 1],
 * pelo que `companies("")` e `companies("", 1)` são **a mesma chave**. Os dois
 * separadores vivem no MESMO `SystemAdminPanel`, logo no mesmo `QueryClient`:
 * quem chega primeiro decide a forma e o segundo recebe a do outro.
 *
 * Os dois sentidos não são simétricos, e a diferença é instrutiva:
 *   Empresas → Utilizadores: o `for...of` corre no RENDER, logo rebenta
 *   antes de qualquer refetch — TypeError, ecrã apanhado pelo error boundary.
 *   Utilizadores → Empresas: o `pagemento?.empresas` é seguro, dá `[]` e a
 *   lista aparece vazia — mas só até o refetch da montagem responder, que
 *   reescreve a entrada com a forma certa. É um piscar, não um erro.
 *
 * **O `|| []` não serve, e a razão é contra-intuitiva:** um objecto é
 * *truthy*, logo `companies || []` devolve o objecto. O
 * `companiesForNewAccess` JÁ tinha esse `|| []` e, com a colisão de chaves
 * presente, a mutação medida dá
 *
 *     TypeError: (companies || []).filter is not a function
 *
 * — o erro MUDA de sítio em vez de desaparecer. Só `Array.isArray` distingue,
 * e mesmo assim o próximo consumidor sem guarda volta a rebentar (`find` no
 * `handleAddAccess`). A correcção é a chave, não o fallback. A guarda no
 * `companyNameById` fica como segunda linha de defesa, e esta mutação é a
 * prova de que ela não basta sozinha.
 *
 * Por isso este teste monta os DOIS separadores no mesmo `QueryClient` — é a
 * única montagem que reproduz o defeito. Os testes que montam um componente
 * sozinho, com a sua própria cache, passam com o defeito presente (os meus
 * passaram).
 */
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../services/api", () => ({
  // A MESMA função serve os dois separadores, e responde conforme os
  // argumentos — tal como o backend.
  getCompanies: vi.fn(async (search, paginacao) =>
    paginacao?.page
      ? { data: { companies: [{ id: "cmp-1", name: "Power" }], total: 1 } }
      : { data: [{ id: "cmp-1", name: "Power" }] },
  ),
  getAdminUsersPaginated: vi.fn(async () => ({
    data: { users: [{ id: "u1", name: "Ana", email: "ana@power.pt" }], total: 1 },
  })),
  getUserCompanyRoles: vi.fn(async () => ({ data: [] })),
  getUserRoles: vi.fn(async () => ({ data: [] })),
  assignUserRole: vi.fn(),
  createUser: vi.fn(),
  deleteUser: vi.fn(),
  deleteUserCompanyRole: vi.fn(),
  updateUser: vi.fn(),
  createCompany: vi.fn(),
  updateCompany: vi.fn(),
  deleteCompany: vi.fn(),
  getCompanyNetworks: vi.fn(async () => ({ data: [] })),
  uploadCompanyLogo: vi.fn(),
}));

import UsersAccessAdminTab from "../UsersAccessAdminTab";
import CompaniesAdminTab from "../CompaniesAdminTab";

function clienteUnico() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

describe("os dois separadores do painel partilham o QueryClient", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("Empresas primeiro, Utilizadores depois: o segundo não rebenta", async () => {
    const queryClient = clienteUnico();

    // 1. O separador Empresas escreve a SUA forma na cache.
    const empresas = render(
      <QueryClientProvider client={queryClient}>
        <CompaniesAdminTab />
      </QueryClientProvider>,
    );
    await waitFor(() => {
      expect(queryClient.getQueryData(["org-admin", "companies", "", 1])).toBeTruthy();
    });
    empresas.unmount();

    // 2. O separador Utilizadores lê a cache já preenchida.
    render(
      <QueryClientProvider client={queryClient}>
        <UsersAccessAdminTab />
      </QueryClientProvider>,
    );

    expect(await screen.findByTestId("org-admin-users-tab")).toBeTruthy();
    expect(await screen.findByTestId("user-row-u1")).toBeTruthy();
  });

  it("e continua a VER as empresas — não basta não rebentar", async () => {
    // Um `|| []` fazia o primeiro teste passar com o Select vazio e o
    // administrador sem conseguir atribuir um acesso.
    const queryClient = clienteUnico();

    const empresas = render(
      <QueryClientProvider client={queryClient}>
        <CompaniesAdminTab />
      </QueryClientProvider>,
    );
    await waitFor(() => {
      expect(queryClient.getQueryData(["org-admin", "companies", "", 1])).toBeTruthy();
    });
    empresas.unmount();

    render(
      <QueryClientProvider client={queryClient}>
        <UsersAccessAdminTab />
      </QueryClientProvider>,
    );
    await screen.findByTestId("user-row-u1");

    const { getByTestId } = screen;
    await waitFor(() => {
      expect(getByTestId("btn-user-actions-u1")).toBeTruthy();
    });
    // O Select de empresas do Sheet só existe com o Sheet aberto; a prova
    // directa e estável é a cache deste separador ter a forma DELE.
    const doSelector = queryClient
      .getQueryCache()
      .getAll()
      .find((q) => q.queryKey[1] === "companies" && Array.isArray(q.state.data));
    expect(doSelector, "o separador Utilizadores tem de ter a sua própria entrada, em array").toBeTruthy();
    expect(doSelector.state.data).toHaveLength(1);
  });

  it("Utilizadores primeiro, Empresas depois: a lista de empresas não fica vazia", async () => {
    // O sentido inverso não rebenta: o acesso é opcional e o refetch da
    // montagem corrige a forma. Fica coberto para o caso de alguém "optimizar"
    // o refetch (um `staleTime` alto) e o piscar passar a ser permanente.
    const queryClient = clienteUnico();

    const utilizadores = render(
      <QueryClientProvider client={queryClient}>
        <UsersAccessAdminTab />
      </QueryClientProvider>,
    );
    await screen.findByTestId("user-row-u1");
    utilizadores.unmount();

    render(
      <QueryClientProvider client={queryClient}>
        <CompaniesAdminTab />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Power")).toBeTruthy();
  });
});
