/**
 * O perfil marcado «Padrão» manda à entrada — no login e num F5 (Out 2026).
 *
 * O DEFEITO: depois do login (e num separador novo) o arranque escolhia o PRIMEIRO UCR com o perfil
 * principal da conta, pela ordem das empresas, e o `active_company_id` do localStorage (de uma sessão
 * anterior) vencia tudo. O perfil «Padrão» só servia de último recurso.
 *
 * O QUE ESTE FICHEIRO AFIRMA: login e arranque sem escolha no separador → «Padrão» (cargo e empresa);
 * uma escolha feita no separador (é o que a troca de empresa usa para recarregar) sobrevive ao F5.
 */
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const UTILIZADOR = {
  id: "u-1",
  name: "Ana",
  email: "ana@power.pt",
  role: "consultor",
  company: "Alfa",
  companies: [
    { company_id: "cmp-alfa", company_name: "Alfa", role: "consultor" },
    { company_id: "cmp-zeta", company_name: "Zeta", role: "diretor", is_default: true },
  ],
};

vi.mock("../../services/api", () => ({
  default: {
    get: vi.fn(async (url) => (String(url).includes("/auth/me") ? { data: UTILIZADOR } : { data: {} })),
    post: vi.fn(async (url) =>
      String(url).includes("/auth/login-v2")
        ? { data: { access_token: "novo", refresh_token: "r", user: UTILIZADOR } }
        : { data: {} },
    ),
    defaults: { headers: { common: {} } },
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
  syncAuthContextHeaders: vi.fn(),
  setAuthToken: vi.fn(),
  clearAuthToken: vi.fn(),
  getRefreshedToken: vi.fn(async () => null),
}));

import { AuthProvider, useAuth } from "../AuthContext";

function montar() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
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
});

afterEach(() => vi.clearAllMocks());

describe("perfil «Padrão» à entrada", () => {
  it("o login arranca no Padrão (cargo e empresa), não na primeira empresa nem no perfil principal", async () => {
    localStorage.setItem("active_company_id", "cmp-alfa"); // resto de uma sessão anterior
    const { result } = montar();
    await act(async () => { await result.current.login("ana@power.pt", "x"); });
    await waitFor(() => expect(result.current.user?.companies).toHaveLength(2));
    expect(result.current.activeRole).toBe("diretor");
    expect(result.current.activeCompanyId).toBe("cmp-zeta");
    expect(localStorage.getItem("active_company_id")).toBe("cmp-zeta");
  });

  it("um F5 sem escolha neste separador arranca no Padrão, mesmo com outra empresa no localStorage", async () => {
    localStorage.setItem("token", "t");
    localStorage.setItem("active_company_id", "cmp-alfa");
    const { result } = montar();
    await waitFor(() => expect(result.current.activeCompanyId).toBe("cmp-zeta"));
    expect(result.current.activeRole).toBe("diretor");
  });

  it("uma escolha feita neste separador sobrevive ao F5", async () => {
    localStorage.setItem("token", "t");
    sessionStorage.setItem("activeRole", "consultor");
    sessionStorage.setItem("activeCompanyId", "cmp-alfa");
    const { result } = montar();
    await waitFor(() => expect(result.current.user?.companies).toHaveLength(2));
    await waitFor(() => expect(result.current.activeCompanyId).toBe("cmp-alfa"));
    expect(result.current.activeRole).toBe("consultor");
  });
});
