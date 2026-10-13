/**
 * A cache do TanStack é de QUEM esteve antes (QA, Out 2026).
 *
 * O DEFEITO
 *   A QA entrava como utilizador da Power, saía e entrava como utilizador da
 *   Domus no MESMO separador. O quadro Kanban mostrava cartões de processos da
 *   Power (o detalhe respondia «Processo não encontrado») e a página de
 *   «Registos de Clientes» listava registos globais. O servidor devolvia o
 *   que devia — reproduzido contra um MongoDB real: a query do quadro e a
 *   listagem estão isoladas por rede. O que o ecrã mostrava era a CACHE do
 *   utilizador anterior: o logout é uma navegação SPA (`navigate("/login")`),
 *   não recarrega a página, e a cache vive 5 minutos (`gcTime`). Só a troca de
 *   perfil, de empresa e o impersonate a esvaziavam.
 *
 * O QUE SE AFIRMA
 *   Sair e entrar esvaziam a cache; e uma troca de perfil continua a esvaziar
 *   (contraprova de que o teste mede a cache e não uma montagem).
 */
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const POWER = {
  id: "u-power", name: "Ana", email: "ana@power.pt", role: "diretor", company: "Power",
  companies: [{ company_id: "cmp-power", company_name: "Power", role: "diretor", is_default: true }],
};
const DOMUS = {
  id: "u-domus", name: "Bruno", email: "bruno@domus.pt", role: "diretor", company: "Domus",
  companies: [{ company_id: "cmp-domus", company_name: "Domus", role: "diretor", is_default: true }],
};

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  defaults: { headers: { common: {} } },
  interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
}));

vi.mock("../../services/api", () => ({
  default: api,
  syncAuthContextHeaders: vi.fn(),
  setAuthToken: vi.fn(),
  clearAuthToken: vi.fn(),
  getRefreshedToken: vi.fn(async () => null),
}));

import { AuthProvider, useAuth } from "../AuthContext";

let queryClient;

function montar() {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }) => (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
  return renderHook(() => useAuth(), { wrapper });
}

const CHAVE_DO_QUADRO = ["processes", "kanban", { consultorFilter: "" }];

function semearCacheDaPower() {
  queryClient.setQueryData(CHAVE_DO_QUADRO, { columns: [{ name: "novo", processes: [{ id: "p-power" }] }] });
  queryClient.setQueryData(["admin", "client-registrations", 1], { registrations: [{ id: "p-power" }] });
}

/** Quem o servidor diz que está autenticado (`/auth/me`): muda quando alguém entra. */
let utilizadorActual;

beforeEach(() => {
  utilizadorActual = POWER;
  sessionStorage.clear();
  localStorage.clear();
  localStorage.setItem("token", "t-power");
  localStorage.setItem("user", JSON.stringify(POWER));
  api.get.mockImplementation(async (url) =>
    String(url).includes("/auth/me") ? { data: utilizadorActual } : { data: {} },
  );
  api.post.mockImplementation(async (url) => {
    if (String(url).includes("/auth/login-v2")) {
      utilizadorActual = DOMUS;
      return { data: { access_token: "t-domus", refresh_token: "r-domus", user: DOMUS } };
    }
    return { data: {} };
  });
});

afterEach(() => vi.clearAllMocks());

describe("a cache não atravessa sessões", () => {
  it("sair esvazia a cache do utilizador que saiu", async () => {
    const { result } = montar();
    await waitFor(() => expect(result.current.user?.id).toBe("u-power"));
    semearCacheDaPower();
    expect(queryClient.getQueryData(CHAVE_DO_QUADRO)).toBeDefined();

    await act(async () => {
      await result.current.logout();
    });

    expect(queryClient.getQueryData(CHAVE_DO_QUADRO)).toBeUndefined();
    expect(queryClient.getQueryCache().getAll()).toHaveLength(0);
  });

  it("entrar como outro utilizador no mesmo separador não herda a cache anterior", async () => {
    // Sem logout no meio (a sessão expirou, ou se entrou por cima): é o login que limpa.
    const { result } = montar();
    await waitFor(() => expect(result.current.user?.id).toBe("u-power"));
    semearCacheDaPower();

    await act(async () => {
      await result.current.login("bruno@domus.pt", "segredo");
    });

    expect(result.current.user?.id).toBe("u-domus");
    expect(queryClient.getQueryData(CHAVE_DO_QUADRO)).toBeUndefined();
    expect(queryClient.getQueryData(["admin", "client-registrations", 1])).toBeUndefined();
  });

  it("contraprova: sem sair nem entrar a cache mantém-se (o teste mede a cache, não a montagem)", async () => {
    const { result } = montar();
    await waitFor(() => expect(result.current.user?.id).toBe("u-power"));
    semearCacheDaPower();

    expect(queryClient.getQueryData(CHAVE_DO_QUADRO)).toBeDefined();
    expect(queryClient.getQueryCache().getAll().length).toBeGreaterThan(0);
  });
});
