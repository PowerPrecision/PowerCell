/**
 * A sessão do parceiro: quatro vias para dentro/fora e a regra de que um
 * estado de carregamento nunca cai no ramo de um estado de dados.
 */
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import sessao from "@/test/fixtures/parceiro/sessao.json";
import perfil from "@/test/fixtures/parceiro/perfil.json";

vi.mock("@/services/partnerApi", () => ({
  entrar: vi.fn(),
  obterPerfil: vi.fn(),
  aceitarConvite: vi.fn(),
  mudarPalavraPasse: vi.fn(),
}));

import { PartnerAuthProvider, usePartnerAuth } from "../PartnerAuthContext";
import * as api from "@/services/partnerApi";
import { queryKeys } from "@/lib/queryClient";
import { anunciarSessaoExpirada, guardarSessao, lerToken } from "@/utils/partnerSession";

function Sonda() {
  const { estado, partner, entrar, sair } = usePartnerAuth();
  return (
    <div>
      <span data-testid="estado">{estado}</span>
      <span data-testid="nome">{partner?.name ?? "—"}</span>
      <button onClick={() => entrar("rui@parceiros.pt", "x")}>entrar</button>
      <button onClick={sair}>sair</button>
    </div>
  );
}

function montar() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const ui = render(
    <QueryClientProvider client={queryClient}>
      <PartnerAuthProvider><Sonda /></PartnerAuthProvider>
    </QueryClientProvider>
  );
  return { queryClient, ...ui };
}

beforeEach(() => {
  sessionStorage.clear();
  vi.clearAllMocks();
});

describe("PartnerAuthProvider", () => {
  it("sem token: anónimo, e não pergunta nada ao servidor", () => {
    montar();
    expect(screen.getByTestId("estado")).toHaveTextContent("anonimo");
    expect(api.obterPerfil).not.toHaveBeenCalled();
  });

  it("com token: «a carregar» até o servidor confirmar — nunca autenticado à partida", async () => {
    guardarSessao("tok", 3600);
    let resolver;
    api.obterPerfil.mockReturnValue(new Promise((r) => { resolver = r; }));
    montar();
    expect(screen.getByTestId("estado")).toHaveTextContent("a_carregar");
    await act(async () => resolver(perfil));
    expect(screen.getByTestId("estado")).toHaveTextContent("autenticado");
    expect(screen.getByTestId("nome")).toHaveTextContent(perfil.name);
  });

  it("um /me que falha (suspenso, expirado) volta ao anónimo e apaga o token", async () => {
    guardarSessao("tok", 3600);
    api.obterPerfil.mockRejectedValue(new Error("401"));
    montar();
    await waitFor(() => expect(screen.getByTestId("estado")).toHaveTextContent("anonimo"));
    expect(lerToken()).toBeNull();
  });

  it("entrar guarda o token da resposta e passa a autenticado", async () => {
    api.entrar.mockResolvedValue(sessao);
    montar();
    await userEvent.click(screen.getByText("entrar"));
    await waitFor(() => expect(screen.getByTestId("estado")).toHaveTextContent("autenticado"));
    expect(lerToken()).toBe(sessao.access_token);
    expect(screen.getByTestId("nome")).toHaveTextContent(sessao.partner.name);
  });

  it("sair apaga o token E a cache do parceiro (nada fica para o próximo)", async () => {
    api.entrar.mockResolvedValue(sessao);
    const { queryClient } = montar();
    queryClient.setQueryData(queryKeys.partner.painel(), { total_de_casos: 3 });
    queryClient.setQueryData(["processes", "list"], { guardar: true });
    await userEvent.click(screen.getByText("entrar"));
    await waitFor(() => expect(screen.getByTestId("estado")).toHaveTextContent("autenticado"));
    await userEvent.click(screen.getByText("sair"));
    expect(screen.getByTestId("estado")).toHaveTextContent("anonimo");
    expect(lerToken()).toBeNull();
    expect(queryClient.getQueryData(queryKeys.partner.painel())).toBeUndefined();
    expect(queryClient.getQueryData(["processes", "list"])).toEqual({ guardar: true });
  });

  it("um 401 a meio da sessão (evento do cliente HTTP) leva ao login", async () => {
    api.entrar.mockResolvedValue(sessao);
    montar();
    await userEvent.click(screen.getByText("entrar"));
    await waitFor(() => expect(screen.getByTestId("estado")).toHaveTextContent("autenticado"));
    act(() => anunciarSessaoExpirada());
    expect(screen.getByTestId("estado")).toHaveTextContent("anonimo");
  });

  it("usar o hook fora do provider é um erro claro", () => {
    const erro = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Sonda />)).toThrow(/PartnerAuthProvider/);
    erro.mockRestore();
  });
});
