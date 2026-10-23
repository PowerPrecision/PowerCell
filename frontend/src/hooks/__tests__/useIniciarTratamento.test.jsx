/** `useIniciarTratamento`: abrir a bancada arranca o tratamento UMA vez e só quando o processo é do utilizador. */
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../services/api", () => ({ startIndexWork: vi.fn() }));

import { startIndexWork } from "../../services/api";
import { queryKeys } from "../../lib/queryClient";
import { useIniciarTratamento } from "../useIniciarTratamento";

function montar(args) {
  const cliente = new QueryClient();
  const invalidar = vi.spyOn(cliente, "invalidateQueries");
  const envolver = ({ children }) => <QueryClientProvider client={cliente}>{children}</QueryClientProvider>;
  const r = renderHook(({ id, activo }) => useIniciarTratamento(id, activo), { wrapper: envolver, initialProps: args });
  return { ...r, invalidar };
}

beforeEach(() => startIndexWork.mockReset());

describe("useIniciarTratamento", () => {
  it("pede uma vez e refaz a bancada e a fila quando o estado mudou", async () => {
    startIndexWork.mockResolvedValue({ data: { iniciado: true } });
    const { invalidar, rerender } = montar({ id: "p1", activo: true });
    await waitFor(() => expect(startIndexWork).toHaveBeenCalledWith("p1"));
    await waitFor(() => expect(invalidar).toHaveBeenCalledWith({ queryKey: queryKeys.index.workstation("p1") }));
    expect(invalidar).toHaveBeenCalledWith({ queryKey: queryKeys.index.queueAll() });
    rerender({ id: "p1", activo: true });
    expect(startIndexWork).toHaveBeenCalledTimes(1);
  });

  it("inactivo não pede", () => {
    montar({ id: "p1", activo: false });
    expect(startIndexWork).not.toHaveBeenCalled();
  });

  it("sem id não pede", () => {
    montar({ id: undefined, activo: true });
    expect(startIndexWork).not.toHaveBeenCalled();
  });

  it("se o servidor diz que não iniciou, não refaz nada", async () => {
    startIndexWork.mockResolvedValue({ data: { iniciado: false, registado: true } });
    const { invalidar } = montar({ id: "p1", activo: true });
    await waitFor(() => expect(startIndexWork).toHaveBeenCalled());
    await Promise.resolve();
    expect(invalidar).not.toHaveBeenCalled();
  });

  it("uma falha não rebenta e deixa tentar de novo ao reabrir", async () => {
    startIndexWork.mockRejectedValueOnce(new Error("rede"));
    const { rerender } = montar({ id: "p1", activo: true });
    await waitFor(() => expect(startIndexWork).toHaveBeenCalledTimes(1));
    startIndexWork.mockResolvedValue({ data: { iniciado: true } });
    rerender({ id: "p2", activo: true });
    await waitFor(() => expect(startIndexWork).toHaveBeenCalledWith("p2"));
  });

  it("outro processo pede de novo", async () => {
    startIndexWork.mockResolvedValue({ data: { iniciado: false } });
    const { rerender } = montar({ id: "p1", activo: true });
    await waitFor(() => expect(startIndexWork).toHaveBeenCalledTimes(1));
    rerender({ id: "p2", activo: true });
    await waitFor(() => expect(startIndexWork).toHaveBeenCalledTimes(2));
  });
});
