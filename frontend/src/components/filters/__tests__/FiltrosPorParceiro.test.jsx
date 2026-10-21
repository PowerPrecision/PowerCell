/**
 * P4 — o filtro «Por Parceiro» nas grelhas de Clientes e de Processos.
 *
 * As opções vêm de /partners/options (os parceiros do Portal não estão na lista de utilizadores) e
 * o filtro só existe quando a página o liga: sem `onParceiroChange` não há select nem pedido.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../../services/api", () => ({
  getPartnerOptions: vi.fn(),
  getUsers: vi.fn(() => Promise.resolve({ data: [] })),
  getWorkflowStatuses: vi.fn(() => Promise.resolve({ data: [] })),
}));

import * as api from "../../../services/api";
import ClientFilters from "../ClientFilters";
import ProcessFilters from "../ProcessFilters";

const PARCEIROS = { data: { partners: [{ id: "pt-1", name: "Rui Parceiro" }, { id: "pt-2", name: "Sara Parceira" }] } };

function montar(ui) {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={cliente}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getPartnerOptions.mockResolvedValue(PARCEIROS);
});

describe("ClientFilters — Por Parceiro", () => {
  it("oferece os parceiros e emite o id escolhido", async () => {
    const aoMudar = vi.fn();
    montar(<ClientFilters parceiro="all" onParceiroChange={aoMudar} />);
    await userEvent.click(screen.getByTestId("client-parceiro-filter"));
    await userEvent.click(await screen.findByRole("option", { name: "Sara Parceira" }));
    expect(aoMudar).toHaveBeenCalledWith("pt-2");
  });

  it("«Todos os parceiros» emite vazio (limpa o filtro)", async () => {
    const aoMudar = vi.fn();
    montar(<ClientFilters parceiro="pt-1" onParceiroChange={aoMudar} />);
    await userEvent.click(screen.getByTestId("client-parceiro-filter"));
    await userEvent.click(await screen.findByRole("option", { name: "Todos os parceiros" }));
    expect(aoMudar).toHaveBeenCalledWith("");
  });

  it("um parceiro escolhido activa o «Limpar Filtros»", () => {
    montar(<ClientFilters parceiro="pt-1" onParceiroChange={vi.fn()} />);
    expect(screen.getByTestId("client-filters-reset")).toBeEnabled();
  });

  it("sem parceiro escolhido o «Limpar Filtros» continua desactivado", () => {
    montar(<ClientFilters parceiro="all" onParceiroChange={vi.fn()} />);
    expect(screen.getByTestId("client-filters-reset")).toBeDisabled();
  });

  it("sem onParceiroChange não há select nem pedido de parceiros", async () => {
    montar(<ClientFilters />);
    expect(screen.queryByTestId("client-parceiro-filter")).toBeNull();
    await new Promise((r) => setTimeout(r, 30));
    expect(api.getPartnerOptions).not.toHaveBeenCalled();
  });

  it("uma resposta com forma inesperada vale lista vazia e não rebenta", async () => {
    api.getPartnerOptions.mockResolvedValue({ data: { partners: { id: "x" } } });
    montar(<ClientFilters parceiro="all" onParceiroChange={vi.fn()} />);
    await userEvent.click(screen.getByTestId("client-parceiro-filter"));
    expect(await screen.findByRole("option", { name: "Todos os parceiros" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Rui Parceiro" })).toBeNull();
  });
});

describe("ProcessFilters — Por Parceiro", () => {
  it("oferece «Sem parceiro» e os parceiros, e emite o escolhido", async () => {
    const aoMudar = vi.fn();
    montar(<ProcessFilters parceiro="all" onParceiroChange={aoMudar} />);
    await userEvent.click(screen.getByTestId("process-parceiro-filter"));
    expect(await screen.findByRole("option", { name: "Sem parceiro" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("option", { name: "Rui Parceiro" }));
    expect(aoMudar).toHaveBeenCalledWith("pt-1");
  });

  it("«Sem parceiro» emite «none», o valor que o servidor entende", async () => {
    const aoMudar = vi.fn();
    montar(<ProcessFilters parceiro="all" onParceiroChange={aoMudar} />);
    await userEvent.click(screen.getByTestId("process-parceiro-filter"));
    await userEvent.click(await screen.findByRole("option", { name: "Sem parceiro" }));
    expect(aoMudar).toHaveBeenCalledWith("none");
  });

  it("sem onParceiroChange o select não existe e nada é pedido", async () => {
    montar(<ProcessFilters />);
    expect(screen.queryByTestId("process-parceiro-filter")).toBeNull();
    await waitFor(() => expect(api.getUsers).toHaveBeenCalled());
    expect(api.getPartnerOptions).not.toHaveBeenCalled();
  });
});
