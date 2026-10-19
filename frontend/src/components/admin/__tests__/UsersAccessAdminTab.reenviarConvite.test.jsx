/**
 * «Reenviar Convite» no menu de três pontos de cada utilizador (QA-9).
 *
 * O servidor gera uma palavra-passe nova e só a troca se o email sair; o ecrã pede confirmação
 * (a palavra-passe actual deixa de funcionar), mostra a causa quando falha e nunca oferece a
 * acção a quem não tem acesso (conta de parceiro, conta desactivada).
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("../../../services/api", () => ({
  getAdminUsersPaginated: vi.fn(),
  getUserCompanyRoles: vi.fn(async () => ({ data: [] })),
  getCompanies: vi.fn(async () => ({ data: [] })),
  getUserRoles: vi.fn(async () => ({ data: [] })),
  assignUserRole: vi.fn(),
  createUser: vi.fn(),
  deleteUser: vi.fn(),
  deleteUserCompanyRole: vi.fn(),
  updateUser: vi.fn(),
  resendUserInvite: vi.fn(),
}));

import { toast } from "sonner";
import UsersAccessAdminTab from "../UsersAccessAdminTab";
import * as api from "../../../services/api";

const UTILIZADORES = [
  { id: "u1", name: "Ana Alves", email: "ana@precision.pt", role: "consultor", is_active: true },
  { id: "u2", name: "Bruno Brito", email: "bruno@precision.pt", role: "consultor", is_active: false },
  { id: "u3", name: "Parceiro Fantasma", email: "p@placeholder.internal", role: "parceiro", is_active: true },
];

function montar() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <UsersAccessAdminTab />
    </QueryClientProvider>,
  );
}

async function abrirMenu(id) {
  await userEvent.click(await screen.findByTestId(`btn-user-actions-${id}`));
}

describe("Reenviar Convite — menu de acções do utilizador", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getAdminUsersPaginated.mockResolvedValue({ data: { users: UTILIZADORES, total: 3 } });
    api.resendUserInvite.mockResolvedValue({ data: { success: true, email: "ana@precision.pt" } });
  });

  it("pede confirmação, reenvia ao utilizador certo e avisa o destino", async () => {
    montar();
    await abrirMenu("u1");
    await userEvent.click(await screen.findByRole("menuitem", { name: /Reenviar Convite/ }));

    const dialogo = await screen.findByTestId("dialogo-reenviar-convite");
    expect(within(dialogo).getByText(/palavra-passe nova/)).toBeInTheDocument();
    // Ainda nada foi pedido ao servidor: a confirmação é o gesto.
    expect(api.resendUserInvite).not.toHaveBeenCalled();

    await userEvent.click(within(dialogo).getByRole("button", { name: "Reenviar convite" }));
    await waitFor(() => expect(api.resendUserInvite).toHaveBeenCalledWith("u1"));
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith("Convite reenviado para ana@precision.pt"),
    );
    await waitFor(() => expect(screen.queryByTestId("dialogo-reenviar-convite")).toBeNull());
  });

  it("cancelar não pede nada ao servidor", async () => {
    montar();
    await abrirMenu("u1");
    await userEvent.click(await screen.findByRole("menuitem", { name: /Reenviar Convite/ }));
    const dialogo = await screen.findByTestId("dialogo-reenviar-convite");
    await userEvent.click(within(dialogo).getByRole("button", { name: "Cancelar" }));
    expect(api.resendUserInvite).not.toHaveBeenCalled();
  });

  it("uma falha mostra a causa do servidor e o diálogo fica aberto para tentar de novo", async () => {
    api.resendUserInvite.mockRejectedValue({
      response: { data: { detail: "Não foi possível enviar o email. A palavra-passe do utilizador não foi alterada." } },
    });
    montar();
    await abrirMenu("u1");
    await userEvent.click(await screen.findByRole("menuitem", { name: /Reenviar Convite/ }));
    await userEvent.click(
      within(await screen.findByTestId("dialogo-reenviar-convite")).getByRole("button", { name: "Reenviar convite" }),
    );
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(expect.stringContaining("não foi alterada")),
    );
    expect(screen.getByTestId("dialogo-reenviar-convite")).toBeInTheDocument();
  });

  it("não oferece a acção a uma conta desactivada", async () => {
    montar();
    await abrirMenu("u2");
    const item = await screen.findByRole("menuitem", { name: /Reenviar Convite/ });
    expect(item).toHaveAttribute("aria-disabled", "true");
  });

  it("não oferece a acção a uma conta de parceiro sem acesso", async () => {
    montar();
    await abrirMenu("u3");
    await screen.findByRole("menuitem", { name: /Editar Dados/ });
    expect(screen.queryByRole("menuitem", { name: /Reenviar Convite/ })).toBeNull();
  });
});
