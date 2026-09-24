/**
 * Ponto 17 — as três camadas, vistas de cima.
 *
 * O teste decisivo aqui é o da CONTA DE PEDIDOS: o desenho inteiro
 * existe para que abrir um processo a meio da lista não custe nada à
 * base de dados. Um `expect(getProcessNeighbours).not.toHaveBeenCalled()`
 * é a única coisa que impede isso de regredir em silêncio.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../services/api", () => ({
  getProcessNeighbours: vi.fn(),
}));

import { getProcessNeighbours } from "../../services/api";
import { useProcessNeighbours } from "../useProcessNeighbours";
import {
  construirContextoDeNavegacao,
  guardarContexto,
  CHAVE_CONTEXTO,
} from "../../utils/processNavigation";

function contexto(over = {}) {
  return construirContextoDeNavegacao({
    ids: ["a", "b", "c"],
    page: 1,
    size: 3,
    total: 3,
    origem: "/processos",
    params: { view_mode: "all", labels: ["VIP", "Urgente"] },
    ...over,
  });
}

function montar(processId, { state, sessao } = {}) {
  if (sessao) guardarContexto(sessao);
  return renderHook(() => useProcessNeighbours(processId), {
    wrapper: ({ children }) => (
      <MemoryRouter
        initialEntries={[{
          pathname: `/process/${processId}`,
          state: state ? { contextoDeNavegacao: state } : undefined,
        }]}
      >
        {children}
      </MemoryRouter>
    ),
  });
}

describe("useProcessNeighbours", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
  });

  it("camada 1: resolve os vizinhos do state SEM pedido nenhum", async () => {
    const { result } = montar("b", { state: contexto() });
    expect(result.current.anteriorId).toBe("a");
    expect(result.current.seguinteId).toBe("c");
    expect(result.current.posicao).toBe(2);
    expect(getProcessNeighbours).not.toHaveBeenCalled();
  });

  it("camada 2: usa a sessão quando o state se perdeu (F5)", async () => {
    const { result } = montar("b", { sessao: contexto() });
    expect(result.current.disponivel).toBe(true);
    expect(result.current.seguinteId).toBe("c");
    expect(getProcessNeighbours).not.toHaveBeenCalled();
  });

  it("o state manda sobre a sessão", () => {
    // Uma sessão velha de outra listagem não pode sequestrar as setas
    // da listagem de onde o utilizador acabou de vir.
    guardarContexto(contexto({ ids: ["x", "y", "z"] }));
    const { result } = montar("b", { state: contexto() });
    expect(result.current.anteriorId).toBe("a");
  });

  it("camada 3: só pergunta ao servidor na fronteira da página", async () => {
    getProcessNeighbours.mockResolvedValue({
      data: { previous_id: "z", next_id: "d", position: 4, total: 9 },
    });
    const { result } = montar("c", {
      state: contexto({ page: 2, size: 3, total: 9 }),
    });

    await waitFor(() => expect(result.current.seguinteId).toBe("d"));
    expect(getProcessNeighbours).toHaveBeenCalledTimes(1);
    // O lado que a página já sabia não é substituído pelo servidor.
    expect(result.current.anteriorId).toBe("b");
  });

  it("camada 3: leva os filtros com as etiquetas repetidas", async () => {
    getProcessNeighbours.mockResolvedValue({ data: {} });
    montar("c", { state: contexto({ page: 2, size: 3, total: 9 }) });

    await waitFor(() => expect(getProcessNeighbours).toHaveBeenCalled());
    const [idPedido, params] = getProcessNeighbours.mock.calls[0];
    expect(idPedido).toBe("c");
    expect(params).toBeInstanceOf(URLSearchParams);
    expect(params.getAll("labels")).toEqual(["VIP", "Urgente"]);
    expect(params.get("view_mode")).toBe("all");
  });

  it("uma falha da camada 3 deixa a seta desactivada e não rebenta", async () => {
    getProcessNeighbours.mockRejectedValue(new Error("rede em baixo"));
    const { result } = montar("c", {
      state: contexto({ page: 2, size: 3, total: 9 }),
    });

    await waitFor(() => expect(result.current.aCarregar).toBe(false));
    expect(result.current.seguinteId).toBeNull();
    expect(result.current.disponivel).toBe(true);
  });

  it("sem contexto nenhum não há setas nem pedidos", () => {
    const { result } = montar("b");
    expect(result.current.disponivel).toBe(false);
    expect(getProcessNeighbours).not.toHaveBeenCalled();
  });

  it("um processo fora da listagem guardada não gera pedidos", () => {
    // Chegou por pesquisa global. Perguntar ao servidor os vizinhos de
    // uma listagem a que ele não pertence seria um pedido inútil em
    // TODAS as aberturas por fora da lista.
    const { result } = montar("fora-da-lista", { state: contexto() });
    expect(result.current.disponivel).toBe(false);
    expect(getProcessNeighbours).not.toHaveBeenCalled();
  });

  it("uma sessão corrompida não impede a página de abrir", () => {
    window.sessionStorage.setItem(CHAVE_CONTEXTO, "{corrompido");
    const { result } = montar("b");
    expect(result.current.disponivel).toBe(false);
  });
});
