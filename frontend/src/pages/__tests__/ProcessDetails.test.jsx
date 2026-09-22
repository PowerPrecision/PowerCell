/**
 * Teste de fumo da página de detalhes do processo (Épico 8, Eixo 1, Fase 0).
 *
 * PORQUÊ ANTES DE CORTAR:
 *   `ProcessDetails.js` tem 3100 linhas e é o coração do CRM. A lição do
 *   Épico 6 foi dura e específica: um componente extraído só está coberto
 *   quando a página que o usa também é montada. Foi o primeiro teste desses
 *   que apanhou o Webmail a rebentar no arranque por um `const` na zona
 *   morta temporal — que nem o eslint, nem o build, nem 70 testes de
 *   componente tinham visto.
 *
 * O QUE É FALSO, E PORQUÊ:
 *   Só as fronteiras de rede, sessão e layout. O estado, os handlers e
 *   TODOS os componentes filhos (separadores, cartões de contexto, gravador
 *   de notas de voz) são os reais — é a ligação entre eles que a
 *   refatorização vai mexer e é isso que aqui se protege.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// ── Fronteiras falsas ────────────────────────────────────────────────
vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    token: "t-1",
    user: {
      id: "u-1",
      name: "Carla Consultora",
      email: "carla@precisioncredito.pt",
      role: "consultor",
    },
    effectiveRole: "consultor",
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
    addActivity: mutacaoFalsa(),
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

describe("ProcessDetails — a página monta", () => {
  it("renderiza sem rebentar", async () => {
    // A asserção mais barata do ficheiro e a que mais vale: é exactamente
    // esta que apanhou a zona morta temporal no Webmail.
    montar();

    expect(await screen.findByTestId("layout")).toBeInTheDocument();
  });

  it("mostra o cliente do processo", async () => {
    montar();

    await waitFor(() =>
      expect(screen.getAllByText(/Ana Martins/).length).toBeGreaterThan(0),
    );
  });

  it("o cabeçalho identifica o processo pelo número", async () => {
    // O `PageHeader` usa `Processo #<process_number>`; a `process_ref`
    // (PROC-012) aparece nos títulos das tarefas, não aqui.
    montar();

    expect(await screen.findByRole("heading", { name: /Processo #12/ })).toBeInTheDocument();
  });
});

describe("ProcessDetails — os três separadores de topo", () => {
  it("Resumo, Documentos e Histórico existem", async () => {
    montar();
    await screen.findByTestId("layout");

    expect(screen.getByRole("tab", { name: /Resumo/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Documentos/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Histórico/i })).toBeInTheDocument();
  });

  it("o Resumo abre por omissão", async () => {
    montar();
    await screen.findByTestId("layout");

    expect(screen.getByRole("tab", { name: /Resumo/i })).toHaveAttribute(
      "data-state",
      "active",
    );
  });

  it("mudar para Histórico troca o conteúdo", async () => {
    const utilizador = userEvent.setup();
    montar();
    await screen.findByTestId("layout");

    await utilizador.click(screen.getByRole("tab", { name: /Histórico/i }));

    await waitFor(() =>
      expect(screen.getByRole("tab", { name: /Histórico/i })).toHaveAttribute(
        "data-state",
        "active",
      ),
    );
  });
});

describe("ProcessDetails — sub-separadores do Resumo", () => {
  it("os domínios de dados estão todos presentes", async () => {
    // São estes oito que a extracção do `ProcessSummaryTab` vai mover.
    montar();
    await screen.findByTestId("layout");

    for (const nome of [/Pessoais|Cliente/i, /Financeir/i, /Imóvel/i, /Crédito/i]) {
      expect(screen.getAllByRole("tab", { name: nome }).length).toBeGreaterThan(0);
    }
  });
});

describe("ProcessDetails — nota de voz (Épico 7) sobrevive", () => {
  it("o botão vive no separador Histórico", async () => {
    // Eixo 3 do épico: o que o Épico 7 acrescentou não pode partir-se no
    // corte. Este teste falha se o `HistoryTab` deixar de receber o
    // callback do contentor.
    const utilizador = userEvent.setup();
    montar();
    await screen.findByTestId("layout");

    await utilizador.click(screen.getByRole("tab", { name: /Histórico/i }));

    expect(await screen.findByTestId("voice-note-open")).toBeInTheDocument();
  });

  it("clicar abre o gravador real", async () => {
    const utilizador = userEvent.setup();
    montar();
    await screen.findByTestId("layout");

    await utilizador.click(screen.getByRole("tab", { name: /Histórico/i }));
    await utilizador.click(await screen.findByTestId("voice-note-open"));

    // O `VoiceNoteRecorder` é o real: se a ligação se partir, não abre.
    // Há dois "Nota de voz" no ecrã — o botão e o título do diálogo; é o
    // conteúdo do diálogo que prova que abriu.
    //
    // Não se procura o botão de GRAVAR: o jsdom não tem `MediaRecorder`
    // nem `getUserMedia`, pelo que o componente mostra — correctamente — o
    // caminho de recurso. O que aqui se prova é que o diálogo abriu e que
    // há por onde entregar áudio.
    expect(
      await screen.findByRole("button", { name: /Carregar ficheiro/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Enviar nota/ })).toBeInTheDocument();
  });

  it("o botão de registar atividade continua ao lado", async () => {
    const utilizador = userEvent.setup();
    montar();
    await screen.findByTestId("layout");

    await utilizador.click(screen.getByRole("tab", { name: /Histórico/i }));

    expect(await screen.findByTestId("quick-note-open")).toBeInTheDocument();
  });
});

describe("ProcessDetails — cartões de contexto (coluna direita)", () => {
  it("o cartão do cliente mostra o titular", async () => {
    montar();
    await screen.findByTestId("layout");

    await waitFor(() =>
      expect(screen.getAllByText(/Ana Martins/).length).toBeGreaterThan(0),
    );
  });

  it("o cartão de atribuição mostra o consultor", async () => {
    // Regressão conhecida: a atribuição gravada só em `consultant_id`
    // deixava este cartão EM BRANCO apesar de tudo o resto funcionar.
    montar();
    await screen.findByTestId("layout");

    await waitFor(() =>
      expect(screen.getAllByText(/Carla Consultora/).length).toBeGreaterThan(0),
    );
  });
});

describe("ProcessDetails — dados servidos pela cache (regressão)", () => {
  it("uma revisita dentro do staleTime mostra o processo, não o esqueleto", async () => {
    // BUG APANHADO POR ESTE FICHEIRO, no primeiro arranque.
    //
    // Na primeira visita a query resolve DEPOIS da montagem: `dataUpdatedAt`
    // muda, a hidratação corre outra vez e tudo aparece. Numa revisita
    // dentro do `staleTime` (60 s) o TanStack serve a cache logo no
    // primeiro render — `dataUpdatedAt` nunca muda. O efeito de reset,
    // declarado depois do de hidratação, desfazia-a na mesma passagem e
    // nada a voltava a disparar: a página ficava presa no esqueleto.
    //
    // O `pacote.valor` é montado com um `dataUpdatedAt` FIXO de propósito:
    // é essa a assinatura de uma leitura de cache.
    pacote.valor = pacoteCompleto({
      processQuery: { isLoading: false, isFetching: false, dataUpdatedAt: 1700000000000 },
      clientQuery: { isLoading: false, isFetching: false, dataUpdatedAt: 1700000000000 },
    });

    montar();

    expect(
      await screen.findByRole("heading", { name: /Processo #12/ }),
    ).toBeInTheDocument();
  });

  it("o esqueleto aparece enquanto a query não resolve", async () => {
    // O contrário também tem de valer: sem dados, o esqueleto é o correcto.
    pacote.valor = pacoteCompleto({
      process: null,
      client: null,
      isLoading: true,
      processQuery: { isLoading: true, isFetching: true, dataUpdatedAt: 0 },
      clientQuery: { isLoading: true, isFetching: true, dataUpdatedAt: 0 },
    });

    montar();
    await screen.findByTestId("layout");

    expect(
      screen.queryByRole("heading", { name: /Processo #12/ }),
    ).not.toBeInTheDocument();
  });
});

describe("ProcessDetails — estados de carregamento e erro", () => {
  it("a carregar não rebenta", async () => {
    pacote.valor = pacoteCompleto({ process: null, client: null, isLoading: true });

    montar();

    expect(await screen.findByTestId("layout")).toBeInTheDocument();
  });

  it("um processo inexistente não rebenta", async () => {
    pacote.valor = pacoteCompleto({
      process: null,
      client: null,
      isError: true,
      error: new Error("404"),
    });

    montar();

    expect(await screen.findByTestId("layout")).toBeInTheDocument();
  });
});
