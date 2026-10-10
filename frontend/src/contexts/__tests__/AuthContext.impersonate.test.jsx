/**
 * Impersonate espelha o alvo e troca de âmbito (Bloco 4, ponto 33).
 *
 * O ambiente de quem "vê como outro utilizador" tem de ser exactamente o do
 * alvo, mesmo que quem iniciou seja Admin. Três coisas o garantem e este
 * ficheiro afirma as três:
 *
 *   1. o perfil publicado (`effectiveRole`) é o do ALVO;
 *   2. os cabeçalhos do alvo são sincronizados ANTES de a cache ser
 *      esvaziada (a ordem do Lote 6: o `clear()` faz as queries activas
 *      voltar a pedir já, e se os cabeçalhos ainda forem os do admin os
 *      dados do admin voltam a entrar na cache do alvo);
 *   3. a cache do administrador é esvaziada — servi-la ao alvo mostra o que
 *      ele NÃO vê, nem que seja até ao pedido seguinte.
 */
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const ADMIN = {
  id: "adm", name: "Admin", email: "admin@x.pt", role: "admin", company: "Power",
  companies: [{ company_id: "cmp-power", company_name: "Power", role: "admin", is_default: true }],
};
const ALVO_NO_ME = {
  id: "alvo", name: "Carlos", email: "c@x.pt", role: "consultor", company: "Power",
  is_impersonated: true, impersonated_by_name: "Admin",
  companies: [{ company_id: "cmp-power", company_name: "Power", role: "consultor", is_default: true }],
};
const ALVO_DA_RESPOSTA = {
  id: "alvo", name: "Carlos", email: "c@x.pt", role: "consultor",
  is_impersonated: true, impersonated_by_name: "Admin",
};

let quemEstaAutenticado;

vi.mock("../../services/api", () => ({
  default: {
    get: vi.fn(async (url) =>
      String(url).includes("/auth/me") ? { data: quemEstaAutenticado } : { data: {} },
    ),
    post: vi.fn(async (url) => {
      if (String(url).includes("/admin/impersonate/")) {
        quemEstaAutenticado = ALVO_NO_ME;
        return { data: { access_token: "tok-alvo", user: ALVO_DA_RESPOSTA } };
      }
      if (String(url).includes("/admin/stop-impersonate")) {
        quemEstaAutenticado = ADMIN;
        return { data: { access_token: "tok-admin", user: { id: "adm", name: "Admin", role: "admin" } } };
      }
      return { data: {} };
    }),
    defaults: { headers: { common: {} } },
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
  syncAuthContextHeaders: vi.fn(),
  setAuthToken: vi.fn(),
  clearAuthToken: vi.fn(),
  getRefreshedToken: vi.fn(async () => null),
}));

import { syncAuthContextHeaders } from "../../services/api";
import { AuthProvider, useAuth } from "../AuthContext";

let queryClient;
let cronologia;

function montar() {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  cronologia = [];
  const clearOriginal = queryClient.clear.bind(queryClient);
  queryClient.clear = (...args) => {
    cronologia.push("clear");
    return clearOriginal(...args);
  };
  syncAuthContextHeaders.mockImplementation((s) => {
    cronologia.push(`sync:${s?.role || "-"}`);
  });
  const wrapper = ({ children }) => (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
  return renderHook(() => useAuth(), { wrapper });
}

beforeEach(() => {
  quemEstaAutenticado = ADMIN;
  sessionStorage.clear();
  localStorage.clear();
  localStorage.setItem("token", "tok-admin");
  sessionStorage.setItem("activeRole", "admin");
});
afterEach(() => vi.clearAllMocks());

describe("impersonate", () => {
  it("o perfil publicado é o do ALVO, não o do administrador", async () => {
    const { result } = montar();
    await waitFor(() => expect(result.current.effectiveRole).toBe("admin"));

    await act(async () => {
      await result.current.impersonate("alvo");
    });

    expect(result.current.isImpersonating).toBe(true);
    expect(result.current.effectiveRole).toBe("consultor");
    await waitFor(() => expect(result.current.user?.role).toBe("consultor"));
    expect(result.current.effectiveRole).toBe("consultor");
  });

  it("um perfil de administrador que se escreva a seguir não vence o do alvo", async () => {
    // `switchActiveRole` não valida o perfil contra os do utilizador: um
    // `activeRole` "admin" pode chegar ao estado por outra via (outro
    // separador, um arranque antes do /auth/me). O que o ecrã lê não pode
    // acompanhá-lo — é a razão de existir do `papelEfectivoDaSessao`.
    const { result } = montar();
    await waitFor(() => expect(result.current.effectiveRole).toBe("admin"));
    await act(async () => { await result.current.impersonate("alvo"); });
    await waitFor(() => expect(result.current.user?.role).toBe("consultor"));

    act(() => result.current.switchActiveRole("admin"));

    expect(result.current.activeRole).toBe("admin");
    expect(result.current.effectiveRole).toBe("consultor");
  });

  it("sincroniza os cabeçalhos do alvo ANTES de esvaziar a cache do administrador", async () => {
    const { result } = montar();
    await waitFor(() => expect(result.current.effectiveRole).toBe("admin"));
    queryClient.setQueryData(["admin-only"], { segredo: true });
    cronologia.length = 0;

    await act(async () => {
      await result.current.impersonate("alvo");
    });

    const indiceDoClear = cronologia.indexOf("clear");
    expect(indiceDoClear).toBeGreaterThanOrEqual(0);
    const antes = cronologia.slice(0, indiceDoClear).filter((e) => e.startsWith("sync:"));
    expect(antes.length).toBeGreaterThan(0);
    expect(antes[antes.length - 1]).toBe("sync:consultor");
    expect(queryClient.getQueryData(["admin-only"])).toBeUndefined();
  });

  it("não deixa o cabeçalho do administrador voltar depois do clear", async () => {
    const { result } = montar();
    await waitFor(() => expect(result.current.effectiveRole).toBe("admin"));
    cronologia.length = 0;

    await act(async () => {
      await result.current.impersonate("alvo");
    });
    await waitFor(() => expect(result.current.user?.role).toBe("consultor"));

    const depois = cronologia.slice(cronologia.indexOf("clear") + 1).filter((e) => e.startsWith("sync:"));
    for (const entrada of depois) expect(entrada).not.toBe("sync:admin");
  });
});

describe("terminar o impersonate", () => {
  it("esvazia a cache do alvo e sincroniza o administrador antes", async () => {
    const original = window.location;
    delete window.location;
    window.location = { ...original, href: "" };
    try {
      const { result } = montar();
      await waitFor(() => expect(result.current.effectiveRole).toBe("admin"));
      await act(async () => { await result.current.impersonate("alvo"); });
      await waitFor(() => expect(result.current.user?.role).toBe("consultor"));
      queryClient.setQueryData(["so-do-alvo"], { x: 1 });
      cronologia.length = 0;

      await act(async () => { await result.current.stopImpersonating(); });

      const indice = cronologia.indexOf("clear");
      expect(indice).toBeGreaterThanOrEqual(0);
      const antes = cronologia.slice(0, indice).filter((e) => e.startsWith("sync:"));
      expect(antes[antes.length - 1]).toBe("sync:admin");
      expect(queryClient.getQueryData(["so-do-alvo"])).toBeUndefined();
    } finally {
      window.location = original;
    }
  });
});
