/**
 * usePortalRealtime — a ligação do CLIENTE ao `/api/ws/portal`.
 *
 * O que estes testes provam, e que é o contrato do
 * `FRONTEND_GUIDELINES.md` § 9:
 *   * liga ao endpoint do Portal (nunca ao `/ws/notifications` da equipa);
 *   * **nunca** envia `join_process_room` — a sala é ditada pelo servidor;
 *   * `ping` é a única mensagem que sai;
 *   * reconecta com backoff, MAS não reconecta em 4001/4002 (veredictos
 *     sobre o token — insistir repetia-os para sempre);
 *   * ao (re)ligar faz UMA leitura para fechar a lacuna do tempo em que
 *     esteve em baixo.
 *
 * O `WebSocket` é falseado ao nível da API do browser (construtor, `send`,
 * `close`, os handlers) — é a fronteira, e é o único falso aqui. A decisão do
 * que fazer com cada evento é a real (`utils/portalRealtime.js`).
 */
import { renderHook, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { usePortalRealtime } from "../usePortalRealtime";

vi.mock("../../utils/apiBaseUrl", () => ({
  API_BASE_URL: "http://localhost:8001",
}));

/** Todos os sockets criados no teste, para inspecção. */
let sockets = [];

class WebSocketFalso {
  static OPEN = 1;
  static CLOSED = 3;

  constructor(url) {
    this.url = url;
    this.readyState = WebSocketFalso.OPEN;
    this.enviado = [];
    this.fechadoCom = null;
    this.onopen = null;
    this.onmessage = null;
    this.onclose = null;
    this.onerror = null;
    sockets.push(this);
  }

  send(texto) {
    this.enviado.push(JSON.parse(texto));
  }

  close(code, reason) {
    this.readyState = WebSocketFalso.CLOSED;
    this.fechadoCom = { code, reason };
  }

  // --- ajudas para o teste conduzir o socket ---
  abrir() {
    this.onopen?.({});
  }

  entregar(envelope) {
    this.onmessage?.({ data: JSON.stringify(envelope) });
  }

  entregarTextoCru(texto) {
    this.onmessage?.({ data: texto });
  }

  morrer(code = 1006) {
    this.readyState = WebSocketFalso.CLOSED;
    this.onclose?.({ code });
  }
}

beforeEach(() => {
  sockets = [];
  vi.stubGlobal("WebSocket", WebSocketFalso);
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function montar(extra = {}) {
  const onMensagens = vi.fn();
  const onDocumentos = vi.fn();
  const onAviso = vi.fn();
  const mensagens = extra.mensagens || [];

  const resultado = renderHook(() =>
    usePortalRealtime({
      enabled: true,
      obterToken: extra.obterToken || (() => "magic-token"),
      onMensagens,
      onDocumentos,
      onAviso,
      mensagensActuais: () => mensagens,
    }),
  );

  return { ...resultado, onMensagens, onDocumentos, onAviso };
}

describe("a ligação", () => {
  it("liga ao endpoint do PORTAL, com o token na query string", () => {
    montar();
    expect(sockets).toHaveLength(1);
    expect(sockets[0].url).toBe(
      "ws://localhost:8001/api/ws/portal?token=magic-token",
    );
  });

  it("NUNCA liga ao endpoint de staff", () => {
    montar();
    expect(sockets[0].url).not.toContain("/ws/notifications");
  });

  it("sem token não abre socket nenhum", () => {
    montar({ obterToken: () => null });
    expect(sockets).toHaveLength(0);
  });

  it("não liga quando desactivado (sessão não verificada)", () => {
    renderHook(() =>
      usePortalRealtime({
        enabled: false,
        obterToken: () => "magic-token",
        onMensagens: vi.fn(),
      }),
    );
    expect(sockets).toHaveLength(0);
  });

  it("o token é lido NO MOMENTO da ligação, não na montagem", async () => {
    // Entre tentativas de reconexão o token pode ter sido renovado.
    let token = "token-antigo";
    const { onMensagens } = montar({ obterToken: () => token });
    act(() => sockets[0].abrir());

    token = "token-novo";
    act(() => sockets[0].morrer());
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });

    expect(sockets[1].url).toContain("token=token-novo");
    expect(onMensagens).toHaveBeenCalled();
  });
});

describe("o que o cliente ENVIA", () => {
  it("nunca envia join_process_room — a sala é ditada pelo servidor", () => {
    montar();
    act(() => sockets[0].abrir());
    act(() => {
      vi.advanceTimersByTime(120000);
    });

    const tipos = sockets[0].enviado.map((m) => m.type);
    expect(tipos).not.toContain("join_process_room");
    expect(tipos).not.toContain("leave_process_room");
  });

  it("envia ping de 30 em 30 segundos, e nada mais", () => {
    montar();
    act(() => sockets[0].abrir());
    act(() => {
      vi.advanceTimersByTime(90000);
    });

    expect(sockets[0].enviado).toEqual([
      { type: "ping" },
      { type: "ping" },
      { type: "ping" },
    ]);
  });

  it("não envia nada antes de o socket abrir", () => {
    montar();
    act(() => {
      vi.advanceTimersByTime(60000);
    });
    expect(sockets[0].enviado).toEqual([]);
  });

  it("para de enviar ping depois de o socket morrer", () => {
    montar();
    act(() => sockets[0].abrir());
    act(() => {
      vi.advanceTimersByTime(30000);
    });
    expect(sockets[0].enviado).toHaveLength(1);

    act(() => sockets[0].morrer());
    act(() => {
      vi.advanceTimersByTime(120000);
    });
    expect(sockets[0].enviado).toHaveLength(1);
  });
});

describe("a recuperação da lacuna", () => {
  it("ao ligar faz UMA leitura das mensagens", () => {
    // Sem isto, reconectar deixava a conversa desactualizada até à mensagem
    // SEGUINTE — e o polling está parado enquanto o socket está ligado.
    const { onMensagens } = montar();
    expect(onMensagens).not.toHaveBeenCalled();

    act(() => sockets[0].abrir());
    expect(onMensagens).toHaveBeenCalledTimes(1);
  });

  it("ao RE-ligar faz outra leitura", async () => {
    const { onMensagens } = montar();
    act(() => sockets[0].abrir());
    act(() => sockets[0].morrer());

    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    act(() => sockets[1].abrir());

    expect(onMensagens).toHaveBeenCalledTimes(2);
  });
});

describe("os eventos recebidos", () => {
  it("uma mensagem nova manda recarregar", () => {
    const { onMensagens } = montar();
    act(() => sockets[0].abrir());
    onMensagens.mockClear();

    act(() =>
      sockets[0].entregar({
        type: "portal_message",
        data: { id: "m9", content: "Bom dia" },
      }),
    );

    expect(onMensagens).toHaveBeenCalledTimes(1);
  });

  it("o eco da própria mensagem não recarrega", () => {
    const { onMensagens } = montar({ mensagens: [{ id: "m1" }] });
    act(() => sockets[0].abrir());
    onMensagens.mockClear();

    act(() =>
      sockets[0].entregar({
        type: "portal_message",
        data: { id: "m1", sender_type: "client" },
      }),
    );

    expect(onMensagens).not.toHaveBeenCalled();
  });

  it("o progresso do Estado recarrega documentos e avisa", () => {
    const { onDocumentos, onAviso } = montar();
    act(() => sockets[0].abrir());

    act(() =>
      sockets[0].entregar({
        type: "portal_gov_progress",
        data: { source: "auto_financas", estado: "concluido", documents_count: 2 },
      }),
    );

    expect(onDocumentos).toHaveBeenCalledTimes(1);
    expect(onAviso).toHaveBeenCalledWith({
      tipo: "sucesso",
      texto: expect.stringContaining("2 documentos"),
    });
  });

  it("uma falha do Estado avisa mas não recarrega documentos", () => {
    const { onDocumentos, onAviso } = montar();
    act(() => sockets[0].abrir());

    act(() =>
      sockets[0].entregar({
        type: "portal_gov_progress",
        data: { estado: "falhou", motivo: "credenciais_invalidas" },
      }),
    );

    expect(onDocumentos).not.toHaveBeenCalled();
    expect(onAviso.mock.calls[0][0].tipo).toBe("erro");
  });

  it("um evento interno não tem efeito nenhum", () => {
    const { onMensagens, onDocumentos, onAviso } = montar();
    act(() => sockets[0].abrir());
    onMensagens.mockClear();

    for (const tipo of ["process_updated", "document_uploaded", "new_email"]) {
      act(() => sockets[0].entregar({ type: tipo, data: { x: 1 } }));
    }

    expect(onMensagens).not.toHaveBeenCalled();
    expect(onDocumentos).not.toHaveBeenCalled();
    expect(onAviso).not.toHaveBeenCalled();
  });

  it("JSON inválido não rebenta o socket", () => {
    const { onMensagens } = montar();
    act(() => sockets[0].abrir());
    onMensagens.mockClear();

    act(() => sockets[0].entregarTextoCru("isto não é json {"));

    expect(onMensagens).not.toHaveBeenCalled();
    // E continua a funcionar depois.
    act(() =>
      sockets[0].entregar({ type: "portal_message", data: { id: "m1" } }),
    );
    expect(onMensagens).toHaveBeenCalledTimes(1);
  });
});

describe("reconexão", () => {
  it("reconecta com backoff exponencial", async () => {
    montar();
    act(() => sockets[0].morrer(1006));

    await act(async () => {
      vi.advanceTimersByTime(999);
    });
    expect(sockets).toHaveLength(1);

    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    expect(sockets).toHaveLength(2);

    // A segunda espera é o dobro.
    act(() => sockets[1].morrer(1006));
    await act(async () => {
      vi.advanceTimersByTime(1999);
    });
    expect(sockets).toHaveLength(2);
    await act(async () => {
      vi.advanceTimersByTime(1);
    });
    expect(sockets).toHaveLength(3);
  });

  it("o backoff é reiniciado depois de uma ligação bem sucedida", async () => {
    montar();
    act(() => sockets[0].morrer(1006));
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    act(() => sockets[1].abrir());
    act(() => sockets[1].morrer(1006));

    // Voltou a 1s, não ficou nos 2s.
    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    expect(sockets).toHaveLength(3);
  });

  it.each([4001, 4002])(
    "NÃO reconecta no código %i — é um veredicto sobre o token",
    async (code) => {
      // Reconectar com o mesmo token repetia o mesmo veredicto para sempre.
      montar();
      act(() => sockets[0].morrer(code));

      await act(async () => {
        vi.advanceTimersByTime(120000);
      });

      expect(sockets).toHaveLength(1);
    },
  );

  it("isConnected reflecte o estado, e é isso que trava o polling", () => {
    // Sem `waitFor`: ele faz polling com temporizadores REAIS e aqui estão
    // falseados — a actualização de estado já chega dentro do `act`.
    const { result } = montar();
    expect(result.current.isConnected).toBe(false);

    act(() => sockets[0].abrir());
    expect(result.current.isConnected).toBe(true);

    act(() => sockets[0].morrer(1006));
    expect(result.current.isConnected).toBe(false);
  });
});

describe("desmontagem", () => {
  it("fecha o socket e não agenda reconexão", async () => {
    const { unmount } = montar();
    act(() => sockets[0].abrir());

    unmount();

    expect(sockets[0].fechadoCom.code).toBe(1000);
    await act(async () => {
      vi.advanceTimersByTime(120000);
    });
    expect(sockets).toHaveLength(1);
  });

  it("para o ping ao desmontar", () => {
    const { unmount } = montar();
    act(() => sockets[0].abrir());
    const enviadosAntes = sockets[0].enviado.length;

    unmount();
    act(() => {
      vi.advanceTimersByTime(120000);
    });

    expect(sockets[0].enviado).toHaveLength(enviadosAntes);
  });

  it("desactivar fecha a ligação", () => {
    const { result, rerender } = renderHook(
      ({ enabled }) =>
        usePortalRealtime({
          enabled,
          obterToken: () => "magic-token",
          onMensagens: vi.fn(),
        }),
      { initialProps: { enabled: true } },
    );

    act(() => sockets[0].abrir());
    expect(result.current.isConnected).toBe(true);

    act(() => rerender({ enabled: false }));

    expect(result.current.isConnected).toBe(false);
    expect(sockets[0].fechadoCom).not.toBeNull();
  });
});
