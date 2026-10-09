/**
 * O Portal BLOQUEADO por processo inativo — a página montada a sério.
 *
 * O servidor responde 403 `{detail: {codigo: "portal_inativo", mensagem}}`.
 * O ecrã decide pelo CÓDIGO: um 403 de outra causa (token de staff, por
 * exemplo) NÃO pode mostrar «acesso suspenso», e um 401 continua a ser o
 * login. Os valores do fixture diferem do texto canónico para provar que se
 * mostra a mensagem do SERVIDOR e não a de recurso.
 */
import { render, screen, waitFor } from "@testing-library/react";
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
  constructor() {
    this.readyState = WebSocketFalso.OPEN;
  }
  send() {}
  close() {
    this.readyState = WebSocketFalso.CLOSED;
  }
}

const resposta = (status, corpo) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => corpo,
  clone: () => resposta(status, corpo),
  headers: { get: () => "application/json" },
});

const MENSAGEM_DO_SERVIDOR = "Processo 42 concluído a 01/10: acesso encerrado.";

vi.setConfig({ testTimeout: 20000 });

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  localStorage.setItem("portalToken", "token-do-cliente");
  vi.stubGlobal("WebSocket", WebSocketFalso);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function montarPortalCom(statusHttp, corpo) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url) => {
      if (String(url).includes("/portal/status")) return resposta(statusHttp, corpo);
      return resposta(200, {});
    }),
  );
  const { default: ClientPortal } = await import("../ClientPortal");
  render(<ClientPortal />);
}

describe("Portal — processo inativo", () => {
  it("mostra o aviso com a mensagem do SERVIDOR, em vez do login", async () => {
    await montarPortalCom(403, {
      detail: { codigo: "portal_inativo", mensagem: MENSAGEM_DO_SERVIDOR },
    });
    const aviso = await screen.findByTestId("portal-inativo");
    expect(aviso).toHaveTextContent(MENSAGEM_DO_SERVIDOR);
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/código/i)).not.toBeInTheDocument();
  });

  it("esquece a sessão: recarregar não reabre o Portal com o mesmo token", async () => {
    await montarPortalCom(403, {
      detail: { codigo: "portal_inativo", mensagem: MENSAGEM_DO_SERVIDOR },
    });
    await screen.findByTestId("portal-inativo");
    await waitFor(() => expect(localStorage.getItem("portalToken")).toBeNull());
    expect(localStorage.getItem("portal_token")).toBeNull();
  });

  it("um 403 de OUTRA causa não é «acesso suspenso»", async () => {
    await montarPortalCom(403, {
      detail: "Este token não tem permissão para aceder ao portal.",
    });
    // O ecrã já decidiu (esquece o token) — só então a ausência do aviso
    // prova alguma coisa; antes disso passava com a página ainda a carregar.
    await waitFor(() => expect(localStorage.getItem("portalToken")).toBeNull());
    expect(screen.queryByTestId("portal-inativo")).not.toBeInTheDocument();
  });

  it("um 401 continua a levar ao login", async () => {
    await montarPortalCom(401, { detail: "Link de acesso inválido." });
    await waitFor(() => {
      expect(localStorage.getItem("portalToken")).toBeNull();
    });
    expect(screen.queryByTestId("portal-inativo")).not.toBeInTheDocument();
  });
});
