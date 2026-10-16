/**
 * Trocar de perfil/empresa actualiza os CABEÇALHOS antes de pedir (Lote 6, pontos 3 e 4).
 *
 * O DEFEITO (produção, Set 2026)
 * ==============================
 * Mudar a empresa activa não actualizava a lista de processos, de clientes,
 * de tarefas nem a caixa do Webmail — e pior: um utilizador da Domus via a
 * caixa geral e as tarefas da POWER.
 *
 * A causa é uma corrida de um único commit do React:
 *
 *   1. o interceptor do Axios lê `X-Company-Id` de `authContextHeaders`,
 *      um snapshot em memória de `services/api.js`, e **prefere-o** ao
 *      `localStorage` (foi feito assim de propósito, para uma página que
 *      escreva "all" no storage não conseguir desviar o âmbito);
 *   2. quem escreve esse snapshot é `syncAuthContextHeaders`, chamado
 *      dentro de um `useEffect` — ou seja, DEPOIS do commit;
 *   3. `switchActiveRole` chama `queryClient.clear()` de forma SÍNCRONA, e
 *      o `clear()` faz as queries activas voltar a pedir imediatamente.
 *
 * Resultado: o refetch da troca sai com o snapshot ANTIGO. Os dados que
 * voltam são da empresa anterior e ficam em cache como se fossem os da
 * nova. O estado converge um commit mais tarde — tarde demais, porque o
 * pedido já foi feito e ninguém o repete.
 *
 * PORQUE É QUE O TESTE ANTERIOR NÃO VIU
 *   `AuthContext.switchRole.test.jsx` afirmava
 *   `sessionStorage.getItem("activeRole") === "diretor"`, com o comentário
 *   "se a cache fosse limpa primeiro, o refetch partia com os headers
 *   antigos". A premissa estava certa e a asserção era sobre o sítio
 *   errado: o storage não é o que o interceptor lê primeiro. Provava que a
 *   escrita acontecera e concluía que os cabeçalhos estavam certos — a
 *   mesma forma da guarda que exigia literalmente a chave de cache
 *   colidida e, por isso, cristalizava o defeito.
 *
 * O QUE ESTE FICHEIRO AFIRMA
 *   A ORDEM: `syncAuthContextHeaders` com o âmbito NOVO tem de acontecer
 *   antes de `queryClient.clear()`. É a ordem que não se consegue provar
 *   com uma asserção sobre estado final.
 */
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// O `user` vem de `GET /auth/me` e NÃO do localStorage: sem o falsear, o
// provider ficava com `user` a `null`, `resolveCompanyIdFromUser` não tinha
// UCRs onde procurar e o teste media a montagem em vez da troca de perfil.
const UTILIZADOR_DO_ME = {
  id: "u-1",
  name: "Ana",
  email: "ana@power.pt",
  role: "consultor",
  company: "Power",
  companies: [
    { company_id: "cmp-power", company_name: "Power", role: "consultor", is_default: true },
    { company_id: "cmp-domus", company_name: "Domus", role: "consultor" },
  ],
};

vi.mock("../../services/api", () => ({
  default: {
    get: vi.fn(async (url) =>
      String(url).includes("/auth/me") ? { data: UTILIZADOR_DO_ME } : { data: {} },
    ),
    post: vi.fn(async () => ({ data: {} })),
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
/** Registo cronológico das duas operações cuja ORDEM é o objecto do teste. */
let cronologia;

function montar() {
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  cronologia = [];

  const clearOriginal = queryClient.clear.bind(queryClient);
  queryClient.clear = (...args) => {
    cronologia.push("clear");
    return clearOriginal(...args);
  };
  syncAuthContextHeaders.mockImplementation((snapshot) => {
    cronologia.push(`sync:${snapshot?.companyId || "-"}:${snapshot?.role || "-"}`);
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
  localStorage.setItem("user", JSON.stringify(UTILIZADOR_DO_ME));
  localStorage.setItem("active_company_id", "cmp-power");
});

afterEach(() => vi.clearAllMocks());

describe("switchActiveRole — os cabeçalhos não podem ficar atrasados", () => {
  it("sincroniza o snapshot com a empresa NOVA antes de esvaziar a cache", async () => {
    const { result } = montar();
    await waitFor(() => expect(result.current.user?.companies).toHaveLength(2));

    cronologia.length = 0;
    act(() => result.current.switchActiveRole("consultor", "cmp-domus"));

    const indiceDoClear = cronologia.indexOf("clear");
    expect(indiceDoClear).toBeGreaterThanOrEqual(0);

    const sincronizacoesAntes = cronologia
      .slice(0, indiceDoClear)
      .filter((e) => e.startsWith("sync:"));

    expect(sincronizacoesAntes).not.toHaveLength(0);
    // A ÚLTIMA sincronização antes do clear é a que o refetch vai usar.
    expect(sincronizacoesAntes[sincronizacoesAntes.length - 1]).toBe(
      "sync:cmp-domus:consultor",
    );
  });

  it("nunca sincroniza a empresa ANTIGA depois de esvaziar", async () => {
    /**
     * Contraprova no outro sentido: acrescentar uma chamada nova antes do
     * `clear()` satisfaria o teste de cima mesmo que o `useEffect` voltasse
     * a escrever o âmbito antigo por cima. Uma queria ir para a Domus, a
     * outra repunha a Power — e o pedido seguinte saía errado outra vez.
     */
    const { result } = montar();
    await waitFor(() => expect(result.current.user?.companies).toHaveLength(2));

    cronologia.length = 0;
    act(() => result.current.switchActiveRole("consultor", "cmp-domus"));
    await waitFor(() => expect(cronologia).toContain("clear"));

    const depoisDoClear = cronologia
      .slice(cronologia.indexOf("clear") + 1)
      .filter((e) => e.startsWith("sync:"));

    for (const entrada of depoisDoClear) {
      expect(entrada).not.toContain("cmp-power");
    }
  });

  it("um perfil vazio não sincroniza nem limpa", async () => {
    const { result } = montar();
    await waitFor(() => expect(result.current.user?.companies).toHaveLength(2));

    cronologia.length = 0;
    act(() => result.current.switchActiveRole(""));

    expect(cronologia).not.toContain("clear");
  });
});

describe("switchActiveCompany — o reload não dispensa o snapshot", () => {
  it("sincroniza o snabshot antes de recarregar a página", async () => {
    /**
     * A troca de empresa termina em `window.location.reload()`, e num
     * browser real o snapshot morre com a página. Mas o `await` do
     * `persistActiveCompany` deixa uma janela em que a app continua viva:
     * qualquer pedido que arranque nesse intervalo (um polling, um refetch
     * ao voltar ao separador) sai com a empresa anterior. Sincronizar antes
     * fecha a janela e não custa nada.
     */
    const recarregar = vi.fn();
    const originalLocation = window.location;
    delete window.location;
    window.location = { ...originalLocation, reload: recarregar };

    try {
      const { result } = montar();
      await waitFor(() => expect(result.current.user?.companies).toHaveLength(2));

      cronologia.length = 0;
      await act(async () => {
        await result.current.switchActiveCompany("cmp-domus");
      });

      expect(recarregar).toHaveBeenCalled();
      const sincronizacoes = cronologia.filter((e) => e.startsWith("sync:"));
      expect(sincronizacoes).toContain("sync:cmp-domus:consultor");
    } finally {
      window.location = originalLocation;
    }
  });
});

describe("switchActiveRole — um perfil que muda de EMPRESA recarrega (Lote 7.1)", () => {
  /**
   * `clear()` esvazia a cache do TanStack, mas o Webmail guarda a empresa em `?company_id=` e em
   * estado local: quem passava de Power a Domus pelo seletor de perfis continuava a ler a caixa da
   * empresa anterior. Trocar de empresa por esta via faz o mesmo que `switchActiveCompany`.
   */
  function comReloadFalso() {
    const recarregar = vi.fn();
    const originalLocation = window.location;
    delete window.location;
    window.location = { ...originalLocation, reload: recarregar };
    return { recarregar, repor: () => { window.location = originalLocation; } };
  }

  it("muda de empresa: grava no servidor e DEPOIS recarrega", async () => {
    const { recarregar, repor } = comReloadFalso();
    try {
      const { result } = montar();
      await waitFor(() => expect(result.current.user?.companies).toHaveLength(2));

      await act(async () => {
        result.current.switchActiveRole("consultor", "cmp-domus");
      });

      await waitFor(() => expect(recarregar).toHaveBeenCalledTimes(1));
      const api = (await import("../../services/api")).default;
      expect(api.post).toHaveBeenCalledWith("/auth/active-company", {
        company_id: "cmp-domus", role: "consultor",
      });
    } finally {
      repor();
    }
  });

  it("o mesmo cargo na MESMA empresa não recarrega (contraprova)", async () => {
    const { recarregar, repor } = comReloadFalso();
    try {
      const { result } = montar();
      await waitFor(() => expect(result.current.user?.companies).toHaveLength(2));

      await act(async () => {
        result.current.switchActiveRole("diretor", "cmp-power");
      });
      // dá tempo a uma promessa pendente de se manifestar
      await new Promise((r) => setTimeout(r, 20));

      expect(recarregar).not.toHaveBeenCalled();
    } finally {
      repor();
    }
  });

  it("reescreve o company_id do URL para a empresa nova antes de recarregar", async () => {
    // O URL tem de existir ANTES de falsear `window.location` (a cópia congela o `href`).
    window.history.replaceState(null, "", "/webmail?company_id=cmp-power&folder=inbox");
    const { recarregar, repor } = comReloadFalso();
    try {
      const { result } = montar();
      await waitFor(() => expect(result.current.user?.companies).toHaveLength(2));

      await act(async () => {
        result.current.switchActiveRole("consultor", "cmp-domus");
      });
      await waitFor(() => expect(recarregar).toHaveBeenCalled());

      // `replaceState` mexe na história REAL (a `window.location` falsa é uma cópia congelada).
      const url = new URL(document.location.href);
      expect(url.searchParams.get("company_id")).toBe("cmp-domus");
      expect(url.searchParams.get("folder")).toBe("inbox");
    } finally {
      repor();
      window.history.replaceState(null, "", "/");
    }
  });

  it("servidor inalcançável: não recarrega (a página de erro do browser é pior)", async () => {
    const api = (await import("../../services/api")).default;
    api.post.mockRejectedValueOnce(Object.assign(new Error("Network Error"), { code: "ERR_NETWORK" }));
    const { recarregar, repor } = comReloadFalso();
    try {
      const { result } = montar();
      await waitFor(() => expect(result.current.user?.companies).toHaveLength(2));

      await act(async () => {
        result.current.switchActiveRole("consultor", "cmp-domus");
      });
      await new Promise((r) => setTimeout(r, 20));

      expect(recarregar).not.toHaveBeenCalled();
    } finally {
      repor();
    }
  });
});
