/**
 * Ligar um 2.º titular: o aviso «já tem processos activos» está LIGADO.
 *
 * Bloco 1, ponto 5. O hook e o diálogo têm teste próprio; o que este ficheiro
 * prova é a LIGAÇÃO ao ecrã que adiciona o cliente — apagar a chamada a
 * `confirmar` deixava o aviso a existir e a nunca aparecer, sem erro nenhum.
 * O cartão é o REAL; só a rede é falsa.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  searchClients: vi.fn(),
  updateProcess: vi.fn(),
  createClient: vi.fn(),
  getClientActiveProcesses: vi.fn(),
}));
vi.mock("../../services/api", () => api);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

import SecondTitularCard from "../SecondTitularCard";

const PROCESSO = { id: "pP", client_id: "c-principal", second_client_id: null };

const ATIVOS = {
  data: {
    client_name: "Rita Faria",
    total: 1,
    processos: [
      { id: "p9", process_number: 77, status: "novo", status_label: "Novo", titular: "titular1", consultor_names: [] },
    ],
  },
};

async function abrirEEscolherCliente() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <SecondTitularCard process={PROCESSO} onUpdate={vi.fn()} financialData={null} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole("button", { name: /Adicionar \/ Ligar 2º Titular/ }));
  fireEvent.change(screen.getByPlaceholderText(/Pesquisar por nome/), { target: { value: "rita" } });
  const resultado = await screen.findByText("Rita Faria");
  fireEvent.click(resultado.closest("button"));
}

describe("SecondTitularCard — o aviso de processos activos", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.searchClients.mockResolvedValue({ data: { results: [{ id: "c-rita", nome: "Rita Faria", email: "r@x.pt" }] } });
    api.updateProcess.mockResolvedValue({ data: {} });
  });

  it("com processos activos pergunta ANTES de ligar — e não liga enquanto não houver resposta", async () => {
    api.getClientActiveProcesses.mockResolvedValue(ATIVOS);

    await abrirEEscolherCliente();

    expect(await screen.findByTestId("active-processes-dialog")).toBeTruthy();
    expect(api.updateProcess).not.toHaveBeenCalled();
    // O processo a que o cliente é ligado não conta para o aviso.
    expect(api.getClientActiveProcesses).toHaveBeenCalledWith("c-rita", "pP");
  });

  it("«Continuar mesmo assim» liga o 2.º titular", async () => {
    api.getClientActiveProcesses.mockResolvedValue(ATIVOS);
    await abrirEEscolherCliente();

    fireEvent.click(await screen.findByRole("button", { name: /Continuar mesmo assim/ }));

    await waitFor(() =>
      expect(api.updateProcess).toHaveBeenCalledWith("pP", { second_client_id: "c-rita" }),
    );
  });

  it("«Cancelar» não liga NADA", async () => {
    api.getClientActiveProcesses.mockResolvedValue(ATIVOS);
    await abrirEEscolherCliente();

    fireEvent.click(await screen.findByRole("button", { name: "Cancelar" }));

    await waitFor(() => expect(screen.queryByTestId("active-processes-dialog")).toBeNull());
    expect(api.updateProcess).not.toHaveBeenCalled();
  });

  it("sem processos activos liga logo, sem diálogo (contraprova)", async () => {
    api.getClientActiveProcesses.mockResolvedValue({ data: { total: 0, processos: [] } });

    await abrirEEscolherCliente();

    await waitFor(() =>
      expect(api.updateProcess).toHaveBeenCalledWith("pP", { second_client_id: "c-rita" }),
    );
    expect(screen.queryByTestId("active-processes-dialog")).toBeNull();
  });
});
