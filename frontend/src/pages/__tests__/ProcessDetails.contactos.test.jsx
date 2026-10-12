/**
 * Apagar o email/telefone nos «Dados do Processo» tem de persistir (QA, Out 2026).
 *
 * O defeito: o utilizador apagava o email, carregava em Guardar, via o toast de
 * sucesso — e o email antigo voltava. O formulário nunca enviava um contacto
 * vazio (três sítios o descartavam por «protecção»), e o servidor ainda o
 * recompunha a partir da ficha do cliente. Aqui monta-se a PÁGINA real e
 * afirma-se o que SAI para o servidor.
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
  financial_data: {},
  real_estate_data: {},
  credit_data: {},
  activities: [],
  labels: [],
  consultor_names: ["Carla Consultora"],
  assigned_consultor_ids: ["u-1"],
};

const CLIENTE = {
  id: "cli-1",
  nome: "Ana Martins",
  contacto: { email: "ana@exemplo.pt", telefone: "912345678" },
  dados_pessoais: { nif: "123456789" },
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

/** Abre o separador Pessoais e põe o cartão «Contactos» em edição. */
async function editarContactos(utilizador) {
  await screen.findByTestId("layout");
  const separadores = screen.getAllByRole("tab", { name: /Pessoais|Cliente/i });
  await utilizador.click(separadores[0]);
  const emailAntes = await screen.findByDisplayValue("ana@exemplo.pt");
  const cartao = emailAntes.closest(".read-only-card") || emailAntes.closest("div.border-l-4");
  await utilizador.click(within(cartao).getByTitle("Editar"));
  return screen.findByDisplayValue("ana@exemplo.pt");
}

describe("ProcessDetails — apagar um contacto persiste (QA)", () => {
  it("apagar o email e guardar envia o email VAZIO ao processo e ao cliente", async () => {
    const utilizador = userEvent.setup();
    montar();
    const campoEmail = await editarContactos(utilizador);

    await utilizador.clear(campoEmail);
    await utilizador.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => expect(gravar.updateProcess).toHaveBeenCalledTimes(1));
    expect(gravar.updateProcess.mock.calls[0][0].client_email).toBe("");
    // O telefone não foi tocado: continua a ir com o valor que tinha.
    expect(gravar.updateProcess.mock.calls[0][0].client_phone).toBe("912345678");

    const pedidoCliente = gravar.updateClient.mock.calls[0][0];
    expect(pedidoCliente.data.contacto).toEqual({ email: "", telefone: "912345678" });
    expect(pedidoCliente.clearContactFields).toEqual(["email"]);
  });

  it("apagar o telefone envia o telefone vazio e mantém o email", async () => {
    const utilizador = userEvent.setup();
    montar();
    await editarContactos(utilizador);

    await utilizador.clear(screen.getByDisplayValue("912345678"));
    await utilizador.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => expect(gravar.updateProcess).toHaveBeenCalledTimes(1));
    expect(gravar.updateProcess.mock.calls[0][0].client_phone).toBe("");
    expect(gravar.updateProcess.mock.calls[0][0].client_email).toBe("ana@exemplo.pt");
    expect(gravar.updateClient.mock.calls[0][0].clearContactFields).toEqual(["telefone"]);
  });

  it("guardar sem tocar nos contactos não manda limpar nada", async () => {
    const utilizador = userEvent.setup();
    montar();
    await editarContactos(utilizador);

    await utilizador.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => expect(gravar.updateProcess).toHaveBeenCalledTimes(1));
    expect(gravar.updateClient.mock.calls[0][0].clearContactFields).toEqual([]);
    expect(gravar.updateProcess.mock.calls[0][0].client_email).toBe("ana@exemplo.pt");
  });
});

