/**
 * «O Meu Perfil» do Portal — a página montada a SÉRIO (Out 2026).
 *
 * O perfil passa a espelhar TODO o formulário de registo: dados pessoais, segundo titular,
 * imóvel pretendido e situação financeira (o NIF só para ver, mascarado). A regra do
 * `SystemConfigPage.seccoes.test.jsx` aplica-se: acrescentar cartões a uma página exige montar
 * a PÁGINA — o teste do componente de campos passava com os cartões por desenhar.
 *
 * A forma de `GET /portal/me` é a que `portal_profile.run_get_client_profile` devolve
 * (verificada em `test_perfil_do_portal_seccoes.py::TestOGetDevolveAsSeccoes`), com valores
 * DIFERENTES das omissões: um erro de leitura não pode passar por uma leitura correcta.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
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

class WebSocketFalso {
  static OPEN = 1;
  static CLOSED = 3;
  constructor() {
    this.readyState = WebSocketFalso.CLOSED;
  }
  send() {}
  close() {}
}

vi.setConfig({ testTimeout: 20000 });

const resposta = (corpo, status = 200) => ({
  ok: status < 400,
  status,
  json: async () => corpo,
  clone: () => resposta(corpo, status),
  headers: { get: () => "application/json" },
});

const STATUS = {
  process: {
    id: "proc-1", client_name: "Ana Silva", status: "analise", status_label: "Em análise",
    status_color: "#0ea5e9", process_type: "credito_habitacao",
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
};

const campo = (field_key, label, destino, section, extra = {}) => ({
  field_key, label, destino, section, field_type: "text", is_required: false,
  is_primary: true, options: [], hint: "", read_only: false, ...extra,
});

const PERFIL = {
  id: "cli-1",
  nome: "Ana Silva",
  contacto: { email: "ana@exemplo.pt" },
  dados_pessoais: { estado_civil: "casado", morada_fiscal: "Rua das Flores 7" },
  titular2_data: { naturalidade: "Braga" },
  real_estate_data: { localizacao: "Cascais", caracteristicas: ["Garagem"] },
  financial_data: { salario_liquido: 2345 },
  somente_leitura: {
    nif: "••••••789", titular2_nif: "••••••777", titular2_name: "Rui Pereira",
    bancos_creditos: "BPI (9000 €)",
  },
  tem_segundo_titular: true,
  secoes: [
    { id: "titular", titulo: "Dados Pessoais" },
    { id: "segundo_titular", titulo: "Segundo Titular" },
    { id: "imovel", titulo: "Imóvel Pretendido" },
    { id: "financeiro", titulo: "Situação Financeira" },
  ],
  form_schema: [
    campo("email", "Email", ["contacto", "email"], "titular", { field_type: "email", is_required: true }),
    campo("nif", "NIF", ["dados_pessoais", "nif"], "titular", { read_only: true }),
    campo("morada_fiscal", "Morada Fiscal", ["dados_pessoais", "morada_fiscal"], "titular"),
    campo("estado_civil", "Estado Civil", ["dados_pessoais", "estado_civil"], "titular", {
      field_type: "select", options: [{ value: "casado", label: "Casado(a)" }, { value: "solteiro", label: "Solteiro(a)" }],
    }),
    campo("titular2_name", "Nome do 2º Titular", ["titular2_data", "name"], "segundo_titular", { read_only: true }),
    campo("titular2_nif", "NIF (2º Titular)", ["titular2_data", "nif"], "segundo_titular", { read_only: true }),
    campo("titular2_naturalidade", "Naturalidade (2º Titular)", ["titular2_data", "naturalidade"], "segundo_titular"),
    campo("localizacao", "Localização", ["real_estate_data", "localizacao"], "imovel"),
    campo("caracteristicas", "Características", ["real_estate_data", "caracteristicas"], "imovel", {
      field_type: "checkbox", options: ["Garagem", "Elevador"],
    }),
    campo("salario_liquido", "Salário líquido", ["financial_data", "salario_liquido"], "financeiro", { field_type: "number" }),
    campo("bancos_creditos", "Créditos em curso", ["financial_data", "bancos_creditos"], "financeiro", {
      read_only: true, field_type: "checkbox",
    }),
  ],
  has_process: false,
  is_data_confirmed: false,
};

let perfil;
let pedidos;

beforeEach(() => {
  pedidos = [];
  perfil = JSON.parse(JSON.stringify(PERFIL));
  localStorage.clear();
  localStorage.setItem("portalToken", "magic-token-do-cliente");
  vi.stubGlobal("WebSocket", WebSocketFalso);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url, opcoes = {}) => {
      const u = String(url);
      const metodo = (opcoes.method || "GET").toUpperCase();
      if (u.includes("/portal/me")) {
        pedidos.push({ metodo, corpo: opcoes.body ? JSON.parse(opcoes.body) : null });
        if (metodo === "PUT") return resposta({ success: true, message: "Perfil atualizado com sucesso.", rejected_fields: [] });
        return resposta(perfil);
      }
      if (u.includes("/portal/messages/unread")) return resposta({ count: 0 });
      if (u.includes("/portal/messages")) return resposta({ messages: [] });
      if (u.includes("/portal/status")) return resposta(STATUS);
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

async function abrirOPerfil() {
  const { default: ClientPortal } = await import("../ClientPortal");
  render(<ClientPortal />);
  await userEvent.click(await screen.findByRole("button", { name: /o meu perfil/i }));
  await screen.findByTestId("perfil-seccao-titular");
}

describe("Portal — «O Meu Perfil» espelha o registo", () => {
  it("desenha um cartão por secção, pela ordem do registo", async () => {
    await abrirOPerfil();
    for (const [id, titulo] of [
      ["titular", "Dados Pessoais"], ["segundo_titular", "Segundo Titular"],
      ["imovel", "Imóvel Pretendido"], ["financeiro", "Situação Financeira"],
    ]) {
      expect(within(screen.getByTestId(`perfil-seccao-${id}`)).getByText(titulo)).toBeInTheDocument();
    }
  });

  it("mostra os valores de cada secção (diferentes das omissões)", async () => {
    await abrirOPerfil();
    expect(screen.getByLabelText(/^Morada Fiscal/)).toHaveValue("Rua das Flores 7");
    expect(screen.getByLabelText(/^Naturalidade \(2º Titular\)/)).toHaveValue("Braga");
    expect(screen.getByLabelText(/^Localização/)).toHaveValue("Cascais");
    expect(screen.getByLabelText(/^Salário líquido/)).toHaveValue(2345);
    expect(screen.getByLabelText("Garagem")).toBeChecked();
    expect(screen.getByLabelText("Elevador")).not.toBeChecked();
  });

  it("o NIF aparece mascarado e desactivado — nunca em claro", async () => {
    await abrirOPerfil();
    const nif = screen.getByLabelText(/^NIF$/);
    expect(nif).toHaveValue("••••••789");
    expect(nif).toBeDisabled();
    expect(screen.getByLabelText(/^NIF \(2º Titular\)/)).toHaveValue("••••••777");
    expect(screen.getByLabelText(/^Créditos em curso/)).toHaveValue("BPI (9000 €)");
  });

  it("sem segundo titular o cartão não existe", async () => {
    perfil.tem_segundo_titular = false;
    perfil.secoes = perfil.secoes.filter((s) => s.id !== "segundo_titular");
    perfil.form_schema = perfil.form_schema.filter((c) => c.section !== "segundo_titular");
    await abrirOPerfil();
    expect(screen.queryByTestId("perfil-seccao-segundo_titular")).not.toBeInTheDocument();
  });

  it("guardar sem tocar nas secções NÃO as reenvia (não pisa o que a equipa corrigiu)", async () => {
    await abrirOPerfil();
    await userEvent.click(screen.getByRole("button", { name: /guardar alterações/i }));
    await waitFor(() => expect(pedidos.some((p) => p.metodo === "PUT")).toBe(true));
    const put = pedidos.find((p) => p.metodo === "PUT").corpo;
    expect(put.titular2_data).toBeUndefined();
    expect(put.real_estate_data).toBeUndefined();
    expect(put.financial_data).toBeUndefined();
    // Os dados pessoais continuam a ir inteiros, como sempre.
    expect(put.dados_pessoais.estado_civil).toBe("casado");
  });

  it("alterar o salário e uma caixa envia SÓ esses campos, nos grupos certos", async () => {
    await abrirOPerfil();
    const salario = screen.getByLabelText(/^Salário líquido/);
    await userEvent.clear(salario);
    await userEvent.type(salario, "2800");
    await userEvent.click(screen.getByLabelText("Elevador"));
    await userEvent.click(screen.getByRole("button", { name: /guardar alterações/i }));

    await waitFor(() => expect(pedidos.some((p) => p.metodo === "PUT")).toBe(true));
    const put = pedidos.find((p) => p.metodo === "PUT").corpo;
    expect(put.financial_data).toEqual({ salario_liquido: "2800" });
    expect(put.real_estate_data).toEqual({ caracteristicas: ["Garagem", "Elevador"] });
    expect(put.titular2_data).toBeUndefined();
  });

  it("nunca envia o que é só de leitura", async () => {
    await abrirOPerfil();
    await userEvent.type(screen.getByLabelText(/^Morada Fiscal/), " 2");
    await userEvent.click(screen.getByRole("button", { name: /guardar alterações/i }));
    await waitFor(() => expect(pedidos.some((p) => p.metodo === "PUT")).toBe(true));
    const bruto = JSON.stringify(pedidos.find((p) => p.metodo === "PUT").corpo);
    expect(bruto).not.toContain("789");
    expect(bruto).not.toContain("BPI");
    expect(bruto).not.toContain("Rui Pereira");
    // Nem sequer a CHAVE: um `nif: null` seria um pedido para o apagar.
    const put = pedidos.find((p) => p.metodo === "PUT").corpo;
    expect("nif" in put.dados_pessoais).toBe(false);
    expect(JSON.stringify(put)).not.toContain("bancos_creditos");
    expect(JSON.stringify(put)).not.toContain("titular2_nif");
  });

  it("perfil trancado desactiva os campos das secções e esconde o guardar", async () => {
    perfil.has_process = true;
    await abrirOPerfil();
    expect(screen.getByLabelText(/^Salário líquido/)).toBeDisabled();
    expect(screen.getByLabelText("Garagem")).toBeDisabled();
    expect(screen.queryByRole("button", { name: /guardar alterações/i })).not.toBeInTheDocument();
  });

  it("um servidor anterior (sem secções nem `section`) continua a mostrar os dados pessoais", async () => {
    delete perfil.secoes;
    perfil.form_schema = perfil.form_schema
      .filter((c) => c.section === "titular" && !c.read_only)
      .map(({ section, read_only, ...resto }) => resto);
    await abrirOPerfil();
    expect(screen.getByLabelText(/^Morada Fiscal/)).toHaveValue("Rua das Flores 7");
  });
});
