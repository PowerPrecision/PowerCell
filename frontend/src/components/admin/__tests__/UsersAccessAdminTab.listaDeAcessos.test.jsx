/**
 * "Acessos actuais" com muitos acessos — a lista tem de ter ELEVADOR.
 *
 * A lista estava num `ScrollArea` com o limite de altura (`max-h-[240px]`)
 * posto na ROOT. A Root tem `overflow-hidden` e o Viewport `h-full`: com a
 * altura da Root em auto, o viewport cresce com o conteúdo, o Radix não
 * desenha barra e a Root corta (ou, sem o corte, a lista cresce e parte o
 * layout da gaveta). Hoje é um contentor nativo `max-h-64 overflow-y-auto`:
 * a barra aparece sempre que há mais acessos do que cabem.
 *
 * O jsdom não calcula alturas — afirma-se a REGRA (as classes que dão o
 * limite e o scroll, no elemento que contém as linhas) e que NENHUM
 * antepassado das linhas corta o excedente.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../services/api", () => ({
  getAdminUsersPaginated: vi.fn(),
  getUserCompanyRoles: vi.fn(async () => ({ data: [] })),
  getCompanies: vi.fn(async () => ({ data: [] })),
  getUserRoles: vi.fn(),
  assignUserRole: vi.fn(),
  createUser: vi.fn(),
  deleteUser: vi.fn(),
  deleteUserCompanyRole: vi.fn(),
  updateUser: vi.fn(),
}));

import UsersAccessAdminTab from "../UsersAccessAdminTab";
import * as api from "../../../services/api";

const UTILIZADOR = { id: "u1", name: "Ana Alves", email: "ana@power.pt", is_active: true };

const acessos = (n) =>
  Array.from({ length: n }, (_, i) => ({
    id: `r${i}`,
    user_id: "u1",
    company_id: `cmp-${i}`,
    company_name: `Empresa ${i}`,
    role: "consultor",
  }));

async function abrirGaveta() {
  const utilizador = userEvent.setup();
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <UsersAccessAdminTab />
    </QueryClientProvider>,
  );
  await utilizador.click(await screen.findByTestId("btn-user-actions-u1"));
  await utilizador.click(await screen.findByRole("menuitem", { name: /gerir acessos ucr/i }));
  return screen.findByTestId("ucr-list-scroll");
}

describe("Acessos actuais — lista com limite de altura e scroll", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getAdminUsersPaginated.mockResolvedValue({ data: { users: [UTILIZADOR], total: 1 } });
    api.getUserRoles.mockResolvedValue({ data: acessos(40) });
  });

  it("o contentor das linhas limita a altura e faz scroll vertical", async () => {
    const lista = await abrirGaveta();

    expect(lista.className).toContain("max-h-64");
    expect(lista.className).toContain("overflow-y-auto");
    // Todas as linhas estão LÁ dentro (alcançáveis pelo scroll, não cortadas).
    expect(within(lista).getAllByTestId(/^ucr-row-/)).toHaveLength(40);
  });

  it("nenhum antepassado da lista corta o excedente (a armadilha do ScrollArea)", async () => {
    const lista = await abrirGaveta();
    const gaveta = screen.getByTestId("user-access-sheet");

    for (let no = lista.parentElement; no && no !== gaveta; no = no.parentElement) {
      expect(no.className).not.toMatch(/overflow-hidden/);
    }
  });

  it("uma lista vazia diz-se, sem contentor de scroll", async () => {
    api.getUserRoles.mockResolvedValue({ data: [] });
    const utilizador = userEvent.setup();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <UsersAccessAdminTab />
      </QueryClientProvider>,
    );
    await utilizador.click(await screen.findByTestId("btn-user-actions-u1"));
    await utilizador.click(await screen.findByRole("menuitem", { name: /gerir acessos ucr/i }));

    expect(await screen.findByText(/ainda não tem nenhum acesso ucr/i)).toBeTruthy();
    expect(screen.queryByTestId("ucr-list-scroll")).toBeNull();
  });
});
