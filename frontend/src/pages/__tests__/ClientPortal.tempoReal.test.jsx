/**
 * Testes de INTEGRAÇÃO — o Portal do Cliente ligado ao `/api/ws/portal`.
 *
 * O QUE ESTES TESTES DEFENDEM
 *   1. **Que o polling de 15s PARA quando o socket liga.** Era o objectivo
 *      do lote: o Portal interrogava `/portal/messages` e
 *      `/portal/messages/unread` de 15 em 15 segundos, para sempre.
 *   2. **Que o polling RETOMA quando a ligação cai.** É a metade que
 *      importa mais — sem ela, um socket morto deixava o cliente sem
 *      mensagens e ninguém dava por isso. A regra do Épico 10: o polling é
 *      RECURSO, não foi apagado.
 *   3. **Que uma mensagem recebida provoca uma leitura**, e que o eco da
 *      própria mensagem não provoca nenhuma.
 *
 * A página é montada a SÉRIO. Falso aqui só o que é fronteira: o `fetch`, o
 * `WebSocket` e o `useSlidingSession` (tem temporizadores próprios de
 * inactividade). O hook `usePortalRealtime`, os efeitos da página e a decisão
 * de `utils/portalRealtime` são os REAIS.
 *
 * Porque é que a página é montada em vez de um componente de teste que
 * reproduza a ligação: um duplo que reimplementa a lógica valida o duplo — foi
 * a lição que este projecto aprendeu duas vezes nos lotes da quarentena e dos
 * WebSockets. A prova de que o polling para tem de correr contra os efeitos
 * VERDADEIROS do `ClientPortal`.
 */
import { render, act, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../hooks/useSlidingSession", () => ({
  __esModule: true,
  default: () => ({ logout: vi.fn() }),
  useSlidingSession: () => ({ logout: vi.fn() }),
}));

vi.mock("../../utils/apiBaseUrl", () => ({
  API_BASE_URL: "http://localhost:8001",
  BACKEND_URL: "http://localhost:8001",
}));

let sockets = [];

class WebSocketFalso {
  static OPEN = 1;
  static CLOSED = 3;

  constructor(url) {
    this.url = url;
    this.readyState = WebSocketFalso.OPEN;
    this.enviado = [];
    this.onopen = null;
    this.onmessage = null;
    this.onclose = null;
    this.onerror = null;
    sockets.push(this);
  }

  send(texto) {
    this.enviado.push(JSON.parse(texto));
  }

  close() {
    this.readyState = WebSocketFalso.CLOSED;
  }

  abrir() {
    this.onopen?.({});
  }

  entregar(envelope) {
    this.onmessage?.({ data: JSON.stringify(envelope) });
  }

  morrer(code = 1006) {
    this.readyState = WebSocketFalso.CLOSED;
    this.onclose?.({ code });
  }
}

/** Contagem de chamadas por caminho, para provar o polling. */
let chamadas = {};

function contar(url) {
  const caminho = String(url).replace("http://localhost:8001", "");
  chamadas[caminho] = (chamadas[caminho] || 0) + 1;
}

function resposta(corpo) {
  return {
    ok: true,
    status: 200,
    json: async () => corpo,
    clone: () => resposta(corpo),
    headers: { get: () => "application/json" },
  };
}

const MENSAGENS = [
  { id: "m1", sender_type: "staff", content: "Bom dia", created_at: "2026-09-27T09:00:00Z" },
];

// O PRIMEIRO `montarPortal()` paga o `await import("../ClientPortal")`:
// a transformação da árvore INTEIRA da página, medida em ~4,9s contra os
// ~50ms dos testes seguintes, que já encontram o módulo em cache. Com o
// limite por omissão de 5s isto passava ou falhava conforme a carga da
// máquina — passou numa execução e estourou na seguinte, na mesma suite.
//
// O limite sobe em vez de se partir o teste em dois porque o custo é de
// ARRANQUE e não de espera: não há aqui nenhum `setTimeout` a ser
// aguardado, e encurtar a asserção não tiraria um milissegundo ao
// `import`. É o preço de montar a página a sério — que é exactamente o
// que este ficheiro existe para fazer.
vi.setConfig({ testTimeout: 20000 });

beforeEach(() => {
  sockets = [];
  chamadas = {};
  localStorage.clear();
  localStorage.setItem("portalToken", "magic-token-do-cliente");

  vi.stubGlobal("WebSocket", WebSocketFalso);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url) => {
      contar(url);
      const u = String(url);
      if (u.includes("/portal/messages/unread")) return resposta({ count: 0 });
      if (u.includes("/portal/messages")) return resposta({ messages: MENSAGENS });
      if (u.includes("/portal/status")) {
        // A forma REAL de `services/portal_status.py` — aninhada. Uma forma
        // inventada fazia a página rebentar no render (`process.client_name` de
        // `undefined`) e, sem render, os efeitos do polling nunca instalavam:
        // as contagens ficavam a 1 e o teste "provava" o contrário do que quer.
        return resposta({
          process: {
            id: "proc-1",
            client_name: "Ana Silva",
            status: "analise",
            status_label: "Em análise",
            status_color: "#0ea5e9",
            process_type: "credito_habitacao",
          },
          progress: { percent: 40, current_step: 2, total_steps: 5 },
          stepper: [],
          documents: { requested: [], uploaded: [], received: [], has_pending: false },
          rgpd: { status: "none", has_rgpd: false },
          team: { consultores: [], mediadores: [] },
          consultor: null,
          welcome_message: "Bem-vinda",
          has_process: true,
          client_id: "cli-1",
        });
      }
      if (u.includes("/portal/events")) return resposta({ events: [] });
      if (u.includes("/portal/recommendations")) return resposta({ recommendations: [] });
      if (u.includes("/portal/visits")) return resposta({ visits: [] });
      return resposta({});
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  vi.useRealTimers();
});

async function montarPortal() {
  const { default: ClientPortal } = await import("../ClientPortal");
  const utils = render(<ClientPortal />);
  // Espera que a sessão seja verificada e o socket aberto.
  await waitFor(() => expect(sockets.length).toBeGreaterThan(0));
  return utils;
}

describe("o Portal liga-se ao WebSocket do cliente", () => {
  it("abre o socket no endpoint do PORTAL com o token do cliente", async () => {
    await montarPortal();

    expect(sockets[0].url).toBe(
      "ws://localhost:8001/api/ws/portal?token=magic-token-do-cliente",
    );
  });

  it("nunca abre o socket de staff", async () => {
    await montarPortal();
    expect(sockets.every((s) => !s.url.includes("/ws/notifications"))).toBe(true);
  });

  it("não envia join_process_room — a sala é ditada pelo servidor", async () => {
    await montarPortal();
    act(() => sockets[0].abrir());

    const tipos = sockets[0].enviado.map((m) => m.type);
    expect(tipos).not.toContain("join_process_room");
  });
});

describe("o polling de recurso", () => {
  it("PARA quando o socket liga", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await montarPortal();

    await act(async () => {
      sockets[0].abrir();
    });

    const antes = chamadas["/portal/messages"] || 0;

    // Três voltas do intervalo de 15s.
    await act(async () => {
      vi.advanceTimersByTime(45000);
    });

    expect(chamadas["/portal/messages"]).toBe(antes);
  });

  it("RETOMA quando a ligação cai", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await montarPortal();

    await act(async () => {
      sockets[0].abrir();
    });
    await act(async () => {
      vi.advanceTimersByTime(45000);
    });
    const comSocket = chamadas["/portal/messages"] || 0;

    // A ligação morre: o polling tem de voltar sozinho.
    await act(async () => {
      sockets[0].morrer(1006);
    });
    await act(async () => {
      vi.advanceTimersByTime(30000);
    });

    expect(chamadas["/portal/messages"]).toBeGreaterThan(comSocket);
  });

  it("corre desde o início quando o socket NUNCA liga", async () => {
    // Um browser atrás de um proxy que bloqueia WebSockets: o socket é criado
    // mas nunca abre. O cliente não pode ficar sem mensagens.
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await montarPortal();

    const antes = chamadas["/portal/messages"] || 0;
    await act(async () => {
      vi.advanceTimersByTime(45000);
    });

    expect(chamadas["/portal/messages"]).toBeGreaterThan(antes);
  });

  it("a primeira leitura acontece mesmo antes de o socket abrir", async () => {
    await montarPortal();
    // O socket avisa do que CHEGA a partir da ligação; o que já existia vem
    // do GET inicial.
    expect(chamadas["/portal/messages"]).toBeGreaterThanOrEqual(1);
  });
});

describe("os eventos chegam ao estado da página", () => {
  it("uma mensagem NOVA provoca uma leitura", async () => {
    await montarPortal();
    await act(async () => {
      sockets[0].abrir();
    });
    const antes = chamadas["/portal/messages"];

    await act(async () => {
      sockets[0].entregar({
        type: "portal_message",
        data: { id: "m-nova", sender_type: "staff", content: "Documento aprovado" },
      });
    });

    expect(chamadas["/portal/messages"]).toBe(antes + 1);
  });

  it("o ECO de uma mensagem já conhecida NÃO provoca leitura", async () => {
    await montarPortal();
    await act(async () => {
      sockets[0].abrir();
    });
    await waitFor(() => expect(chamadas["/portal/messages"]).toBeGreaterThan(0));
    const antes = chamadas["/portal/messages"];

    await act(async () => {
      // `m1` já está na lista devolvida pelo GET.
      sockets[0].entregar({
        type: "portal_message",
        data: { id: "m1", sender_type: "client", content: "Bom dia" },
      });
    });

    expect(chamadas["/portal/messages"]).toBe(antes);
  });

  it("um evento INTERNO não provoca leitura nenhuma", async () => {
    await montarPortal();
    await act(async () => {
      sockets[0].abrir();
    });
    const antes = chamadas["/portal/messages"];

    await act(async () => {
      for (const tipo of ["process_updated", "document_uploaded", "new_email"]) {
        sockets[0].entregar({ type: tipo, data: { process_id: "p1" } });
      }
    });

    expect(chamadas["/portal/messages"]).toBe(antes);
  });

  it("o progresso do Estado recarrega os dados do portal", async () => {
    await montarPortal();
    await act(async () => {
      sockets[0].abrir();
    });
    const antes = chamadas["/portal/status"] || 0;

    await act(async () => {
      sockets[0].entregar({
        type: "portal_gov_progress",
        data: { source: "auto_financas", estado: "concluido", documents_count: 2 },
      });
    });

    await waitFor(() =>
      expect(chamadas["/portal/status"]).toBeGreaterThan(antes),
    );
  });
});
