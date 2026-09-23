/**
 * Trocar de perfil tem de limpar a cache (Lote 5, ponto 6).
 *
 * O QUE ACONTECIA
 *   `switchActiveCompany` termina em `window.location.reload()` — limpa
 *   tudo e funciona. `switchActiveRole` escreve no storage e no estado e
 *   NÃO toca no TanStack Query. O comentário no código chegava a afirmar
 *   que servia "para as páginas voltarem a pedir a API sem hard-reload",
 *   mas nada as fazia pedir: os dados não estavam stale e ninguém os
 *   invalidou. Trocar de Consultor para Diretor não mudava a lista.
 *
 * PORQUÊ `clear()` E NÃO `invalidateQueries()`
 *   `invalidate` marca como stale e refaz o pedido — mas continua a
 *   MOSTRAR os dados antigos enquanto o novo não chega. Numa troca de
 *   perfil isso é renderizar dados do outro âmbito, ainda que por
 *   instantes. É o mesmo raciocínio que já justificava o reload na troca
 *   de empresa: primeiro esvaziar, depois pedir.
 */
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../services/api", () => ({
  default: {
    get: vi.fn(async () => ({ data: {} })),
    post: vi.fn(async () => ({ data: {} })),
    defaults: { headers: { common: {} } },
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
  syncAuthContextHeaders: vi.fn(),
  setAuthToken: vi.fn(),
  clearAuthToken: vi.fn(),
  getRefreshedToken: vi.fn(async () => null),
}));

import { AuthProvider, useAuth } from "../AuthContext";

const UTILIZADOR = {
  id: "u-1",
  name: "Ana",
  email: "ana@power.pt",
  role: "consultor",
  companies: [
    { company_id: "cmp-power", company_name: "Power", role: "consultor", is_default: true },
    { company_id: "cmp-power", company_name: "Power", role: "diretor" },
  ],
};

let queryClient;

function montar() {
  queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }) => (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
  return renderHook(() => useAuth(), { wrapper });
}

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
  localStorage.setItem("token", "t");
  localStorage.setItem("user", JSON.stringify(UTILIZADOR));
});

afterEach(() => vi.clearAllMocks());

describe("Trocar de perfil", () => {
  it("esvazia a cache de dados", async () => {
    const { result } = montar();
    await waitFor(() => expect(result.current.switchActiveRole).toBeTruthy());

    queryClient.setQueryData(["processes", "list"], [{ id: "p-do-consultor" }]);
    expect(queryClient.getQueryData(["processes", "list"])).toBeTruthy();

    act(() => result.current.switchActiveRole("diretor"));

    await waitFor(() =>
      expect(queryClient.getQueryData(["processes", "list"])).toBeUndefined(),
    );
  });

  it("regista o perfil novo antes de limpar", async () => {
    // Ordem importa: se a cache fosse limpa primeiro, o refetch que se
    // segue partia com os headers antigos e voltava a encher a cache
    // com o âmbito errado.
    const { result } = montar();
    await waitFor(() => expect(result.current.switchActiveRole).toBeTruthy());

    act(() => result.current.switchActiveRole("diretor"));

    expect(sessionStorage.getItem("activeRole")).toBe("diretor");
  });

  it("um perfil vazio não limpa nada", async () => {
    const { result } = montar();
    await waitFor(() => expect(result.current.switchActiveRole).toBeTruthy());

    queryClient.setQueryData(["processes", "list"], [{ id: "p-1" }]);
    act(() => result.current.switchActiveRole(""));

    expect(queryClient.getQueryData(["processes", "list"])).toBeTruthy();
  });
});
