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
import { construirContextoDeNavegacao } from "../../utils/processNavigation";

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

describe("ProcessDetails — nota de voz (Épico 7) sobrevive ao Ponto 9", () => {
  // O Ponto 9 mudou o sítio: o Histórico ficou só de leitura e a nota de
  // voz passou para o cartão de Observações, no Resumo. O que este bloco
  // defende continua a ser o mesmo — que o Épico 7 não se parte quando se
  // mexe à volta dele —, mas agora no sítio certo. Só a PÁGINA montada
  // prova esta mudança: os testes de componente passam a montar cada peça
  // no sítio novo e nenhum deles vê que as duas foram religadas.

  it("o botão vive no Resumo, ao lado das notas escritas", async () => {
    montar();
    await screen.findByTestId("layout");

    // O Resumo abre por omissão — não é preciso navegar.
    expect(await screen.findByTestId("voice-note-open")).toBeInTheDocument();
  });

  it("clicar abre o gravador real", async () => {
    const utilizador = userEvent.setup();
    montar();
    await screen.findByTestId("layout");

    await utilizador.click(await screen.findByTestId("voice-note-open"));

    // O `VoiceNoteRecorder` é o real: se a ligação se partir, não abre.
    // Não se procura o botão de GRAVAR: o jsdom não tem `MediaRecorder`
    // nem `getUserMedia`, pelo que o componente mostra — correctamente — o
    // caminho de recurso. O que aqui se prova é que o diálogo abriu e que
    // há por onde entregar áudio.
    expect(
      await screen.findByRole("button", { name: /Carregar ficheiro/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Enviar nota/ })).toBeInTheDocument();
  });

  it("o gravador está montado com o Resumo, não com o Histórico", async () => {
    // Escrevi primeiro este teste a afirmar que "mudar de separador não
    // fecha a gravação" — e falhou por bom motivo: o `VoiceNoteRecorder`
    // é um diálogo MODAL, logo com ele aberto os separadores por trás
    // ficam `aria-hidden` e não há como lá clicar. A afirmação era sobre
    // um percurso que a UI não permite, e ficaria aqui a dar uma garantia
    // falsa. O que se pode afirmar, e é o que importa, é que o gatilho e
    // o gravador estão ligados a partir do Resumo — o separador que abre
    // por omissão — sem passar pelo Histórico.
    const utilizador = userEvent.setup();
    montar();
    await screen.findByTestId("layout");

    expect(screen.getByRole("tab", { name: /Resumo/i })).toHaveAttribute(
      "data-state",
      "active",
    );
    await utilizador.click(await screen.findByTestId("voice-note-open"));

    expect(
      await screen.findByRole("button", { name: /Enviar nota/ }),
    ).toBeInTheDocument();
  });

  it("o Histórico não oferece nada com que escrever", async () => {
    // Ponto 9: trilha de auditoria. A ausência afirma-se, senão volta.
    const utilizador = userEvent.setup();
    montar();
    await screen.findByTestId("layout");

    await utilizador.click(screen.getByRole("tab", { name: /Histórico/i }));
    await screen.findByTestId("historico-so-leitura");

    expect(screen.queryByTestId("quick-note-open")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Registar Atividade/i }),
    ).not.toBeInTheDocument();
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

describe("ProcessDetails — cartão de partilha (D-25)", () => {
  it("um processo partilhado mostra com quem — a ligação página ↔ cartão", async () => {
    pacote.valor = pacoteCompleto({
      process: {
        ...PROCESSO,
        partner_companies: [
          { company_id: "cmp-domus", company_name: "Domus", network_id: "grupo_domus" },
        ],
      },
    });
    montar();
    await screen.findByTestId("layout");

    const cartao = await screen.findByTestId("cartao-partilha");
    expect(cartao.textContent).toContain("Domus");
    // O perfil da sessão é consultor: vê com quem, mas não pode revogar.
    expect(screen.queryByRole("button", { name: /Revogar partilha com/ })).toBeNull();
  });

  it("um processo exclusivo da casa não mostra o cartão (contraprova)", async () => {
    montar();
    await screen.findByTestId("layout");
    await waitFor(() => expect(screen.getAllByText(/Ana Martins/).length).toBeGreaterThan(0));
    expect(screen.queryByTestId("cartao-partilha")).toBeNull();
  });
});

describe("ProcessDetails — serviço pago pelo parceiro (Portal do Parceiro)", () => {
  afterEach(() => { sessao.papel = "consultor"; });

  it("um processo COM parceiro mostra o cartão à equipa e o dado é pedido", async () => {
    pacote.valor = pacoteCompleto({ process: { ...PROCESSO, assigned_parceiro_id: "pt-1" } });
    const api = await import("../../services/api");
    api.getServicoDoParceiro.mockClear();
    montar();
    await screen.findByTestId("layout");

    expect(await screen.findByTestId("cartao-servico-do-parceiro")).toBeInTheDocument();
    await waitFor(() => expect(api.getServicoDoParceiro).toHaveBeenCalledWith("proc-1"));
  });

  it("um processo SEM parceiro não mostra o cartão e nunca pede o dado (contraprova)", async () => {
    const api = await import("../../services/api");
    api.getServicoDoParceiro.mockClear();
    montar();
    await screen.findByTestId("layout");
    await waitFor(() => expect(screen.getAllByText(/Ana Martins/).length).toBeGreaterThan(0));

    expect(screen.queryByTestId("cartao-servico-do-parceiro")).toBeNull();
    expect(api.getServicoDoParceiro).not.toHaveBeenCalled();
  });

  it.each(["indexacao", "parceiro"])("o perfil %s não vê o cartão, mesmo com parceiro, e o dado nunca é pedido", async (papel) => {
    sessao.papel = papel;
    pacote.valor = pacoteCompleto({ process: { ...PROCESSO, assigned_parceiro_id: "pt-1" } });
    const api = await import("../../services/api");
    api.getServicoDoParceiro.mockClear();
    montar();
    await screen.findByTestId("layout");
    await waitFor(() => expect(screen.getAllByText(/Ana Martins/).length).toBeGreaterThan(0));

    expect(screen.queryByTestId("cartao-servico-do-parceiro")).toBeNull();
    expect(api.getServicoDoParceiro).not.toHaveBeenCalled();
  });
});

describe("ProcessDetails — origem financeira (Bloco 4, ponto 7)", () => {
  afterEach(() => { sessao.papel = "consultor"; });

  it.each(["diretor", "ceo", "admin"])(
    "a gestão (%s) vê o cartão e o dado é pedido",
    async (papel) => {
      sessao.papel = papel;
      const api = await import("../../services/api");
      api.getOrigemFinanceira.mockClear();
      montar();
      await screen.findByTestId("layout");

      expect(await screen.findByTestId("cartao-origem-financeira")).toBeInTheDocument();
      await waitFor(() => expect(api.getOrigemFinanceira).toHaveBeenCalledWith("proc-1"));
    },
  );

  it.each(["consultor", "intermediario", "administrativo", "indexacao"])(
    "%s NÃO vê o cartão e o dado nunca é pedido",
    async (papel) => {
      sessao.papel = papel;
      const api = await import("../../services/api");
      api.getOrigemFinanceira.mockClear();
      montar();
      await screen.findByTestId("layout");
      await waitFor(() => expect(screen.getAllByText(/Ana Martins/).length).toBeGreaterThan(0));

      expect(screen.queryByTestId("cartao-origem-financeira")).toBeNull();
      expect(api.getOrigemFinanceira).not.toHaveBeenCalled();
    },
  );
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


describe("ProcessDetails — processo FECHADO: modo de leitura e Reabrir", () => {
  const FASES = [
    { id: "s1", name: "Em Análise", label: "Em Análise", order: 1, is_active: true },
    { id: "s2", name: "Aprovado", label: "Aprovado", order: 2, is_active: true },
    { id: "s3", name: "concluidos", label: "Concluído", order: 3, is_active: false },
  ];

  const fechado = () =>
    pacoteCompleto({
      process: { ...PROCESSO, status: "concluidos" },
      workflowStatuses: FASES,
    });

  afterEach(() => { sessao.papel = "consultor"; });

  it.each(["consultor", "admin", "ceo", "master"])(
    "%s vê o aviso de processo fechado e o botão Reabrir (sem isenção por cargo)",
    async (papel) => {
      sessao.papel = papel;
      pacote.valor = fechado();
      montar();

      expect(await screen.findByTestId("processo-fechado-banner")).toBeInTheDocument();
      expect(screen.getByTestId("reabrir-processo-btn")).toBeInTheDocument();
      expect(screen.queryByText(/pode editar valores retroativamente/i)).toBeNull();
    },
  );

  it("um processo aberto não mostra aviso nem Reabrir (contraprova)", async () => {
    pacote.valor = pacoteCompleto({ workflowStatuses: FASES });
    montar();
    await screen.findByTestId("layout");
    await waitFor(() => expect(screen.getAllByText(/Ana Martins/).length).toBeGreaterThan(0));

    expect(screen.queryByTestId("processo-fechado-banner")).toBeNull();
    expect(screen.queryByTestId("reabrir-processo-btn")).toBeNull();
  });

  it("o motor manda: uma fase configurada como inativa fecha mesmo fora da lista legada", async () => {
    pacote.valor = pacoteCompleto({
      process: { ...PROCESSO, status: "renegociacao" },
      workflowStatuses: [
        ...FASES,
        { id: "s4", name: "renegociacao", label: "Renegociação", order: 4, is_active: false },
      ],
    });
    montar();

    expect(await screen.findByTestId("processo-fechado-banner")).toBeInTheDocument();
  });

  it("o separador Documentos fica em modo de leitura: sem Upload", async () => {
    pacote.valor = fechado();
    montar();
    await screen.findByTestId("processo-fechado-banner");
    await userEvent.click(screen.getByRole("tab", { name: /documentos/i }));

    expect(await screen.findByTestId("documentos-processo-fechado")).toBeInTheDocument();
    expect(screen.queryByTestId("upload-file-btn")).toBeNull();
    expect(screen.queryByTestId("portal-request-add-button")).toBeNull();
  });

  it("o separador Documentos de um processo ABERTO mantém o Upload (contraprova)", async () => {
    pacote.valor = pacoteCompleto({ workflowStatuses: FASES });
    montar();
    await screen.findByTestId("layout");
    await userEvent.click(await screen.findByRole("tab", { name: /documentos/i }));

    expect(await screen.findByTestId("upload-file-btn")).toBeInTheDocument();
    expect(screen.queryByTestId("documentos-processo-fechado")).toBeNull();
  });

  // D-34 — as cinco áreas secundárias. O servidor recusa (403) a TODOS os
  // perfis; o ecrã não pode oferecer o que vai ser recusado.
  describe("D-34: acções secundárias desactivadas", () => {
    // Fase fechada SÓ no motor (fora da lista legada): o menu do Portal não
    // está desactivado à nascença, por isso a prova é a dos itens.
    const soNoMotor = () =>
      pacoteCompleto({
        process: { ...PROCESSO, status: "renegociacao" },
        workflowStatuses: [
          ...FASES,
          { id: "s4", name: "renegociacao", label: "Renegociação", order: 4, is_active: false },
        ],
      });

    it.each(["consultor", "admin", "master"])(
      "%s: Copiar Link e Enviar por Email do Portal ficam desactivados",
      async (papel) => {
        sessao.papel = papel;
        pacote.valor = soNoMotor();
        montar();
        await screen.findByTestId("processo-fechado-banner");

        await userEvent.click(screen.getByRole("button", { name: /portal do cliente/i }));
        expect(await screen.findByRole("menuitem", { name: /copiar link/i })).toHaveAttribute("aria-disabled", "true");
        expect(screen.getByRole("menuitem", { name: /enviar por email/i })).toHaveAttribute("aria-disabled", "true");
      },
    );

    it("com o processo ABERTO os dois itens estão activos (contraprova)", async () => {
      pacote.valor = pacoteCompleto({ workflowStatuses: FASES });
      montar();
      await screen.findByTestId("layout");
      await waitFor(() => expect(screen.getAllByText(/Ana Martins/).length).toBeGreaterThan(0));

      await userEvent.click(screen.getByRole("button", { name: /portal do cliente/i }));
      expect(await screen.findByRole("menuitem", { name: /copiar link/i })).not.toHaveAttribute("aria-disabled", "true");
      expect(screen.getByRole("menuitem", { name: /enviar por email/i })).not.toHaveAttribute("aria-disabled", "true");
    });

    it("o separador Mensagens não deixa escrever ao cliente", async () => {
      pacote.valor = soNoMotor();
      montar();
      await screen.findByTestId("processo-fechado-banner");
      await userEvent.click(screen.getByRole("tab", { name: /mensagens/i }));

      expect(await screen.findByTestId("mensagens-somente-leitura")).toBeInTheDocument();
      expect(screen.queryByPlaceholderText(/escreva uma mensagem para o cliente/i)).toBeNull();
    });

    it("num processo ABERTO o separador Mensagens deixa escrever (contraprova)", async () => {
      pacote.valor = pacoteCompleto({ workflowStatuses: FASES });
      montar();
      await screen.findByTestId("layout");
      await userEvent.click(await screen.findByRole("tab", { name: /mensagens/i }));

      expect(await screen.findByPlaceholderText(/escreva uma mensagem para o cliente/i)).toBeInTheDocument();
      expect(screen.queryByTestId("mensagens-somente-leitura")).toBeNull();
    });
  });

  it("Reabrir só oferece fases activas e chama o servidor com a escolhida", async () => {
    const api = await import("../../services/api");
    api.reopenProcess.mockClear();
    pacote.valor = fechado();
    montar();

    await userEvent.click(await screen.findByTestId("reabrir-processo-btn"));
    const dialogo = await screen.findByTestId("reabrir-processo-dialog");
    expect(within(dialogo).getByTestId("reabrir-confirmar")).toBeDisabled();

    await userEvent.click(within(dialogo).getByTestId("reabrir-fase-select"));
    expect(screen.queryByRole("option", { name: "Concluído" })).toBeNull();
    await userEvent.click(await screen.findByRole("option", { name: "Aprovado" }));
    await userEvent.click(within(dialogo).getByTestId("reabrir-confirmar"));

    await waitFor(() => expect(api.reopenProcess).toHaveBeenCalledWith("proc-1", "Aprovado"));
    await waitFor(() => expect(pacote.valor.refetchAll).toHaveBeenCalled());
  });
});


describe("ProcessDetails — «Voltar» devolve a listagem com a pesquisa", () => {
  const LISTA = "/processos?search=ana&status=cpcv&page=2";

  function Sonda() {
    const l = useLocation();
    const tipo = useNavigationType();
    const nav = useNavigate();
    return (
      <div>
        <div data-testid="sonda">{l.pathname}{l.search}</div>
        <div data-testid="tipo">{tipo}</div>
        <button type="button" onClick={() => nav(-1)}>recuar-na-historia</button>
      </div>
    );
  }

  /** Listagem → detalhe, com o contexto de navegação que a listagem leva consigo. */
  function montarDaLista({ ids = ["proc-1", "proc-2", "proc-3"], semHistoria = false } = {}) {
    const contexto = construirContextoDeNavegacao({
      ids, page: 1, size: 20, total: ids.length, origem: LISTA,
    });
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    const detalhe = { pathname: "/process/proc-1", state: { contextoDeNavegacao: contexto } };
    return render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter
          initialEntries={semHistoria ? [detalhe] : [LISTA, detalhe]}
          initialIndex={semHistoria ? 0 : 1}
        >
          <Routes>
            <Route path="/processos" element={<Sonda />} />
            <Route path="/process/:id" element={<><ProcessDetails /><Sonda /></>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  beforeEach(() => { window.sessionStorage.clear(); });

  it("Voltar regressa à listagem COM a pesquisa e os filtros", async () => {
    montarDaLista();
    await userEvent.click(await screen.findByRole("button", { name: "Voltar" }));
    expect(await screen.findByTestId("sonda")).toHaveTextContent(LISTA);
  });

  it("as setas SUBSTITUEM a entrada: a história não cresce, e recuar regressa à listagem", async () => {
    montarDaLista();
    await userEvent.click(await screen.findByRole("button", { name: "Processo seguinte" }));
    await waitFor(() => expect(screen.getByTestId("sonda")).toHaveTextContent("/process/proc-2"));

    // Antes, a seta empilhava: recuar levava ao processo anterior, não à listagem.
    expect(screen.getByTestId("tipo")).toHaveTextContent("REPLACE");
    await userEvent.click(screen.getByRole("button", { name: "recuar-na-historia" }));
    expect(await screen.findByTestId("sonda")).toHaveTextContent(LISTA);
  });

  it("aberto sem história (separador novo), Voltar vai para a listagem de origem", async () => {
    montarDaLista({ semHistoria: true });
    await userEvent.click(await screen.findByRole("button", { name: "Voltar" }));
    expect(await screen.findByTestId("sonda")).toHaveTextContent(LISTA);
  });
});
