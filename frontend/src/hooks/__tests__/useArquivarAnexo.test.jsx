import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getEmailArchiveSuggestions: vi.fn(),
  archiveEmailAttachment: vi.fn(),
}));
vi.mock("../../services/api", () => api);

const avisos = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast: avisos }));

import useArquivarAnexo from "../useArquivarAnexo";

const ANEXO = { id: "a1", filename: "cc.pdf" };
const SUGESTOES = {
  enderecos: ["joana@x.pt"],
  sugestoes: [{ process_id: "p-1", client_name: "Joana", ja_indexado: false }],
  sugerido: "p-1",
};

beforeEach(() => {
  vi.clearAllMocks();
  api.getEmailArchiveSuggestions.mockResolvedValue({ data: SUGESTOES });
  api.archiveEmailAttachment.mockResolvedValue({ data: { success: true, intake: { fila_ia: true } } });
});

describe("useArquivarAnexo", () => {
  it("abrir carrega as sugestões do email", async () => {
    const { result } = renderHook(() => useArquivarAnexo({ emailId: "em-1" }));
    act(() => result.current.abrir(ANEXO, 0));

    expect(result.current.aberto).toBe(true);
    expect(result.current.estado).toBe("a_carregar");
    await waitFor(() => expect(result.current.estado).toBe("pronto"));
    expect(api.getEmailArchiveSuggestions).toHaveBeenCalledWith("em-1");
    expect(result.current.resposta).toEqual(SUGESTOES);
  });

  it("sem email aberto não faz nada", () => {
    const { result } = renderHook(() => useArquivarAnexo({ emailId: null }));
    act(() => result.current.abrir(ANEXO, 0));
    expect(result.current.aberto).toBe(false);
    expect(api.getEmailArchiveSuggestions).not.toHaveBeenCalled();
  });

  it("um erro do servidor fica no diálogo e permite tentar de novo", async () => {
    api.getEmailArchiveSuggestions.mockRejectedValueOnce({ response: { data: { detail: "Sem rede" } } });
    const { result } = renderHook(() => useArquivarAnexo({ emailId: "em-1" }));
    act(() => result.current.abrir(ANEXO, 0));

    await waitFor(() => expect(result.current.estado).toBe("erro"));
    expect(result.current.erro).toBe("Sem rede");

    act(() => result.current.tentarDeNovo());
    await waitFor(() => expect(result.current.estado).toBe("pronto"));
  });

  it("confirmar envia o processo e a pasta, avisa e fecha", async () => {
    const onArquivado = vi.fn();
    const { result } = renderHook(() => useArquivarAnexo({ emailId: "em-1", onArquivado }));
    act(() => result.current.abrir(ANEXO, 2));
    await waitFor(() => expect(result.current.estado).toBe("pronto"));

    await act(() => result.current.confirmar({ processId: "p-1", category: "Outros" }));

    expect(api.archiveEmailAttachment).toHaveBeenCalledWith("em-1", "a1", {
      process_id: "p-1",
      category: "Outros",
    });
    expect(avisos.success).toHaveBeenCalledWith(expect.stringMatching(/pasta Index/));
    expect(onArquivado).toHaveBeenCalledWith(2, expect.any(Object), "p-1");
    expect(result.current.aberto).toBe(false);
  });

  it("um anexo sem id usa o id composto email:índice", async () => {
    const { result } = renderHook(() => useArquivarAnexo({ emailId: "em-1" }));
    act(() => result.current.abrir({ filename: "x.pdf" }, 3));
    await waitFor(() => expect(result.current.estado).toBe("pronto"));
    await act(() => result.current.confirmar({ processId: "p-1", category: "Outros" }));
    expect(api.archiveEmailAttachment.mock.calls[0][1]).toBe("em-1:3");
  });

  it("uma recusa do servidor mantém o diálogo aberto e mostra o motivo", async () => {
    api.archiveEmailAttachment.mockRejectedValueOnce({
      response: { status: 403, data: { detail: "Sem permissão X" } },
    });
    const { result } = renderHook(() => useArquivarAnexo({ emailId: "em-1" }));
    act(() => result.current.abrir(ANEXO, 0));
    await waitFor(() => expect(result.current.estado).toBe("pronto"));

    await act(() => result.current.confirmar({ processId: "p-1", category: "Outros" }));

    expect(avisos.error).toHaveBeenCalledWith("Sem permissão X");
    expect(result.current.aberto).toBe(true);
    expect(result.current.arquivando).toBe(false);
  });

  it("não arquiva duas vezes em paralelo", async () => {
    let resolver;
    api.archiveEmailAttachment.mockReturnValueOnce(new Promise((r) => { resolver = r; }));
    const { result } = renderHook(() => useArquivarAnexo({ emailId: "em-1" }));
    act(() => result.current.abrir(ANEXO, 0));
    await waitFor(() => expect(result.current.estado).toBe("pronto"));

    act(() => { result.current.confirmar({ processId: "p-1", category: "Outros" }); });
    await waitFor(() => expect(result.current.arquivando).toBe(true));
    await act(() => result.current.confirmar({ processId: "p-1", category: "Outros" }));
    expect(api.archiveEmailAttachment).toHaveBeenCalledTimes(1);

    await act(async () => { resolver({ data: {} }); });
  });

  it("a resposta de um pedido antigo não aparece num diálogo novo", async () => {
    let resolverPrimeiro;
    api.getEmailArchiveSuggestions
      .mockReturnValueOnce(new Promise((r) => { resolverPrimeiro = r; }))
      .mockResolvedValueOnce({ data: { sugestoes: [], enderecos: ["outro@x.pt"] } });

    const { result } = renderHook(() => useArquivarAnexo({ emailId: "em-1" }));
    act(() => result.current.abrir(ANEXO, 0));
    act(() => result.current.fechar());
    act(() => result.current.abrir({ id: "a2" }, 1));
    await waitFor(() => expect(result.current.estado).toBe("pronto"));

    await act(async () => { resolverPrimeiro({ data: SUGESTOES }); });
    expect(result.current.resposta.enderecos).toEqual(["outro@x.pt"]);
  });
});
