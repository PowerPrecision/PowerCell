/**
 * Criar um processo para um cliente EXISTENTE: o aviso está LIGADO.
 *
 * Bloco 1, ponto 5. O hook e o diálogo têm teste próprio; aqui prova-se a
 * ligação ao ecrã. O modal é o REAL; só a rede é falsa.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  createClientProcess: vi.fn(),
  createClient: vi.fn(),
  searchClients: vi.fn(),
  getClientActiveProcesses: vi.fn(),
}));
vi.mock("../../services/api", () => api);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

import CreateProcessModal from "../CreateProcessModal";

const ATIVOS = {
  data: {
    client_name: "Rita Faria",
    total: 2,
    processos: [
      { id: "p9", process_number: 77, status: "novo", status_label: "Novo", titular: "titular1", consultor_names: [] },
      { id: "p8", process_number: 60, status: "em_analise", status_label: "Em Análise", titular: "titular2", consultor_names: [] },
    ],
  },
};

function montar(props = {}) {
  return render(
    <MemoryRouter>
      <CreateProcessModal
        open
        onOpenChange={vi.fn()}
        onSuccess={vi.fn()}
        preSelectedClient={{ id: "c-rita", name: "Rita Faria" }}
        {...props}
      />
    </MemoryRouter>,
  );
}

const criar = () => fireEvent.click(screen.getByRole("button", { name: /Criar Processo/ }));

describe("CreateProcessModal — o aviso de processos activos", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.createClientProcess.mockResolvedValue({ data: { id: "pNovo", process_number: 500 } });
  });

  it("com processos activos pergunta ANTES de criar", async () => {
    api.getClientActiveProcesses.mockResolvedValue(ATIVOS);
    montar();

    criar();

    const dialogo = await screen.findByTestId("active-processes-dialog");
    expect(dialogo.textContent).toContain("2 processos activos");
    expect(api.createClientProcess).not.toHaveBeenCalled();
    expect(api.getClientActiveProcesses).toHaveBeenCalledWith("c-rita", undefined);
  });

  it("«Continuar mesmo assim» cria o processo", async () => {
    api.getClientActiveProcesses.mockResolvedValue(ATIVOS);
    montar();
    criar();

    const dialogo = await screen.findByTestId("active-processes-dialog");
    fireEvent.click(within(dialogo).getByRole("button", { name: /Continuar mesmo assim/ }));

    await waitFor(() =>
      expect(api.createClientProcess).toHaveBeenCalledWith(
        expect.objectContaining({ client_id: "c-rita" }),
      ),
    );
  });

  it("«Cancelar» no aviso não cria NADA", async () => {
    api.getClientActiveProcesses.mockResolvedValue(ATIVOS);
    montar();
    criar();

    const dialogo = await screen.findByTestId("active-processes-dialog");
    fireEvent.click(within(dialogo).getByRole("button", { name: "Cancelar" }));

    await waitFor(() => expect(screen.queryByTestId("active-processes-dialog")).toBeNull());
    expect(api.createClientProcess).not.toHaveBeenCalled();
  });

  it("sem processos activos cria logo (contraprova)", async () => {
    api.getClientActiveProcesses.mockResolvedValue({ data: { total: 0, processos: [] } });
    montar();

    criar();

    await waitFor(() => expect(api.createClientProcess).toHaveBeenCalled());
    expect(screen.queryByTestId("active-processes-dialog")).toBeNull();
  });
});
