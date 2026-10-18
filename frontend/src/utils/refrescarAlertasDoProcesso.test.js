import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { queryKeys } from "../lib/queryClient";
import { agendarRefrescoDosAlertas, ESPERAS_DO_REFRESCO_MS } from "./refrescarAlertasDoProcesso";

describe("agendarRefrescoDosAlertas", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("invalida a chave dos alertas do processo em cada espera, e só nelas", () => {
    const queryClient = { invalidateQueries: vi.fn() };
    agendarRefrescoDosAlertas(queryClient, "p-1");

    expect(queryClient.invalidateQueries).not.toHaveBeenCalled();
    vi.advanceTimersByTime(ESPERAS_DO_REFRESCO_MS[0]);
    expect(queryClient.invalidateQueries).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(ESPERAS_DO_REFRESCO_MS[1]);
    expect(queryClient.invalidateQueries).toHaveBeenCalledTimes(2);
    expect(queryClient.invalidateQueries).toHaveBeenLastCalledWith({
      queryKey: queryKeys.processes.alerts("p-1"),
    });
  });

  it("cancelar impede as passagens que faltam", () => {
    const queryClient = { invalidateQueries: vi.fn() };
    const cancelar = agendarRefrescoDosAlertas(queryClient, "p-1");
    cancelar();
    vi.advanceTimersByTime(60_000);
    expect(queryClient.invalidateQueries).not.toHaveBeenCalled();
  });

  it("sem processo ou sem cliente de cache não faz nada (e não rebenta)", () => {
    expect(() => agendarRefrescoDosAlertas(null, "p-1")()).not.toThrow();
    const queryClient = { invalidateQueries: vi.fn() };
    agendarRefrescoDosAlertas(queryClient, "")();
    vi.advanceTimersByTime(60_000);
    expect(queryClient.invalidateQueries).not.toHaveBeenCalled();
  });
});
