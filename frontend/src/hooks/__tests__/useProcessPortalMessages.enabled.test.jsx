/**
 * Polling do portal para processos que já não existem (Lote 3, ponto 9).
 *
 * O DEFEITO
 *   `ProcessDetails` já sabia que o processo tinha sido eliminado — a
 *   query devolve 404 e a página mostra "Processo não encontrado". Mas
 *   esse `if (notFound) return <...>` é um early return no RENDER, e os
 *   hooks correm ANTES dele: `useProcessPortalMessages` continuava a
 *   interrogar `/portal-messages/unread` de 30 em 30 segundos sobre um
 *   processo que não existe.
 *
 *   O hook tinha uma defesa própria, mas só cobria o intervalo. O efeito
 *   de `isActive` (mudar de separador), o `refresh()` do WebSocket e o
 *   `fetchMessages` não a respeitavam — e o guard é um `useRef`, que
 *   reinicia em cada montagem.
 *
 * A CORRECÇÃO
 *   Quem sabe que o processo desapareceu é a página. `enabled: false`
 *   desliga o hook à nascença, em vez de cada caminho se defender depois
 *   do facto.
 */
import { renderHook, waitFor, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({ token: "t-1" }),
}));

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { useProcessPortalMessages } from "../useProcessPortalMessages";

const pedidos = [];

function ligarRede({ estado = 200 } = {}) {
  globalThis.fetch = vi.fn((url) => {
    pedidos.push(String(url));
    return Promise.resolve({
      ok: estado === 200,
      status: estado,
      json: () => Promise.resolve({ unread_count: 3, messages: [] }),
    });
  });
}

const pedidosDeUnread = () => pedidos.filter((u) => u.includes("/unread"));
const pedidosDeMensagens = () =>
  pedidos.filter((u) => u.includes("portal-messages") && !u.includes("/unread"));

beforeEach(() => {
  pedidos.length = 0;
  vi.useFakeTimers({ shouldAdvanceTime: true });
  ligarRede();
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe("useProcessPortalMessages — processo eliminado", () => {
  it("não pergunta nada quando está desligado", async () => {
    renderHook(() =>
      useProcessPortalMessages("proc-apagado", { enabled: false }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(pedidosDeUnread()).toHaveLength(0);
  });

  it("não volta a perguntar no intervalo seguinte", async () => {
    // O sintoma reportado: 404 a cada 30 segundos.
    renderHook(() =>
      useProcessPortalMessages("proc-apagado", { enabled: false }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(90000);
    });
    expect(pedidosDeUnread()).toHaveLength(0);
  });

  it("mudar de separador não contorna o desligamento", async () => {
    // O efeito de `isActive` chamava `fetchUnreadCount` directamente,
    // ignorando a defesa interna do hook.
    renderHook(() =>
      useProcessPortalMessages("proc-apagado", {
        enabled: false,
        isActive: true,
      }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(pedidosDeUnread()).toHaveLength(0);
    expect(pedidosDeMensagens()).toHaveLength(0);
  });

  it("o refresh manual também respeita o desligamento", async () => {
    // `refresh()` é chamado pelo WebSocket e não passava pelo guard.
    const { result } = renderHook(() =>
      useProcessPortalMessages("proc-apagado", { enabled: false }),
    );
    await act(async () => {
      result.current.refresh();
      await vi.advanceTimersByTimeAsync(100);
    });
    expect(pedidos).toHaveLength(0);
  });
});

describe("useProcessPortalMessages — processo normal", () => {
  it("pergunta o unread à montagem", async () => {
    renderHook(() => useProcessPortalMessages("proc-1"));
    await waitFor(() => expect(pedidosDeUnread().length).toBeGreaterThan(0));
  });

  it("continua a fazer polling", async () => {
    renderHook(() => useProcessPortalMessages("proc-1"));
    await waitFor(() => expect(pedidosDeUnread().length).toBeGreaterThan(0));
    const antes = pedidosDeUnread().length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(31000);
    });
    expect(pedidosDeUnread().length).toBeGreaterThan(antes);
  });

  it("com o separador activo carrega também as mensagens", async () => {
    renderHook(() => useProcessPortalMessages("proc-1", { isActive: true }));
    await waitFor(() => expect(pedidosDeMensagens().length).toBeGreaterThan(0));
  });

  it("sem `enabled` explícito assume ligado (retrocompatível)", async () => {
    // Os consumidores existentes não passam a opção.
    renderHook(() => useProcessPortalMessages("proc-1", {}));
    await waitFor(() => expect(pedidosDeUnread().length).toBeGreaterThan(0));
  });

  it("um 404 continua a desligar o polling por si", async () => {
    // A defesa interna do hook mantém-se: cobre o caso em que o processo
    // é eliminado com a página JÁ aberta.
    ligarRede({ estado: 404 });
    renderHook(() => useProcessPortalMessages("proc-1"));
    await waitFor(() => expect(pedidosDeUnread().length).toBeGreaterThan(0));
    const antes = pedidosDeUnread().length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(120000);
    });
    expect(pedidosDeUnread().length).toBe(antes);
  });
});
