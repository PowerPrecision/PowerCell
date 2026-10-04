/**
 * O separador "As Minhas Visitas" do Portal — a página montada a SÉRIO.
 *
 * O QUE ESTE FICHEIRO DEFENDE (Lote 9, Fase B)
 * ============================================
 * O PACOTE CB comentou o BOTÃO de acesso e deixou a tab escrita — o
 * endpoint (`POST /portal/visits/request`), o scraper anti-bot com 11
 * portais e o ecrã existiam todos, e a funcionalidade estava inalcançável
 * por três linhas de comentário. **Um separador que não existe não produz
 * erro nenhum**, e foi assim que ficou meses sem ninguém reparar.
 *
 * A regra do `SystemConfigPage.seccoes.test.jsx` aplica-se aqui: quem
 * acrescenta (ou reactiva) um separador tem de montar a PÁGINA. Um teste
 * do componente do separador passava com o botão comentado.
 *
 * A página é montada a sério, como nos ficheiros vizinhos: um duplo que
 * reproduza a ligação valida o duplo.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
      if (u.includes("/portal/visits")) return resposta({ visits: VISITAS });
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

const VISITAS = [
  {
    id: "v-pedida",
    status: "solicitada",
    status_label: "A aguardar agendamento",
    property_title: "T3 em Cascais com vista mar",
    property_url: "https://www.idealista.pt/imovel/111/",
    scraped_url: "https://www.idealista.pt/imovel/111/",
    created_at: "2026-10-01T09:00:00Z",
  },
  {
    id: "v-marcada",
    status: "agendada",
    status_label: "Agendada",
    property_title: "T2 em Leiria",
    formatted_date: "20/11/2026 às 15:00",
    created_at: "2026-09-20T09:00:00Z",
  },
];

async function montarPortal() {
  const { default: ClientPortal } = await import("../ClientPortal");
  render(<ClientPortal />);
  // A página só está pronta quando o `/portal/status` resolveu.
  await screen.findByRole("button", { name: /as minhas visitas|visitas/i });
}

describe("Portal — o separador das Visitas", () => {
  it("o botão de acesso EXISTE (estava comentado)", async () => {
    await montarPortal();
    expect(
      screen.getByRole("button", { name: /as minhas visitas|visitas/i })
    ).toBeInTheDocument();
  });

  it("o contador mostra os pedidos à espera de agendamento", async () => {
    await montarPortal();
    const botao = screen.getByRole("button", {
      name: /as minhas visitas|visitas/i,
    });
    // Uma `solicitada` nas duas visitas semeadas.
    expect(botao).toHaveTextContent("1");
  });

  it("clicar no botão abre o separador e mostra as visitas", async () => {
    await montarPortal();
    await userEvent.click(
      screen.getByRole("button", { name: /as minhas visitas|visitas/i })
    );
    expect(
      await screen.findByText("T3 em Cascais com vista mar")
    ).toBeInTheDocument();
    expect(screen.getByText("T2 em Leiria")).toBeInTheDocument();
  });

  it("o separador tem o campo para submeter o link de um anúncio", async () => {
    // É o ponto 3 do lote: o cliente cola o URL e o motor extrai os dados.
    await montarPortal();
    await userEvent.click(
      screen.getByRole("button", { name: /as minhas visitas|visitas/i })
    );
    const campos = await screen.findAllByPlaceholderText(/cole aqui o link/i);
    expect(campos.length).toBeGreaterThan(0);
  });

  it("submeter um link chama o endpoint do pedido de visita", async () => {
    await montarPortal();
    await userEvent.click(
      screen.getByRole("button", { name: /as minhas visitas|visitas/i })
    );
    const campo = (await screen.findAllByPlaceholderText(/cole aqui o link/i))[0];
    await userEvent.type(campo, "https://www.idealista.pt/imovel/999/");

    await userEvent.click(
      screen.getByRole("button", { name: /pedir visita/i })
    );

    await waitFor(() =>
      expect(
        globalThis.fetch.mock.calls.some(([u]) =>
          String(u).includes("/portal/visits/request")
        )
      ).toBe(true)
    );
  });

  it("uma lista de visitas com a forma errada não rebenta o Portal", async () => {
    // `|| []` devolvia o objecto (é truthy) e o `.filter` do contador
    // rebentava — só `Array.isArray` distingue (§ 27.38).
    globalThis.fetch.mockImplementation(async (url) => {
      contar(url);
      const u = String(url);
      if (u.includes("/portal/visits")) return resposta({ visits: { 0: VISITAS[0] } });
      if (u.includes("/portal/messages/unread")) return resposta({ count: 0 });
      if (u.includes("/portal/messages")) return resposta({ messages: MENSAGENS });
      if (u.includes("/portal/status")) {
        return resposta({
          process: {
            id: "proc-1", client_name: "Ana Silva", status: "analise",
            status_label: "Em análise", status_color: "#0ea5e9",
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
      return resposta({});
    });

    await montarPortal();
    const botao = screen.getByRole("button", {
      name: /as minhas visitas|visitas/i,
    });
    expect(botao).toBeInTheDocument();
    // Sem contador: a lista não é uma lista, logo não há pedidos a contar.
    expect(botao).not.toHaveTextContent("1");
  });
});
