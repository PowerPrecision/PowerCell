/**
 * Trocar de empresa com o servidor em baixo não leva a aplicação atrás (Lote 6, ponto 5).
 *
 * O DEFEITO: a troca termina em `window.location.reload()`. Com a hospedagem a reiniciar, o
 * reload cai na página de erro do browser (`ERR_CONNECTION_CLOSED`) e a aplicação desaparece.
 *
 * O pedido `POST /auth/active-company` que precede o reload é a sonda: se o servidor não
 * responde, desfaz-se a troca (storage, estado, cabeçalhos) e diz-se porquê. Um 4xx NÃO desfaz —
 * esse diz algo sobre o pedido, e o cliente já tem a empresa nos cabeçalhos.
 */
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const UTILIZADOR_DO_ME = {
  id: "u-1", name: "Ana", email: "ana@power.pt", role: "consultor", company: "Power",
  companies: [
    { company_id: "cmp-power", company_name: "Power", role: "consultor", is_default: true },
    { company_id: "cmp-domus", company_name: "Domus", role: "consultor" },
  ],
};

const rede = vi.hoisted(() => ({ erroDaTroca: null }));

vi.mock("../../services/api", () => ({
  default: {
    get: vi.fn(async (url) => (String(url).includes("/auth/me") ? { data: UTILIZADOR_DO_ME } : { data: {} })),
    post: vi.fn(async (url) => {
      if (String(url).includes("/auth/active-company") && rede.erroDaTroca) throw rede.erroDaTroca;
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

const toast = vi.hoisted(() => ({ error: vi.fn(), success: vi.fn(), info: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

import { syncAuthContextHeaders } from "../../services/api";
import { AuthProvider, useAuth } from "../AuthContext";

let recarregar;
let localizacaoOriginal;

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
  rede.erroDaTroca = null;
  sessionStorage.clear();
  localStorage.clear();
  localStorage.setItem("token", "t");
  localStorage.setItem("user", JSON.stringify(UTILIZADOR_DO_ME));
  localStorage.setItem("active_company_id", "cmp-power");
  sessionStorage.setItem("activeCompanyId", "cmp-power");
  recarregar = vi.fn();
  localizacaoOriginal = window.location;
  delete window.location;
  window.location = { ...localizacaoOriginal, reload: recarregar };
});

afterEach(() => {
  window.location = localizacaoOriginal;
  vi.clearAllMocks();
});

async function trocarParaADomus() {
  const { result } = montar();
  await waitFor(() => expect(result.current.user?.companies).toHaveLength(2));
  let devolvido;
  await act(async () => {
    devolvido = await result.current.switchActiveCompany("cmp-domus");
  });
  return { result, devolvido };
}

describe("switchActiveCompany — servidor inalcançável", () => {
  it.each([
    ["sem resposta (ERR_CONNECTION_CLOSED)", Object.assign(new Error("Network Error"), { code: "ERR_NETWORK", request: {} })],
    ["502 Bad Gateway", { response: { status: 502, data: "<html>Bad Gateway</html>" } }],
    ["503", { response: { status: 503, data: {} } }],
    ["504", { response: { status: 504, data: {} } }],
  ])("%s: NÃO recarrega, desfaz a troca e diz porquê", async (_nome, erro) => {
    rede.erroDaTroca = erro;

    const { result, devolvido } = await trocarParaADomus();

    expect(devolvido).toBe(false);
    expect(recarregar).not.toHaveBeenCalled();
    // A empresa activa mantém-se — no armazenamento, no estado e nos cabeçalhos.
    expect(localStorage.getItem("active_company_id")).toBe("cmp-power");
    expect(sessionStorage.getItem("activeCompanyId")).toBe("cmp-power");
    expect(result.current.effectiveCompanyId).toBe("cmp-power");
    const ultimo = syncAuthContextHeaders.mock.calls.at(-1)[0];
    expect(ultimo.companyId).toBe("cmp-power");
    expect(toast.error).toHaveBeenCalledWith(expect.stringMatching(/servidor não respondeu/i));
  });

  it("sem empresa anterior gravada no armazenamento, desfazer REMOVE a chave (não deixa 'null')", async () => {
    // O provider grava a empresa por omissão ao montar; é DEPOIS disso que se apaga, para o
    // «anterior» da troca ser, de facto, «nada gravado».
    const { result } = montar();
    await waitFor(() => expect(result.current.user?.companies).toHaveLength(2));
    localStorage.removeItem("active_company_id");
    sessionStorage.removeItem("activeCompanyId");
    rede.erroDaTroca = { response: { status: 502, data: "" } };

    await act(async () => {
      await result.current.switchActiveCompany("cmp-domus");
    });

    expect(localStorage.getItem("active_company_id")).toBeNull();
    expect(sessionStorage.getItem("activeCompanyId")).toBeNull();
    expect(recarregar).not.toHaveBeenCalled();
  });

  it("contraprova: servidor a responder → troca, sincroniza e recarrega", async () => {
    const { devolvido } = await trocarParaADomus();

    expect(devolvido).toBe(true);
    expect(recarregar).toHaveBeenCalledTimes(1);
    expect(localStorage.getItem("active_company_id")).toBe("cmp-domus");
    expect(toast.error).not.toHaveBeenCalled();
  });

  it.each([400, 403, 404, 500])(
    "contraprova: um %s da aplicação NÃO desfaz a troca (o cliente já tem a empresa nos cabeçalhos)",
    async (estado) => {
      rede.erroDaTroca = { response: { status: estado, data: { detail: "x" } } };

      const { devolvido } = await trocarParaADomus();

      expect(devolvido).toBe(true);
      expect(recarregar).toHaveBeenCalledTimes(1);
      expect(localStorage.getItem("active_company_id")).toBe("cmp-domus");
    },
  );
});
