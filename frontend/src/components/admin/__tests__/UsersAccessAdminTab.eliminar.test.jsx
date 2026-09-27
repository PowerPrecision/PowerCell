/**
 * Eliminar com janela de desfazer — a remoção optimista escrevia numa
 * chave de cache que NINGUÉM lê (Set 2026).
 *
 * O componente LÊ `queryKeys.orgAdmin.usersPaginated(pesquisa, pagina)`
 * = `['org-admin','users','paginated', …]` e ESCREVIA em
 * `queryKeys.orgAdmin.users()` = `['org-admin','users']`.
 *
 * `invalidateQueries` casa por PREFIXO, por isso a invalidação sempre
 * funcionou e ninguém deu pelo defeito. O `setQueryData` casa por chave
 * EXACTA: criava uma entrada fantasma e o ecrã não mexia. Três
 * consequências, todas invisíveis num teste que não monte a tabela:
 *   1. clicar Eliminar não retirava a linha (só 8s depois, no commit);
 *   2. "Desfazer" não repunha nada — o que salvava o utilizador de ser
 *      apagado era só o `clearTimeout`;
 *   3. se o servidor recusasse, o `restoreUser()` não devolvia a linha.
 *
 * Mesma família do `build_company_scope_condition`: cada metade
 * correcta, a combinação não.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../services/api", () => ({
  getAdminUsersPaginated: vi.fn(),
  getUserCompanyRoles: vi.fn(async () => ({ data: [] })),
  getCompanies: vi.fn(async () => ({ data: [] })),
  getUserRoles: vi.fn(async () => ({ data: [] })),
  assignUserRole: vi.fn(),
  createUser: vi.fn(),
  deleteUser: vi.fn(async () => ({ data: {} })),
  deleteUserCompanyRole: vi.fn(),
  updateUser: vi.fn(),
}));

import UsersAccessAdminTab from "../UsersAccessAdminTab";
import * as api from "../../../services/api";

const UTILIZADORES = [
  { id: "u1", name: "Ana Alves", email: "ana@power.pt", is_active: true },
  { id: "u2", name: "Bruno Brito", email: "bruno@power.pt", is_active: true },
];

function montar() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <UsersAccessAdminTab />
    </QueryClientProvider>,
  );
  return queryClient;
}

async function eliminar(utilizador, id) {
  await utilizador.click(await screen.findByTestId(`btn-user-actions-${id}`));
  await utilizador.click(await screen.findByTestId(`btn-delete-user-${id}`));
}

describe("Eliminar utilizador — remoção optimista", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getAdminUsersPaginated.mockResolvedValue({
      data: { users: UTILIZADORES, total: UTILIZADORES.length },
    });
  });

  it("a linha sai da tabela imediatamente", async () => {
    const utilizador = userEvent.setup();
    montar();

    expect(await screen.findByTestId("user-row-u1")).toBeTruthy();

    await eliminar(utilizador, "u1");

    // Sem esperar pelos 8s do commit: é isto que o utilizador vê.
    await waitFor(() => {
      expect(screen.queryByTestId("user-row-u1")).toBeNull();
    });
    // E só essa — eliminar um não pode limpar a tabela.
    expect(screen.getByTestId("user-row-u2")).toBeTruthy();
  });

  it("o total da paginação desce com a linha", async () => {
    // Retirar a linha e deixar o total a dizer "2 utilizadores" mostrava
    // uma contagem que não corresponde ao que está no ecrã.
    const utilizador = userEvent.setup();
    montar();
    await screen.findByTestId("user-row-u1");

    await eliminar(utilizador, "u1");

    await waitFor(() => {
      expect(screen.getByTestId("paginacao-intervalo").textContent).toContain(
        "1–1 de 1 utilizadores",
      );
    });
  });

  it("não chama o servidor antes de a janela de desfazer fechar", async () => {
    const utilizador = userEvent.setup();
    montar();
    await screen.findByTestId("user-row-u1");

    await eliminar(utilizador, "u1");

    expect(api.deleteUser).not.toHaveBeenCalled();
  });
});
