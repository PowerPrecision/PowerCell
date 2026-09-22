/**
 * Testes de INTEGRAÇÃO da página do Webmail (Épico 6, seguimento).
 *
 * Os testes de componente provam cada coluna isoladamente. O que ficava
 * por provar era a LIGAÇÃO: a página é o contentor que detém o estado e
 * os handlers, e foi precisamente essa ligação que o épico refez.
 *
 * O que é falso aqui, e porquê:
 * - `DashboardLayout` — arrastava a app inteira (sidebar, notificações,
 *   WebSockets); um passthrough chega para o que se testa;
 * - `AuthContext`, `useWebmailEmails`, `useNewEmailRealtime` e o `fetch` —
 *   são as fronteiras de rede/sessão. Falsear estas quatro é o suficiente:
 *   o estado, os handlers e TODOS os componentes extraídos são os reais.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// ── Fronteiras falsas ────────────────────────────────────────────────
vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    token: "t-1",
    user: { id: "u-1", email: "consultor@powercell.pt", name: "Consultor" },
    effectiveRole: "consultor",
    activeCompanyId: "c-1",
    effectiveCompanyId: "c-1",
  }),
}));

const estadoDaLista = vi.hoisted(() => ({ valor: null }));

vi.mock("../../hooks/useWebmailEmails", async (original) => {
  const real = await original();
  return {
    ...real,
    useWebmailEmails: (filtros) => {
      estadoDaLista.ultimosFiltros = filtros;
      return estadoDaLista.valor;
    },
  };
});

// O `react-resizable-panels` mede os elementos para calcular o layout, e no
// jsdom tudo tem dimensão zero ("Previous layout not found for panel index
// -1"). É limitação do ambiente, não da aplicação: as colunas passam a
// divs simples. O que se testa é o conteúdo delas, não o arrastar da barra.
vi.mock("../../components/ui/resizable", () => ({
  ResizablePanelGroup: ({ children }) => <div>{children}</div>,
  ResizablePanel: ({ children }) => <div>{children}</div>,
  ResizableHandle: () => <div />,
}));

vi.mock("../../hooks/useNewEmailRealtime", () => ({
  useNewEmailRealtime: () => ({ isConnected: false }),
  invalidateEmailQueries: vi.fn(),
}));

import WebmailPage from "../WebmailPage";

// ── Dados ────────────────────────────────────────────────────────────
const email = (overrides = {}) => ({
  id: "e1",
  subject: "Proposta do banco",
  preview: "Segue a simulação",
  from_email: "banco@exemplo.pt",
  client_name: "",
  to_emails: ["geral@powercell.pt"],
  direction: "received",
  is_read: true,
  is_starred: false,
  attachments: [],
  labels: [],
  sent_at: "2026-09-20T10:30:00Z",
  ...overrides,
});

const respostaDaLista = (emails, extra = {}) => ({
  data: { emails, total: emails.length, pages: 1, unread_count: 0, ...extra },
  isLoading: false,
  isFetched: true,
  refetch: vi.fn(),
});

function montar() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/webmail"]}>
        <WebmailPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  estadoDaLista.valor = respostaDaLista([email()]);
  estadoDaLista.ultimosFiltros = null;
  // Qualquer chamada de rede que escape responde vazio em vez de rebentar.
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) }),
  );
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("WebmailPage — as três colunas ligadas", () => {
  it("monta as três colunas", async () => {
    montar();

    expect(await screen.findByTestId("webmail-folder-pane")).toBeInTheDocument();
    expect(screen.getByTestId("webmail-list-pane")).toBeInTheDocument();
    expect(screen.getByTestId("webmail-reading-pane")).toBeInTheDocument();
  });

  it("os emails do hook chegam à lista, agrupados em conversas", async () => {
    estadoDaLista.valor = respostaDaLista([
      email({ id: "a", subject: "Primeiro" }),
      email({ id: "b", subject: "Segundo" }),
    ]);
    montar();

    expect(await screen.findByText("Primeiro")).toBeInTheDocument();
    expect(screen.getByText("Segundo")).toBeInTheDocument();
  });

  it("sem selecção, o painel de leitura convida a escolher", async () => {
    montar();

    expect(
      await screen.findByText("Selecione um email para visualizar"),
    ).toBeInTheDocument();
  });
});

describe("WebmailPage — abrir um email (lista → painel de leitura)", () => {
  it("clicar na conversa carrega o detalhe e mostra-o", async () => {
    const utilizador = userEvent.setup();
    globalThis.fetch = vi.fn((url) => {
      if (String(url).includes("/api/emails/e1")) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              ...email(),
              body: "Confirmamos a pré-aprovação do crédito.",
            }),
        });
      }
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
    });

    montar();
    await utilizador.click(await screen.findByText("Proposta do banco"));

    const leitura = screen.getByTestId("webmail-reading-pane");
    await waitFor(() =>
      expect(
        within(leitura).getByText("Confirmamos a pré-aprovação do crédito."),
      ).toBeInTheDocument(),
    );
  });

  it("um email não lido é marcado como lido ao abrir", async () => {
    const utilizador = userEvent.setup();
    estadoDaLista.valor = respostaDaLista([email({ is_read: false })]);

    const chamadas = [];
    globalThis.fetch = vi.fn((url, opcoes) => {
      chamadas.push({ url: String(url), metodo: opcoes?.method || "GET" });
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(email()) });
    });

    montar();
    await utilizador.click(await screen.findByText("Proposta do banco"));

    await waitFor(() =>
      expect(
        chamadas.some((c) => c.url.includes("/mark") && c.metodo === "POST"),
      ).toBe(true),
    );
  });
});

describe("WebmailPage — conversas (estado no contentor)", () => {
  const conversa = [
    email({ id: "m2", subject: "Re: Proposta", references: "<raiz@x>" }),
    email({ id: "m1", subject: "Proposta", message_id: "<raiz@x>", preview: "Bom dia" }),
  ];

  it("expandir mostra as mensagens anteriores; fechar esconde-as", async () => {
    const utilizador = userEvent.setup();
    estadoDaLista.valor = respostaDaLista(conversa);
    montar();

    const expandir = await screen.findByRole("button", { name: /Expandir conversa/ });
    await utilizador.click(expandir);

    expect(await screen.findByTestId("linha-email-m1")).toBeInTheDocument();

    await utilizador.click(screen.getByRole("button", { name: /Fechar conversa/ }));
    await waitFor(() =>
      expect(screen.queryByTestId("linha-email-m1")).not.toBeInTheDocument(),
    );
  });
});

describe("WebmailPage — navegação de pastas", () => {
  it("escolher uma pasta muda o pedido de dados", async () => {
    const utilizador = userEvent.setup();
    montar();

    await utilizador.click(await screen.findByText("Enviados"));

    await waitFor(() => expect(estadoDaLista.ultimosFiltros.folder).toBe("sent"));
  });

  it("mudar de pasta volta à primeira página", async () => {
    const utilizador = userEvent.setup();
    estadoDaLista.valor = respostaDaLista([email()], { pages: 3 });
    montar();

    await utilizador.click(await screen.findByRole("button", { name: "Seguinte" }));
    await waitFor(() => expect(estadoDaLista.ultimosFiltros.page).toBe(2));

    await utilizador.click(screen.getByText("Destacados"));
    await waitFor(() => expect(estadoDaLista.ultimosFiltros.page).toBe(1));
  });

  it("o cabeçalho da lista acompanha a pasta escolhida", async () => {
    const utilizador = userEvent.setup();
    montar();

    await utilizador.click(await screen.findByText("Enviados"));

    const lista = screen.getByTestId("webmail-list-pane");
    await waitFor(() =>
      expect(within(lista).getByRole("heading", { name: "Enviados" })).toBeInTheDocument(),
    );
  });
});

describe("WebmailPage — compositor", () => {
  it("'Nova Mensagem' abre o compositor e Cancelar fecha-o", async () => {
    const utilizador = userEvent.setup();
    montar();

    await utilizador.click(await screen.findByRole("button", { name: /Nova Mensagem/ }));
    expect(await screen.findByText("Nova Mensagem", { selector: "h2" })).toBeInTheDocument();

    await utilizador.click(screen.getByRole("button", { name: "Cancelar" }));
    await waitFor(() =>
      expect(screen.queryByText("Componha e envie um email")).not.toBeInTheDocument(),
    );
  });

  it("escrever no compositor mantém o texto (estado vive na página)", async () => {
    const utilizador = userEvent.setup();
    montar();

    await utilizador.click(await screen.findByRole("button", { name: /Nova Mensagem/ }));
    const assunto = await screen.findByPlaceholderText(/assunto/i);
    await utilizador.type(assunto, "Pedido de documentos");

    expect(assunto).toHaveValue("Pedido de documentos");
  });
});

describe("WebmailPage — paginação", () => {
  it("a página seguinte é pedida ao hook", async () => {
    const utilizador = userEvent.setup();
    estadoDaLista.valor = respostaDaLista([email()], { pages: 2 });
    montar();

    await utilizador.click(await screen.findByRole("button", { name: "Seguinte" }));

    await waitFor(() => expect(estadoDaLista.ultimosFiltros.page).toBe(2));
  });
});
