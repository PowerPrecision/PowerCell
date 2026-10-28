/**
 * Pedido de alteração de atribuição (Out 2026): o Index pede à chefia com um motivo opcional; a chefia vê
 * os pedidos na «Supervisão do Index» e fecha-os («Tratado» / «Recusar»).
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../services/api", () => ({
  getPedidosDeAtribuicao: vi.fn(),
  pedirAlteracaoDeAtribuicao: vi.fn(),
  resolverPedidoDeAtribuicao: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { toast } from "sonner";
import {
  getPedidosDeAtribuicao,
  pedirAlteracaoDeAtribuicao,
  resolverPedidoDeAtribuicao,
} from "../../../services/api";
import { PedirAlteracaoDeAtribuicao } from "../PedirAlteracaoDeAtribuicao";
import { PedidosDeAtribuicaoCard } from "../PedidosDeAtribuicaoCard";

function montar(ui) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

const PEDIDO = {
  id: "ped-1", process_id: "proc-9", process_number: 42, client_name: "Ana Lopes",
  requested_by_name: "Ivo Index", created_at: "2026-10-28T10:00:00+00:00", motivo: "É de outro balcão",
};

beforeEach(() => {
  vi.clearAllMocks();
  getPedidosDeAtribuicao.mockResolvedValue({ data: { itens: [] } });
  pedirAlteracaoDeAtribuicao.mockResolvedValue({ data: { success: true } });
  resolverPedidoDeAtribuicao.mockResolvedValue({ data: { success: true } });
});

describe("PedirAlteracaoDeAtribuicao (Index)", () => {
  it("envia o pedido com o motivo escrito", async () => {
    montar(<PedirAlteracaoDeAtribuicao processId="proc-9" />);
    await userEvent.click(await screen.findByTestId("botao-pedir-alteracao-atribuicao"));
    await userEvent.type(screen.getByTestId("motivo-pedido-atribuicao"), "  Tenho processos a mais ");
    await userEvent.click(screen.getByTestId("enviar-pedido-atribuicao"));
    await waitFor(() => expect(pedirAlteracaoDeAtribuicao).toHaveBeenCalledWith("proc-9", "Tenho processos a mais"));
    expect(getPedidosDeAtribuicao).toHaveBeenCalledWith({ estado: "pendente", process_id: "proc-9" });
  });

  it("o motivo é opcional", async () => {
    montar(<PedirAlteracaoDeAtribuicao processId="proc-9" />);
    await userEvent.click(await screen.findByTestId("botao-pedir-alteracao-atribuicao"));
    await userEvent.click(screen.getByTestId("enviar-pedido-atribuicao"));
    await waitFor(() => expect(pedirAlteracaoDeAtribuicao).toHaveBeenCalledWith("proc-9", ""));
  });

  it("com um pedido pendente mostra «Pedido de alteração enviado» em vez do botão", async () => {
    getPedidosDeAtribuicao.mockResolvedValue({ data: { itens: [PEDIDO] } });
    montar(<PedirAlteracaoDeAtribuicao processId="proc-9" />);
    expect(await screen.findByTestId("pedido-atribuicao-pendente")).toHaveTextContent("Pedido de alteração enviado");
    expect(screen.queryByTestId("botao-pedir-alteracao-atribuicao")).not.toBeInTheDocument();
  });

  it("uma recusa do servidor mostra o motivo dele", async () => {
    pedirAlteracaoDeAtribuicao.mockRejectedValue({ response: { data: { detail: "Já tem um pedido pendente." } } });
    montar(<PedirAlteracaoDeAtribuicao processId="proc-9" />);
    await userEvent.click(await screen.findByTestId("botao-pedir-alteracao-atribuicao"));
    await userEvent.click(screen.getByTestId("enviar-pedido-atribuicao"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Já tem um pedido pendente."));
  });
});

describe("PedidosDeAtribuicaoCard (chefia)", () => {
  it("sem pedidos não aparece", async () => {
    montar(<PedidosDeAtribuicaoCard />);
    await waitFor(() => expect(getPedidosDeAtribuicao).toHaveBeenCalled());
    expect(screen.queryByTestId("pedidos-de-atribuicao")).not.toBeInTheDocument();
  });

  it("lista o pedido com o motivo e fecha-o como tratado", async () => {
    getPedidosDeAtribuicao.mockResolvedValue({ data: { itens: [PEDIDO] } });
    montar(<PedidosDeAtribuicaoCard />);
    expect(await screen.findByText("É de outro balcão")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /#42 · Ana Lopes/ })).toHaveAttribute("href", "/processo/proc-9");
    await userEvent.click(screen.getByRole("button", { name: /Tratado/ }));
    await waitFor(() => expect(resolverPedidoDeAtribuicao).toHaveBeenCalledWith("ped-1", "concluido", undefined));
  });
});
