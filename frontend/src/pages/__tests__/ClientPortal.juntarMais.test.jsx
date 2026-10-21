/**
 * Pedidos com várias peças no Portal do Cliente — a quantidade é uma RECOMENDAÇÃO.
 *
 * Decisão da direcção (Out 2026): «últimos 3 recibos» cumpre-se com 1 ficheiro (o
 * processo avança), mas o cartão não desaparece: continua visível a convidar a
 * juntar mais, sem nada de obrigatório. A forma dos dados é a REAL de
 * `services/portal_status.py` (com `suggested_count`) e os valores são diferentes
 * das omissões (um erro de leitura seria indistinguível de uma leitura certa).
 */
import { render, screen, within } from "@testing-library/react";
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

vi.setConfig({ testTimeout: 20000 });

const ficheiro = (n) => ({ file_id: `f${n}`, filename: `recibo-${n}.pdf`, s3_path: `x/recibo-${n}.pdf` });

let documentos;

function resposta(corpo) {
  return {
    ok: true,
    status: 200,
    json: async () => corpo,
    clone: () => resposta(corpo),
    headers: { get: () => "application/json" },
  };
}

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("portalToken", "magic-token-do-cliente");
  vi.stubGlobal(
    "WebSocket",
    class {
      static OPEN = 1;
      static CLOSED = 3;
      constructor() {
        this.readyState = 3;
      }
      send() {}
      close() {}
    },
  );
  documentos = { requested: [], uploaded: [], received: [], has_pending: false };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url) => {
      const u = String(url);
      if (u.includes("/portal/messages/unread")) return resposta({ count: 0 });
      if (u.includes("/portal/messages")) return resposta({ messages: [] });
      if (u.includes("/portal/status")) {
        return resposta({
          process: { id: "proc-1", client_name: "Ana Silva", status: "analise", status_label: "Em análise", status_color: "#0ea5e9", process_type: "credito_habitacao" },
          progress: { percent: 40, current_step: 2, total_steps: 5 },
          stepper: [],
          documents: documentos,
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
});

async function montar() {
  const { default: ClientPortal } = await import("../ClientPortal");
  render(<ClientPortal />);
}

const pedido = (extra) => ({
  id: "rec",
  label: "Recibos de Vencimento",
  category_label: "Recibos de Vencimento",
  icon: "📄",
  category: "Recibos",
  suggested_count: 4,
  expected_count: 4,
  ...extra,
});

describe("Portal — a quantidade é uma recomendação", () => {
  it("pedido pendente sem ficheiros diz que pode enviar menos", async () => {
    documentos = { ...documentos, has_pending: true, requested: [pedido({ status: "REQUESTED", attached_files: [], uploaded_count: 0 })] };
    await montar();
    expect(await screen.findByTestId("convite-juntar-mais")).toHaveTextContent("Recomendado: 4 ficheiros — pode enviar menos.");
    expect(screen.getByRole("button", { name: /submeter/i })).toBeInTheDocument();
  });

  it("um pedido JÁ cumprido com 1 ficheiro continua visível, a convidar a juntar mais", async () => {
    documentos = {
      ...documentos,
      received: [pedido({ status: "RECEIVED", filename: "recibo-1.pdf", attached_files: [ficheiro(1)], uploaded_count: 1 })],
    };
    await montar();
    const seccao = await screen.findByTestId("pedidos-para-juntar-mais");
    expect(within(seccao).getByTestId("convite-juntar-mais")).toHaveTextContent("Pode juntar mais — recomendado: 4.");
    expect(within(seccao).getByRole("button", { name: /adicionar mais/i })).toBeInTheDocument();
    // E continua a constar dos Recebidos (o pedido está cumprido).
    expect(screen.getByText(/Documentos Recebidos \(1\)/)).toBeInTheDocument();
  });

  it("com a recomendação atingida o convite desaparece", async () => {
    documentos = {
      ...documentos,
      received: [pedido({ status: "RECEIVED", attached_files: [1, 2, 3, 4].map(ficheiro), uploaded_count: 4 })],
    };
    await montar();
    await screen.findByText(/Documentos Recebidos \(1\)/);
    expect(screen.queryByTestId("pedidos-para-juntar-mais")).not.toBeInTheDocument();
  });

  it("um pedido de 1 ficheiro cumprido nunca convida", async () => {
    documentos = {
      ...documentos,
      received: [pedido({ id: "cc", label: "CC", category_label: "CC", suggested_count: 1, expected_count: 1, status: "RECEIVED", attached_files: [ficheiro(1)], uploaded_count: 1 })],
    };
    await montar();
    await screen.findByText(/Documentos Recebidos \(1\)/);
    expect(screen.queryByTestId("pedidos-para-juntar-mais")).not.toBeInTheDocument();
  });
});
