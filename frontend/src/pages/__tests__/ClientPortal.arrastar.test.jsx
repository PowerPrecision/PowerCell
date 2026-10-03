/**
 * Arrastar e largar no Portal do Cliente — a página montada a SÉRIO.
 *
 * O QUE ESTES TESTES DEFENDEM (Lote 6, ponto 3)
 *   1. **Que a zona de largar é toda a área útil do pedido**, e que um
 *      ficheiro largado nela é ENVIADO. Já havia um `onDrop` nesta linha, mas
 *      sem contador de entradas/saídas: o realce piscava ao passar sobre o
 *      conteúdo.
 *   2. **Que o arrasto respeita o MESMO `accept` do botão.** O `<input>` tinha
 *      `accept` e o caminho do `drop` não: largar um `.exe` ia direito ao
 *      upload. A parede real é a quarentena de magic bytes do servidor; isto é
 *      para o cliente não descobrir pelo erro depois de a rede ter
 *      transportado o ficheiro.
 *
 * A página é montada a sério, pela mesma razão do ficheiro vizinho: um duplo
 * que reproduza a ligação valida o duplo. O `Dropzone` e o `uploadFiles` reais
 * é que têm de concordar.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
          documents: {
            requested: [
              {
                id: "req-1",
                label: "IRS",
                icon: "📄",
                category: "IRS",
                status: "REQUESTED",
                attached_files: [],
              },
            ],
            uploaded: [],
            received: [],
            has_pending: true,
          },
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

vi.setConfig({ testTimeout: 20000 });

const ficheiro = (nome) =>
  new File(["conteudo"], nome, { type: "application/octet-stream" });

const arrastoDeFicheiros = (...nomes) => ({
  types: ["Files"],
  files: nomes.map(ficheiro),
  dropEffect: "",
});

async function montarPortal() {
  const { default: ClientPortal } = await import("../ClientPortal");
  render(<ClientPortal />);
  return screen.findByTestId("zona-upload-req-1");
}

describe("Portal — arrastar e largar documentos", () => {
  it("a zona de largar existe em toda a linha do pedido", async () => {
    const zona = await montarPortal();
    expect(zona).toBeInTheDocument();
    // E o botão continua lá: a zona embrulha, não substitui — é o caminho
    // acessível por teclado.
    expect(screen.getByRole("button", { name: /submeter/i })).toBeInTheDocument();
  });

  it("realça durante o arrasto e não pisca sobre o conteúdo", async () => {
    const zona = await montarPortal();
    const botao = screen.getByRole("button", { name: /submeter/i });

    fireEvent.dragEnter(zona, { dataTransfer: arrastoDeFicheiros("irs.pdf") });
    expect(zona).toHaveAttribute("data-arrasto-activo", "true");

    fireEvent.dragEnter(botao, { dataTransfer: arrastoDeFicheiros("irs.pdf") });
    fireEvent.dragLeave(botao, { dataTransfer: arrastoDeFicheiros("irs.pdf") });
    expect(zona).toHaveAttribute("data-arrasto-activo", "true");

    fireEvent.dragLeave(zona, { dataTransfer: arrastoDeFicheiros("irs.pdf") });
    expect(zona).toHaveAttribute("data-arrasto-activo", "false");
  });

  it("largar um PDF pede o URL de upload ao servidor", async () => {
    const zona = await montarPortal();
    chamadas = {};
    fireEvent.drop(zona, { dataTransfer: arrastoDeFicheiros("irs.pdf") });
    await waitFor(() =>
      expect(
        Object.keys(chamadas).some((c) => c.includes("upload-url"))
      ).toBe(true)
    );
  });

  it("largar um .exe NÃO envia nada e diz qual recusou", async () => {
    const zona = await montarPortal();
    chamadas = {};
    fireEvent.drop(zona, { dataTransfer: arrastoDeFicheiros("virus.exe") });

    expect(await screen.findByText(/virus\.exe/)).toBeInTheDocument();
    expect(Object.keys(chamadas).some((c) => c.includes("upload-url"))).toBe(false);
  });

  it("de uma mistura, só o aceite segue", async () => {
    const zona = await montarPortal();
    chamadas = {};
    fireEvent.drop(zona, {
      dataTransfer: arrastoDeFicheiros("irs.pdf", "virus.exe"),
    });
    await waitFor(() =>
      expect(
        Object.keys(chamadas).some((c) => c.includes("upload-url"))
      ).toBe(true)
    );
    expect(await screen.findByText(/virus\.exe/)).toBeInTheDocument();
  });
});
