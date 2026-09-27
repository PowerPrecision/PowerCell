/**
 * O Kanban e a lacuna que o polling não tapava (Épico 10, Fase 3).
 *
 * O Kanban NUNCA teve polling: vive de `staleTime` + `refetchOnWindowFocus`.
 * Por isso a Fase 3 não lhe corta nada — corrige o outro lado da moeda. Os
 * eventos emitidos enquanto o socket esteve em baixo perderam-se e nada os
 * repete; sem uma invalidação na volta da ligação, o quadro fica calado e
 * desactualizado ao mesmo tempo, que é pior do que estar visivelmente
 * offline: parece estar a funcionar.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { queryKeys } from "../../lib/queryClient";

let estadoDaLigacao = { isConnected: true, on: () => () => {}, sendMessage: vi.fn() };

vi.mock("../useWebSocket", () => ({
  useWebSocket: () => estadoDaLigacao,
  WSEventType: {
    PROCESS_CREATED: "process_created",
    PROCESS_STATUS_CHANGED: "process_status_changed",
    PROCESS_UPDATED: "process_updated",
    PROCESS_ASSIGNED: "process_assigned",
    PROCESS_MOVED: "process_moved",
    PROCESS_LOCKED: "process_locked",
    PROCESS_UNLOCKED: "process_unlocked",
  },
}));

import { useKanbanRealtime } from "../queries/useKanbanRealtime";

const FILTROS = { view_mode: "all" };

function montar(client) {
  const wrapper = ({ children }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return renderHook(() => useKanbanRealtime({ filters: FILTROS }), { wrapper });
}

let client;
let invalidar;

beforeEach(() => {
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  invalidar = vi.spyOn(client, "invalidateQueries");
  estadoDaLigacao = { isConnected: true, on: () => () => {}, sendMessage: vi.fn() };
});

describe("recuperação do Kanban na volta da ligação", () => {
  it("invalida o quadro quando o WebSocket regressa depois de cair", () => {
    estadoDaLigacao = { ...estadoDaLigacao, isConnected: false };
    const { rerender } = montar(client);
    invalidar.mockClear();

    estadoDaLigacao = { ...estadoDaLigacao, isConnected: true };
    rerender();

    expect(invalidar).toHaveBeenCalledWith({
      queryKey: queryKeys.processes.kanban(FILTROS),
    });
  });

  it("não invalida na primeira ligação", () => {
    // A query inicial do TanStack já trouxe o quadro; invalidar aqui seria
    // um segundo pedido em cada abertura da página.
    montar(client);
    expect(invalidar).not.toHaveBeenCalledWith({
      queryKey: queryKeys.processes.kanban(FILTROS),
    });
  });

  it("não invalida ao PERDER a ligação", () => {
    // Ao perder, os dados em cache continuam a ser os últimos bons; pedir
    // agora é pedir com a rede a falhar.
    const { rerender } = montar(client);
    invalidar.mockClear();

    estadoDaLigacao = { ...estadoDaLigacao, isConnected: false };
    rerender();

    expect(invalidar).not.toHaveBeenCalledWith({
      queryKey: queryKeys.processes.kanban(FILTROS),
    });
  });
});
