/**
 * O contentor do Hub: o que cada resposta do servidor quer dizer.
 *
 * A forma das respostas é a REAL (`services/portal_hub.py`): `GET /portal/hub` →
 * `{cliente_nome, processos, entrada}`; `POST /portal/hub/select` → `{token, process_id, ...}`.
 * Os valores dos fixtures são diferentes dos textos de recurso do componente.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { EVENTO_DA_SESSAO_DO_PORTAL, guardarHub, lerHub } from "../../../utils/portalHub";
import PortalHubEcra from "../PortalHubEcra";

vi.mock("../../../utils/apiBaseUrl", () => ({
  API_BASE_URL: "http://localhost:8001",
  BACKEND_URL: "http://localhost:8001",
}));

const P1 = { id: "p-1", numero: 11, tipo_rotulo: "Crédito Habitação", empresa: "Power Real Estate", estado_rotulo: "Fase Bancária" };
const P2 = { id: "p-2", numero: 22, tipo_rotulo: "Crédito Pessoal", empresa: "Domus", estado_rotulo: "Clientes em Espera" };
const P3 = { id: "p-3", numero: 33, tipo_rotulo: "Seguros", empresa: "Power Real Estate", estado_rotulo: "Em curso" };

const resposta = (status, corpo) => ({ ok: status >= 200 && status < 300, status, json: async () => corpo });

let chamadas;
let rotas;

beforeEach(() => {
  localStorage.clear();
  chamadas = [];
  rotas = {};
  guardarHub({ hub_token: "HUB-TOKEN", processos: [P1, P2] });
  localStorage.setItem("portalToken", "token-do-processo-por-omissao");
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url, opcoes = {}) => {
      chamadas.push({ url: String(url), opcoes });
      const chave = `${opcoes.method || "GET"} ${String(url).replace("http://localhost:8001", "")}`;
      if (rotas[chave]) return rotas[chave](opcoes);
      return resposta(500, {});
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const montar = () => render(<PortalHubEcra hub={lerHub()} nome="Joana" />);

describe("escolher um processo", () => {
  it("pede ao servidor com o token do Hub e troca o token de sessão pelo do processo", async () => {
    rotas["POST /portal/hub/select"] = () => resposta(200, { token: "TOKEN-DE-P2", process_id: "p-2", token_type: "access_code_session" });
    const aviso = vi.fn();
    window.addEventListener(EVENTO_DA_SESSAO_DO_PORTAL, aviso);
    montar();
    await userEvent.click(screen.getByRole("button", { name: /Domus/ }));
    await waitFor(() => expect(localStorage.getItem("portalToken")).toBe("TOKEN-DE-P2"));
    window.removeEventListener(EVENTO_DA_SESSAO_DO_PORTAL, aviso);

    const pedido = chamadas.find((c) => c.url.endsWith("/portal/hub/select"));
    expect(pedido.opcoes.headers.Authorization).toBe("Bearer HUB-TOKEN");
    expect(JSON.parse(pedido.opcoes.body)).toEqual({ process_id: "p-2" });
    expect(localStorage.getItem("portalProcessId")).toBe("p-2");
    expect(lerHub().escolhido).toBe("p-2");
    expect(aviso).toHaveBeenCalled();
  });

  it("a mensagem do servidor de um processo suspenso é a que se mostra, e a lista refaz-se", async () => {
    rotas["POST /portal/hub/select"] = () => resposta(403, { detail: { codigo: "portal_inativo", mensagem: "Processo 22 suspenso desde 01/10." } });
    rotas["GET /portal/hub"] = () => resposta(200, { processos: [P1, P3] });
    montar();
    await userEvent.click(screen.getByRole("button", { name: /Domus/ }));
    expect(await screen.findByTestId("portal-hub-erro")).toHaveTextContent("Processo 22 suspenso desde 01/10.");
    await waitFor(() => expect(lerHub().processos.map((p) => p.id)).toEqual(["p-1", "p-3"]));
    expect(localStorage.getItem("portalToken")).toBe("token-do-processo-por-omissao");
  });

  it("um 404 diz que o processo já não está disponível", async () => {
    rotas["POST /portal/hub/select"] = () => resposta(404, { detail: "Processo não encontrado." });
    rotas["GET /portal/hub"] = () => resposta(200, { processos: [P1, P2] });
    montar();
    await userEvent.click(screen.getByRole("button", { name: /Power/ }));
    expect(await screen.findByTestId("portal-hub-erro")).toHaveTextContent("Este processo já não está disponível.");
  });

  it("um 429 pede para aguardar", async () => {
    rotas["POST /portal/hub/select"] = () => resposta(429, { detail: "rate limit" });
    montar();
    await userEvent.click(screen.getByRole("button", { name: /Power/ }));
    expect(await screen.findByTestId("portal-hub-erro")).toHaveTextContent(/Demasiados pedidos/);
  });

  it("uma sessão do Hub expirada (401) leva ao login: esquece a sessão toda", async () => {
    rotas["POST /portal/hub/select"] = () => resposta(401, { detail: "A sessão expirou." });
    montar();
    await userEvent.click(screen.getByRole("button", { name: /Power/ }));
    await waitFor(() => expect(localStorage.getItem("portalToken")).toBeNull());
    expect(lerHub().token).toBe("");
  });

  it("sem rede diz-se, e o cliente pode tentar de novo", async () => {
    rotas["POST /portal/hub/select"] = () => {
      throw new TypeError("Failed to fetch");
    };
    montar();
    await userEvent.click(screen.getByRole("button", { name: /Power/ }));
    expect(await screen.findByTestId("portal-hub-erro")).toHaveTextContent(/Sem ligação ao servidor/);
    expect(screen.getByRole("button", { name: /Power/ })).toBeEnabled();
  });

  it("um duplo clique envia UM pedido", async () => {
    let resolver;
    rotas["POST /portal/hub/select"] = () => new Promise((r) => { resolver = () => r(resposta(200, { token: "T", process_id: "p-1" })); });
    montar();
    const botao = screen.getByRole("button", { name: /Power/ });
    await userEvent.click(botao);
    await userEvent.click(botao);
    expect(chamadas.filter((c) => c.url.endsWith("/portal/hub/select"))).toHaveLength(1);
    resolver();
    await waitFor(() => expect(localStorage.getItem("portalToken")).toBe("T"));
  });
});

describe("quando a lista muda debaixo dos pés do cliente", () => {
  it("se sobra UM processo entra-se nele: não há o que escolher", async () => {
    rotas["POST /portal/hub/select"] = (opcoes) => {
      const alvo = JSON.parse(opcoes.body).process_id;
      return alvo === "p-2"
        ? resposta(404, { detail: "Processo não encontrado." })
        : resposta(200, { token: "TOKEN-DE-P1", process_id: "p-1" });
    };
    rotas["GET /portal/hub"] = () => resposta(200, { processos: [P1] });
    montar();
    await userEvent.click(screen.getByRole("button", { name: /Domus/ }));
    await waitFor(() => expect(localStorage.getItem("portalToken")).toBe("TOKEN-DE-P1"));
    expect(lerHub().escolhido).toBe("p-1");
  });

  it("se não sobra nenhum, a sessão acaba", async () => {
    rotas["POST /portal/hub/select"] = () => resposta(404, { detail: "Processo não encontrado." });
    rotas["GET /portal/hub"] = () => resposta(200, { processos: [] });
    montar();
    await userEvent.click(screen.getByRole("button", { name: /Domus/ }));
    await waitFor(() => expect(localStorage.getItem("portalToken")).toBeNull());
  });

  it("se a lista vem com 'processos' que não é um array, a sessão acaba em vez de rebentar", async () => {
    rotas["POST /portal/hub/select"] = () => resposta(404, { detail: "x" });
    rotas["GET /portal/hub"] = () => resposta(200, { processos: { 0: P1, 1: P2 } });
    montar();
    await userEvent.click(screen.getByRole("button", { name: /Domus/ }));
    await waitFor(() => expect(localStorage.getItem("portalToken")).toBeNull());
  });
});

describe("sair", () => {
  it("esquece a sessão e o Hub", async () => {
    montar();
    await userEvent.click(screen.getByRole("button", { name: /sair/i }));
    expect(localStorage.getItem("portalToken")).toBeNull();
    expect(lerHub().token).toBe("");
  });
});
