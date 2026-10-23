/**
 * O Hub do Portal — a página montada a sério (D-42).
 *
 * Um cliente com dois processos activos (Power e Domus) vê primeiro a lista, escolhe, e o Portal
 * passa a ser DESSE processo: o token de sessão é o do processo e nada do outro atravessa
 * (a conversa, os eventos, as visitas). Trocar de processo não termina a sessão.
 *
 * A forma das respostas é a REAL dos serviços (`portal_hub`, `portal_status`); o mock de
 * `/portal/messages` responde conforme o token do pedido — se o Portal usasse o token errado, a
 * conversa errada aparecia no ecrã.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { guardarHub, lerHub } from "../../utils/portalHub";

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

const POWER = { id: "p-power", numero: 11, tipo_rotulo: "Crédito Habitação", empresa: "Power Real Estate", estado_rotulo: "Fase Bancária" };
const DOMUS = { id: "p-domus", numero: 22, tipo_rotulo: "Crédito Pessoal", empresa: "Domus", estado_rotulo: "Clientes em Espera" };

const TOKENS = { "TOKEN-DA-POWER": "p-power", "TOKEN-DA-DOMUS": "p-domus" };
const CONVERSA = {
  "p-power": [{ id: "m1", sender_type: "team", sender_name: "Equipa", content: "Mensagem da conversa da POWER", created_at: "2026-10-01T10:00:00Z" }],
  "p-domus": [{ id: "m2", sender_type: "team", sender_name: "Equipa", content: "Mensagem da conversa da DOMUS", created_at: "2026-10-02T10:00:00Z" }],
};

let chamadas;

function resposta(status, corpo) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => corpo,
    clone: () => resposta(status, corpo),
    headers: { get: () => "application/json" },
  };
}

const tokenDoPedido = (opcoes) => String(opcoes?.headers?.Authorization || "").replace("Bearer ", "");

beforeEach(() => {
  localStorage.clear();
  chamadas = [];
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
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url, opcoes = {}) => {
      const u = String(url).replace("http://localhost:8001", "");
      chamadas.push({ u, metodo: opcoes.method || "GET", token: tokenDoPedido(opcoes), corpo: opcoes.body });
      if (u === "/portal/hub/select") {
        const alvo = JSON.parse(opcoes.body).process_id;
        return resposta(200, {
          token: alvo === "p-power" ? "TOKEN-DA-POWER" : "TOKEN-DA-DOMUS",
          process_id: alvo,
          token_type: "access_code_session",
        });
      }
      const processo = TOKENS[tokenDoPedido(opcoes)];
      if (u.startsWith("/portal/messages/unread")) return resposta(200, { count: 0 });
      if (u.startsWith("/portal/messages")) return resposta(200, { messages: CONVERSA[processo] || [] });
      if (u.startsWith("/portal/status")) {
        return resposta(200, {
          process: { id: processo, client_name: "Ana Silva", status: "analise", status_label: "Em análise", status_color: "#0ea5e9", process_type: "credito_habitacao" },
          progress: { percent: 40, current_step: 2, total_steps: 5 },
          stepper: [],
          documents: { requested: [], uploaded: [], received: [], has_pending: false },
          rgpd: { status: "none", has_rgpd: false },
          team: { consultores: [], mediadores: [] },
          consultor: null,
          welcome_message: `Bem-vinda ao processo ${processo}`,
          has_process: true,
          client_id: "cli-1",
        });
      }
      if (u.startsWith("/portal/events")) return resposta(200, { events: [] });
      if (u.startsWith("/portal/recommendations")) return resposta(200, { recommendations: [] });
      if (u.startsWith("/portal/visits")) return resposta(200, { visits: [] });
      return resposta(200, {});
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function montar() {
  const { default: ClientPortal } = await import("../ClientPortal");
  return render(<ClientPortal />);
}

/** O que o login deixa guardado quando o cliente tem DOIS processos activos. */
function sessaoDeUmClienteComDoisProcessos({ escolhido = "" } = {}) {
  localStorage.setItem("portalToken", "TOKEN-DE-OMISSAO");
  localStorage.setItem("portalAuthMethod", "access_code");
  localStorage.setItem("portalLastActivity", String(Date.now()));
  guardarHub({ hub_token: "HUB-TOKEN", processos: [POWER, DOMUS] }, { escolhido });
}

describe("o Hub antes de entrar num processo", () => {
  it("com dois processos activos mostra a lista em vez de entrar num à sorte", async () => {
    sessaoDeUmClienteComDoisProcessos();
    await montar();
    expect(await screen.findByTestId("portal-hub")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Crédito Habitação · Power Real Estate" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Crédito Pessoal · Domus" })).toBeInTheDocument();
    expect(chamadas.filter((c) => c.u.startsWith("/portal/status"))).toEqual([]);
    expect(chamadas.filter((c) => c.u.startsWith("/portal/messages"))).toEqual([]);
  });

  it("escolher abre o Portal DESSE processo, com o token desse processo", async () => {
    sessaoDeUmClienteComDoisProcessos();
    await montar();
    await userEvent.click(await screen.findByRole("button", { name: /Domus/ }));

    expect(await screen.findByText(/Bem-vinda ao processo p-domus/)).toBeInTheDocument();
    expect(screen.queryByTestId("portal-hub")).not.toBeInTheDocument();

    const escolha = chamadas.find((c) => c.u === "/portal/hub/select");
    expect(escolha.token).toBe("HUB-TOKEN");
    expect(JSON.parse(escolha.corpo)).toEqual({ process_id: "p-domus" });
    const leituras = chamadas.filter((c) => c.u.startsWith("/portal/status"));
    expect(leituras.length).toBeGreaterThan(0);
    expect(leituras.every((c) => c.token === "TOKEN-DA-DOMUS")).toBe(true);
  });

  it("a conversa que se vê é a do processo escolhido", async () => {
    sessaoDeUmClienteComDoisProcessos();
    await montar();
    await userEvent.click(await screen.findByRole("button", { name: /Power/ }));
    expect(await screen.findByText("Mensagem da conversa da POWER")).toBeInTheDocument();
    expect(screen.queryByText("Mensagem da conversa da DOMUS")).not.toBeInTheDocument();
  });
});

describe("trocar de processo", () => {
  it("o botão só existe com Hub e leva de volta à lista sem terminar a sessão", async () => {
    sessaoDeUmClienteComDoisProcessos({ escolhido: "p-power" });
    localStorage.setItem("portalToken", "TOKEN-DA-POWER");
    await montar();
    await screen.findByText(/Bem-vinda ao processo p-power/);

    await userEvent.click(await screen.findByTestId("portal-trocar-de-processo"));
    expect(await screen.findByTestId("portal-hub")).toBeInTheDocument();
    expect(localStorage.getItem("portalToken")).toBe("TOKEN-DA-POWER");
    expect(lerHub().token).toBe("HUB-TOKEN");
  });

  it("nada do processo anterior atravessa: a conversa é a do novo", async () => {
    sessaoDeUmClienteComDoisProcessos({ escolhido: "p-power" });
    localStorage.setItem("portalToken", "TOKEN-DA-POWER");
    await montar();
    expect(await screen.findByText("Mensagem da conversa da POWER")).toBeInTheDocument();

    await userEvent.click(await screen.findByTestId("portal-trocar-de-processo"));
    await userEvent.click(await screen.findByRole("button", { name: /Domus/ }));

    expect(await screen.findByText("Mensagem da conversa da DOMUS")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Mensagem da conversa da POWER")).not.toBeInTheDocument());
    // e os pedidos seguintes já vão com o token do novo processo
    const ultimaLeitura = [...chamadas].reverse().find((c) => c.u.startsWith("/portal/messages") && !c.u.includes("unread"));
    expect(ultimaLeitura.token).toBe("TOKEN-DA-DOMUS");
  });
});

describe("sem Hub tudo fica como estava", () => {
  it("um cliente com um só processo entra directamente e não vê «Trocar de processo»", async () => {
    localStorage.setItem("portalToken", "TOKEN-DA-POWER");
    localStorage.setItem("portalAuthMethod", "access_code");
    localStorage.setItem("portalLastActivity", String(Date.now()));
    await montar();
    expect(await screen.findByText(/Bem-vinda ao processo p-power/)).toBeInTheDocument();
    expect(screen.queryByTestId("portal-hub")).not.toBeInTheDocument();
    expect(screen.queryByTestId("portal-trocar-de-processo")).not.toBeInTheDocument();
  });

  it("um link que levava a um processo entra nele e deixa trocar", async () => {
    sessaoDeUmClienteComDoisProcessos({ escolhido: "p-domus" });
    localStorage.setItem("portalToken", "TOKEN-DA-DOMUS");
    await montar();
    expect(await screen.findByText(/Bem-vinda ao processo p-domus/)).toBeInTheDocument();
    expect(screen.queryByTestId("portal-hub")).not.toBeInTheDocument();
    expect(screen.getByTestId("portal-trocar-de-processo")).toBeInTheDocument();
  });
});

describe("terminar a sessão no Hub", () => {
  it("«Sair» leva ao login e esquece a credencial do Hub", async () => {
    sessaoDeUmClienteComDoisProcessos();
    await montar();
    await userEvent.click(await screen.findByRole("button", { name: /sair/i }));
    await waitFor(() => expect(screen.queryByTestId("portal-hub")).not.toBeInTheDocument());
    expect(localStorage.getItem("portalToken")).toBeNull();
    expect(lerHub().token).toBe("");
  });
});
