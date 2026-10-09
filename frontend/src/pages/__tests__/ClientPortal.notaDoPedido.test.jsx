/**
 * A nota de um pedido chega ao cliente — a página montada a sério.
 *
 * Os valores do fixture diferem do texto de recurso; a nota é multi-linha e
 * comprida para provar que não é cortada.
 */
import { render, screen } from "@testing-library/react";
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

class WebSocketFalso {
  static OPEN = 1;
  static CLOSED = 3;
  constructor() { this.readyState = 1; }
  send() {}
  close() {}
}

const ok = (corpo) => ({
  ok: true, status: 200, json: async () => corpo,
  clone: () => ok(corpo), headers: { get: () => "application/json" },
});

const NOTA = "Tem de estar legalizada.\nValidade máxima de 3 meses e todas as páginas.";

vi.setConfig({ testTimeout: 20000 });

beforeEach(() => {
  localStorage.clear();
  localStorage.setItem("portalToken", "token");
  vi.stubGlobal("WebSocket", WebSocketFalso);
  vi.stubGlobal("fetch", vi.fn(async (url) => {
    const u = String(url);
    if (u.includes("/portal/messages/unread")) return ok({ count: 0 });
    if (u.includes("/portal/messages")) return ok({ messages: [] });
    if (u.includes("/portal/status")) {
      return ok({
        process: { id: "p", client_name: "Ana", status: "x", status_label: "Em análise",
          status_color: "#0ea5e9", process_type: "credito_habitacao" },
        progress: { percent: 10, current_step: 1, total_steps: 5 },
        stepper: [],
        documents: {
          requested: [{ id: "r1", label: "Certidão de Casamento", icon: "📎", category: "Outros",
            status: "REQUESTED", notes: NOTA, attached_files: [] }],
          uploaded: [],
          received: [{ id: "x1", filename: "irs.pdf", category_label: "Certidão de Nascimento",
            icon: "📄", notes: "Recebida e validada.", attached_files: [], received_at: "2026-10-01" }],
          has_pending: true,
        },
        rgpd: { status: "none", has_rgpd: false },
        team: { consultores: [], mediadores: [] },
        consultor: null, welcome_message: "Olá", has_process: true, client_id: "c",
      });
    }
    return ok({});
  }));
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Portal — a nota do pedido", () => {
  it("o pedido mostra o nome específico e a nota INTEIRA, com as quebras de linha", async () => {
    const { default: ClientPortal } = await import("../ClientPortal");
    render(<ClientPortal />);
    await screen.findByText("Certidão de Casamento");
    const notas = await screen.findAllByTestId("nota-do-pedido");
    const doPedido = notas.find((n) => n.textContent.includes("legalizada"));
    expect(doPedido).toBeTruthy();
    expect(doPedido.textContent).toBe(NOTA);
    expect(doPedido.className).not.toMatch(/truncate/);
  });

  it("depois de recebido, o documento continua a mostrar a nota", async () => {
    const { default: ClientPortal } = await import("../ClientPortal");
    render(<ClientPortal />);
    await screen.findByText("irs.pdf");
    expect(await screen.findByText("Recebida e validada.")).toBeInTheDocument();
  });
});
