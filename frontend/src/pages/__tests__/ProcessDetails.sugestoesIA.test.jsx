/**
 * «Rever Sugestões IA» abre quando a análise termina — mesmo vinda do separador Documentos (Lote 7.3).
 *
 * O defeito: a análise corre no separador Documentos, mas a barra «Rever» e o painel estavam desenhados
 * dentro do separador Resumo. Quem analisava não via nada acontecer e o painel «não abria». Monta a
 * página REAL (só o separador Documentos é falseado, para disparar a entrega das sugestões).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import servicoPorPagar from "@/test/fixtures/parceiro/servico_por_pagar.json";

// ── Fronteiras falsas ────────────────────────────────────────────────
// O separador Documentos é falseado por um botão que entrega à página o que a análise de um
// documento devolve: é a ligação separador → página que aqui se afirma, não o S3FileManager.
vi.mock("../../components/processDetails/tabs/DocumentsTab", () => ({
  default: ({ handleDocumentDataExtracted }) => (
    <button
      type="button"
      onClick={() => handleDocumentDataExtracted({
        extractedData: { nif: "987654321", nome_completo: "Ana Martins" },
        conflicts: [],
        sourceDocument: "cartao_cidadao.pdf",
      })}
    >
      Simular análise concluída
    </button>
  ),
}));
vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));

// O perfil da sessão muda por teste (a origem financeira só aparece à gestão).
const sessao = vi.hoisted(() => ({ papel: "diretor" }));

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

const mutacaoFalsa = () => ({ mutateAsync: vi.fn(() => Promise.resolve({})), isPending: false });

vi.mock("../../hooks/mutations/useProcessMutations", () => ({
  useProcessMutations: () => ({
    moveProcess: mutacaoFalsa(),
    updateProcess: mutacaoFalsa(),
    updateClient: mutacaoFalsa(),
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

// ── Dados ────────────────────────────────────────────────────────────
const PROCESSO = {
  id: "proc-1",
  process_ref: "PROC-012",
  process_number: 12,
  client_id: "cli-1",
  client_name: "Ana Martins",
  status: "Em Análise",
  service_type: "Crédito Habitação",
  priority: "Média",
  created_at: "2026-09-01T10:00:00Z",
  updated_at: "2026-09-20T10:00:00Z",
  personal_data: { nome: "Ana Martins", nif: "123456789" },
  financial_data: {},
  real_estate_data: {},
  credit_data: {},
  activities: [],
  labels: [],
  consultor_names: ["Carla Consultora"],
  assigned_consultor_ids: ["u-1"],
};

const CLIENTE = { id: "cli-1", name: "Ana Martins", email: "ana@exemplo.pt" };

const pacoteCompleto = (overrides = {}) => ({
  process: PROCESSO,
  client: CLIENTE,
  history: [],
  activities: [],
  deadlines: [],
  workflowStatuses: [
    { id: "s1", name: "Em Análise", order: 1 },
    { id: "s2", name: "Aprovado", order: 2 },
  ],
  isLoading: false,
  isError: false,
  error: null,
  refetchAll: vi.fn(() => Promise.resolve()),
  processQuery: { isLoading: false, isFetching: false, dataUpdatedAt: Date.now() },
  clientQuery: { isLoading: false, isFetching: false },
  ...overrides,
});

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
  pacote.valor = pacoteCompleto();
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) }),
  );
  // O jsdom não implementa nenhuma destas.
  URL.createObjectURL = vi.fn(() => "blob:x");
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  vi.restoreAllMocks();
});

// ====================================================================

describe("ProcessDetails — «Rever Sugestões IA» reage à análise feita noutro separador (Lote 7.3)", () => {
  async function analisarNoSeparadorDocumentos() {
    montar();
    await userEvent.click(await screen.findByRole("tab", { name: /documentos/i }));
    await userEvent.click(await screen.findByRole("button", { name: /simular análise concluída/i }));
  }

  it("o painel abre logo, sem sair do separador Documentos", async () => {
    await analisarNoSeparadorDocumentos();

    // Antes: a barra «Rever» vivia dentro do Resumo e o painel nunca abria.
    expect(await screen.findByTestId("sugestoes-ia-drawer")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /documentos/i, hidden: true })).toHaveAttribute("data-state", "active");
  });

  it("fechado o painel, a barra «Rever» continua à vista (e reabre-o) em qualquer separador", async () => {
    await analisarNoSeparadorDocumentos();
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByTestId("sugestoes-ia-drawer")).toBeNull());

    const rever = await screen.findByRole("button", { name: /rever/i });
    await userEvent.click(rever);

    expect(await screen.findByTestId("sugestoes-ia-drawer")).toBeInTheDocument();
  });

  it("sem análise não há barra nem painel (contraprova)", async () => {
    montar();
    await screen.findByRole("tab", { name: /documentos/i });

    expect(screen.queryByRole("button", { name: /rever/i })).toBeNull();
    expect(screen.queryByTestId("sugestoes-ia-drawer")).toBeNull();
  });

  it("uma segunda análise volta a abrir o painel", async () => {
    await analisarNoSeparadorDocumentos();
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByTestId("sugestoes-ia-drawer")).toBeNull());

    await userEvent.click(screen.getByRole("button", { name: /simular análise concluída/i }));

    expect(await screen.findByTestId("sugestoes-ia-drawer")).toBeInTheDocument();
  });
});
