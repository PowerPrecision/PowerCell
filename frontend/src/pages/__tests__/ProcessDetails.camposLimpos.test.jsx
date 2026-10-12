/**
 * Apagar QUALQUER campo opcional nos «Dados do Processo» tem de persistir (QA, Out 2026).
 *
 * A correcção do email/telefone deixou o resto de fora: apagar o NIF (ou a
 * morada, o rendimento…) e guardar dava o toast de sucesso e o valor antigo
 * voltava — os limpadores descartavam os vazios e o servidor nunca recebia o
 * pedido. Aqui monta-se a PÁGINA real e afirma-se o que SAI para o servidor.
 *
 * A regra: só se envia vazio para o que tinha valor ao carregar e o utilizador
 * apagou; o que já nasceu vazio continua omitido, e o 0 é um valor.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation, useNavigate, useNavigationType } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import servicoPorPagar from "@/test/fixtures/parceiro/servico_por_pagar.json";

// ── Fronteiras falsas ────────────────────────────────────────────────
vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));

// O perfil da sessão muda por teste (a origem financeira só aparece à gestão).
const sessao = vi.hoisted(() => ({ papel: "consultor" }));

// Parcial: só a origem financeira é falseada; o resto do `api` é o real.
vi.mock("../../services/api", async (importOriginal) => ({
  ...(await importOriginal()),
  getOrigemFinanceira: vi.fn(() => Promise.resolve({ data: {
    process_id: "proc-1", definida: false, tipo: null, rotulo: null,
    angariador: null, definido_por: null, definido_em: null,
  } })),
  getCandidatosOrigemFinanceira: vi.fn(() => Promise.resolve({ data: { candidatos: [] } })),
  // Forma REAL do servidor (fixture gerada pelo serviço), não uma inventada.
  getServicoDoParceiro: vi.fn(() => Promise.resolve({ data: servicoPorPagar })),
  reopenProcess: vi.fn(() => Promise.resolve({ data: { reopened: true } })),
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    token: "t-1",
    user: {
      id: "u-1",
      name: "Carla Consultora",
      email: "carla@precisioncredito.pt",
      role: sessao.papel,
    },
    effectiveRole: sessao.papel,
    activeCompanyId: "c-1",
    effectiveCompanyId: "c-1",
    permissions: {},
  }),
}));

vi.mock("../../hooks/useWebSocket", () => ({
  default: () => ({
    isConnected: false,
    on: () => () => {},
    joinProcessRoom: vi.fn(),
    leaveProcessRoom: vi.fn(),
  }),
}));

vi.mock("../../hooks/useTaskEvents", () => ({
  default: () => ({ isConnected: false }),
  useTaskEvents: () => ({ isConnected: false }),
}));

vi.mock("../../hooks/useProcessPortalMessages", () => ({
  useProcessPortalMessages: () => ({
    messages: [],
    loading: false,
    sending: false,
    newMessage: "",
    setNewMessage: vi.fn(),
    sendMessage: vi.fn(),
    fetchMessages: vi.fn(),
    refresh: vi.fn(),
    unreadCount: 0,
  }),
}));

const pacote = vi.hoisted(() => ({ valor: null }));

vi.mock("../../hooks/queries/useProcessQuery", async (original) => {
  const real = await original();
  return { ...real, useProcessFullData: () => pacote.valor };
});

// Espiões ESTÁVEIS (o mock da página cria objectos novos em cada render e não
// deixava afirmar o que foi enviado). `mutateAsync` é o que o `executeSave` chama.
const gravar = vi.hoisted(() => ({
  updateProcess: vi.fn(() => Promise.resolve({})),
  updateClient: vi.fn(() => Promise.resolve({})),
}));

const mutacaoFalsa = () => ({ mutateAsync: vi.fn(() => Promise.resolve({})), isPending: false });

vi.mock("../../hooks/mutations/useProcessMutations", () => ({
  useProcessMutations: () => ({
    moveProcess: mutacaoFalsa(),
    updateProcess: { mutateAsync: gravar.updateProcess, isPending: false },
    updateClient: { mutateAsync: gravar.updateClient, isPending: false },
    assignProcess: mutacaoFalsa(),
    deleteActivity: mutacaoFalsa(),
    deadlines: {
      create: mutacaoFalsa(),
      update: mutacaoFalsa(),
      remove: mutacaoFalsa(),
    },
  }),
}));

import ProcessDetails from "../ProcessDetails";
import { construirContextoDeNavegacao } from "../../utils/processNavigation";

// ── Dados ────────────────────────────────────────────────────────────
const PROCESSO = {
  id: "proc-1",
  process_number: 12,
  client_id: "cli-1",
  client_name: "Ana Martins",
  client_email: "ana@exemplo.pt",
  client_phone: "912345678",
  status: "Em Análise",
  personal_data: { nome: "Ana Martins", nif: "123456789", email: "ana@exemplo.pt", telefone: "912345678" },
  // Valores AFASTADOS das omissões; `salario_liquido` é o nome alternativo que o
  // ecrã usava como recurso do rendimento mensal.
  financial_data: {
    monthly_income: 2100, salario_liquido: 1900, nr_dependentes: 2, renda_habitacao_atual: 450,
  },
  real_estate_data: {},
  credit_data: {},
  titular2_data: {
    name: "Rui Costa", nif: "987654321", naturalidade: "Braga",
    portal_financas_utilizador: "rui.fin", seg_social_utilizador: "rui.ss",
  },
  activities: [],
  labels: [],
  consultor_names: ["Carla Consultora"],
  assigned_consultor_ids: ["u-1"],
};

const CLIENTE = {
  id: "cli-1",
  nome: "Ana Martins",
  contacto: { email: "ana@exemplo.pt", telefone: "912345678" },
  dados_pessoais: {
    nif: "123456789", morada_fiscal: "Rua das Flores 1", address: "Rua das Flores 1",
    naturalidade: "Porto", codigo_postal: "4000-001",
  },
};

function montar() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/processo/proc-1"]}>
        <Routes>
          <Route path="/processo/:id" element={<ProcessDetails />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  gravar.updateProcess.mockClear();
  gravar.updateClient.mockClear();
  pacote.valor = {
    process: PROCESSO,
    client: CLIENTE,
    history: [],
    activities: [],
    deadlines: [],
    workflowStatuses: [{ id: "s1", name: "Em Análise", order: 1 }],
    isLoading: false,
    isError: false,
    error: null,
    refetchAll: vi.fn(() => Promise.resolve()),
    processQuery: { isLoading: false, isFetching: false, dataUpdatedAt: Date.now() },
    clientQuery: { isLoading: false, isFetching: false },
  };
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) }),
  );
  URL.createObjectURL = vi.fn(() => "blob:x");
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
});

/** Abre um separador e põe em edição o cartão que contém o campo com este valor. */
async function editarCartaoDe(utilizador, separador, valorAtual) {
  await screen.findByTestId("layout");
  await utilizador.click(screen.getAllByRole("tab", { name: separador })[0]);
  const campo = await screen.findByDisplayValue(valorAtual);
  const cartao = campo.closest(".read-only-card") || campo.closest("div.border-l-4");
  await utilizador.click(within(cartao).getByTitle("Editar"));
  return screen.findByDisplayValue(valorAtual);
}

async function guardar(utilizador) {
  await utilizador.click(screen.getByRole("button", { name: "Guardar" }));
  await waitFor(() => expect(gravar.updateProcess).toHaveBeenCalledTimes(1));
  return {
    processo: gravar.updateProcess.mock.calls[0][0],
    cliente: gravar.updateClient.mock.calls[0]?.[0],
  };
}

describe("ProcessDetails — apagar o NIF persiste (QA)", () => {
  it("apagar o NIF e guardar envia o NIF VAZIO ao processo e ao cliente", async () => {
    const utilizador = userEvent.setup();
    montar();
    const campo = await editarCartaoDe(utilizador, /Pessoais|Cliente/i, "123456789");

    await utilizador.clear(campo);
    const { processo, cliente } = await guardar(utilizador);

    expect(processo.personal_data.nif).toBe("");
    expect(cliente.data.dados_pessoais.nif).toBe("");
  });

  it("o resto dos campos pessoais continua a ir com o valor que tinha", async () => {
    const utilizador = userEvent.setup();
    montar();
    const campo = await editarCartaoDe(utilizador, /Pessoais|Cliente/i, "123456789");

    await utilizador.clear(campo);
    const { processo, cliente } = await guardar(utilizador);

    expect(processo.personal_data.morada_fiscal).toBe("Rua das Flores 1");
    expect(cliente.data.dados_pessoais.naturalidade).toBe("Porto");
  });

  it("guardar sem tocar no NIF não manda apagar nada", async () => {
    const utilizador = userEvent.setup();
    montar();
    await editarCartaoDe(utilizador, /Pessoais|Cliente/i, "123456789");

    const { processo, cliente } = await guardar(utilizador);

    expect(processo.personal_data.nif).toBe("123456789");
    const enviados = Object.entries(cliente.data.dados_pessoais).filter(([, v]) => v === "");
    expect(enviados).toEqual([]);
  });
});

describe("ProcessDetails — apagar a morada persiste (QA)", () => {
  it("a morada apagada leva o nome alternativo (`address`) que o servidor também tinha", async () => {
    const utilizador = userEvent.setup();
    montar();
    const campo = await editarCartaoDe(utilizador, /Pessoais|Cliente/i, "Rua das Flores 1");

    await utilizador.clear(campo);
    const { processo, cliente } = await guardar(utilizador);

    expect(cliente.data.dados_pessoais.morada_fiscal).toBe("");
    expect(cliente.data.dados_pessoais.address).toBe("");
    expect(processo.personal_data.morada_fiscal).toBe("");
  });

  it("o input NÃO volta a mostrar o nome alternativo depois de apagado", async () => {
    const utilizador = userEvent.setup();
    montar();
    const campo = await editarCartaoDe(utilizador, /Pessoais|Cliente/i, "Rua das Flores 1");

    await utilizador.clear(campo);
    // Com `value={morada_fiscal || address || ""}` o input voltava a "Rua das Flores 1".
    expect(campo).toHaveValue("");
  });
});

describe("ProcessDetails — financeiro: apagar e o zero (QA)", () => {
  it("apagar o rendimento mensal envia null e retira o nome alternativo", async () => {
    const utilizador = userEvent.setup();
    montar();
    const campo = await editarCartaoDe(utilizador, /Financeiro/i, "2100");

    await utilizador.clear(campo);
    expect(campo).toHaveValue(null);
    const { processo } = await guardar(utilizador);

    expect(processo.financial_data.monthly_income).toBeNull();
    expect(processo.financial_data.salario_liquido).toBeNull();
    // O resto da secção vai como estava.
    expect(processo.financial_data.renda_habitacao_atual).toBe(450);
  });

  it("escrever 0 grava 0 (um valor) e não apaga o campo", async () => {
    const utilizador = userEvent.setup();
    montar();
    const campo = await editarCartaoDe(utilizador, /Financeiro/i, "2100");

    await utilizador.clear(campo);
    await utilizador.type(campo, "0");
    expect(campo).toHaveValue(0);
    const { processo } = await guardar(utilizador);

    expect(processo.financial_data.monthly_income).toBe(0);
    // O alternativo só sai quando o canónico é APAGADO, não quando vale 0.
    expect(processo.financial_data.salario_liquido).toBe(1900);
  });

  it("os dependentes a 0 mostram-se como 0, não como campo vazio", async () => {
    const utilizador = userEvent.setup();
    pacote.valor.process = { ...PROCESSO, financial_data: { ...PROCESSO.financial_data, nr_dependentes: 0 } };
    montar();
    await editarCartaoDe(utilizador, /Financeiro/i, "2100");
    expect(screen.getAllByDisplayValue("0").length).toBeGreaterThan(0);
  });
});

describe("ProcessDetails — 2.º titular (QA)", () => {
  it("apagar um campo do 2.º titular tira-o da secção e guarda os restantes", async () => {
    const utilizador = userEvent.setup();
    montar();
    const campo = await editarCartaoDe(utilizador, /Financeiro/i, "rui.fin");

    await utilizador.clear(campo);
    const { processo } = await guardar(utilizador);

    // O servidor SUBSTITUI a secção: o que não vai deixa de existir.
    expect(processo.titular2_data).not.toHaveProperty("portal_financas_utilizador");
    expect(processo.titular2_data).toMatchObject({
      name: "Rui Costa", nif: "987654321", seg_social_utilizador: "rui.ss",
    });
  });

  it("um NIF do 2.º titular com menos de 9 dígitos NÃO se grava (apagaria o guardado)", async () => {
    const utilizador = userEvent.setup();
    pacote.valor.process = { ...PROCESSO, titular2_data: { ...PROCESSO.titular2_data, nif: "123" } };
    montar();
    await editarCartaoDe(utilizador, /Financeiro/i, "rui.fin");

    await utilizador.click(screen.getByRole("button", { name: "Guardar" }));

    // Nada saiu para o servidor, nem o processo nem o cliente.
    await new Promise((r) => setTimeout(r, 150));
    expect(gravar.updateProcess).not.toHaveBeenCalled();
    expect(gravar.updateClient).not.toHaveBeenCalled();
  });
});
