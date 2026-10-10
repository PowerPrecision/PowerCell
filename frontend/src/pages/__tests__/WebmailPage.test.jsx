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
 * - `AuthContext`, `useWebmailEmails`, `useNewEmailRealtime` e
 *   `services/api` — são as fronteiras de rede/sessão. Falsear estas
 *   quatro é o suficiente: o estado, os handlers e TODOS os componentes
 *   extraídos são os reais.
 *
 * NOTA (Ponto 8, Fase 2): a fronteira era o `globalThis.fetch`. Com a
 * migração para o cliente Axios deixou de haver `fetch` nenhum na
 * página, e um stub dele já não interceptava nada — o jsdom tentava
 * ligar-se ao `localhost:8001` a sério. A fronteira passou a ser o
 * módulo de transporte, que é onde ela sempre devia ter estado.
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

// O perfil activo muda por teste (quem arquiva anexos depende dele).
const sessao = vi.hoisted(() => ({ papel: "consultor" }));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    token: "t-1",
    user: { id: "u-1", email: "consultor@powercell.pt", name: "Consultor" },
    effectiveRole: sessao.papel,
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

// ── O transporte (Ponto 8, Fase 2) ───────────────────────────────────
// Tudo devolve `{ data: {} }` por omissão; cada teste substitui o que
// precisa. `chamadasDaApi` regista o que foi pedido, para os testes que
// afirmam sobre a chamada e não sobre o ecrã.
const apiFalsa = vi.hoisted(() => ({ chamadas: [] }));

vi.mock("../../services/api", () => {
  const vazio = () => Promise.resolve({ data: {} });
  const registar = (nome) => vi.fn((...args) => {
    apiFalsa.chamadas.push({ nome, args });
    return (apiFalsa[nome] || vazio)(...args);
  });
  return {
    getWebmailStats: registar("getWebmailStats"),
    getWebmailCompanies: registar("getWebmailCompanies"),
    getEmailJobStatus: registar("getEmailJobStatus"),
    getPersonalEmailAccounts: registar("getPersonalEmailAccounts"),
    getEmailLabels: registar("getEmailLabels"),
    getEmailFolders: registar("getEmailFolders"),
    createEmailFolder: registar("createEmailFolder"),
    updateEmailFolder: registar("updateEmailFolder"),
    deleteEmailFolder: registar("deleteEmailFolder"),
    moveEmailsToFolder: registar("moveEmailsToFolder"),
    applyEmailLabels: registar("applyEmailLabels"),
    getWebmailEmail: registar("getWebmailEmail"),
    markEmail: registar("markEmail"),
    deleteEmail: registar("deleteEmail"),
    deleteEmailPermanent: registar("deleteEmailPermanent"),
    associateEmailToProcess: registar("associateEmailToProcess"),
    sendWebmailEmail: registar("sendWebmailEmail"),
    cancelEmailSend: registar("cancelEmailSend"),
    uploadEmailAttachment: registar("uploadEmailAttachment"),
    downloadWebmailAttachment: registar("downloadWebmailAttachment"),
    syncWebmail: registar("syncWebmail"),
    syncWebmailUser: registar("syncWebmailUser"),
    getProcesses: registar("getProcesses"),
    getEmailArchiveSuggestions: registar("getEmailArchiveSuggestions"),
    archiveEmailAttachment: registar("archiveEmailAttachment"),
    getEmailContacts: registar("getEmailContacts"),
    saveEmailContact: registar("saveEmailContact"),
    hideEmailContact: registar("hideEmailContact"),
    readBlobErrorBody: vi.fn(async () => ({})),
  };
});

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

function montar(rota = "/webmail") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[rota]}>
        <WebmailPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const DUAS_EMPRESAS = {
  data: {
    companies: [
      { company_id: "power", company_name: "Power Real Estate", roles: ["consultor"] },
      { company_id: "domus", company_name: "Domus", roles: ["consultor"] },
    ],
  },
};

beforeEach(() => {
  sessao.papel = "consultor";
  estadoDaLista.valor = respostaDaLista([email()]);
  estadoDaLista.ultimosFiltros = null;
  // Qualquer chamada de rede que escape responde vazio em vez de rebentar.
  apiFalsa.chamadas.length = 0;
  for (const chave of Object.keys(apiFalsa)) {
    if (chave !== "chamadas") delete apiFalsa[chave];
  }
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
    apiFalsa.getWebmailEmail = () =>
      Promise.resolve({
        data: { ...email(), body: "Confirmamos a pré-aprovação do crédito." },
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

    apiFalsa.getWebmailEmail = () => Promise.resolve({ data: email() });

    montar();
    await utilizador.click(await screen.findByText("Proposta do banco"));

    await waitFor(() =>
      expect(
        apiFalsa.chamadas.some(
          (c) => c.nome === "markEmail" && c.args[1]?.type === "read",
        ),
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


describe("WebmailPage — separadores por Empresa (Ponto 8, Fase 3)", () => {
  it("desenha um separador por empresa do utilizador", async () => {
    apiFalsa.getWebmailCompanies = () => Promise.resolve(DUAS_EMPRESAS);
    montar();

    expect(
      await screen.findByRole("tab", { name: /Power Real Estate/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Domus/ })).toBeInTheDocument();
  });

  it("a empresa do separador viaja em cada pedido da lista", async () => {
    // É o que torna o isolamento da Fase 1 efectivo: sem o `companyId`
    // nos filtros, o backend caía no caminho legado (header) e o
    // separador não mandava em nada.
    apiFalsa.getWebmailCompanies = () => Promise.resolve(DUAS_EMPRESAS);
    montar("/webmail?company_id=domus");

    await waitFor(() =>
      expect(estadoDaLista.ultimosFiltros?.companyId).toBe("domus"),
    );
  });

  it("trocar de separador muda a empresa dos pedidos", async () => {
    const utilizador = userEvent.setup();
    apiFalsa.getWebmailCompanies = () => Promise.resolve(DUAS_EMPRESAS);
    montar();

    await waitFor(() =>
      expect(estadoDaLista.ultimosFiltros?.companyId).toBe("power"),
    );
    await utilizador.click(screen.getByRole("tab", { name: /Domus/ }));

    await waitFor(() =>
      expect(estadoDaLista.ultimosFiltros?.companyId).toBe("domus"),
    );
  });

  it("uma empresa pedida que já não existe cai na primeira", async () => {
    // Acesso revogado ou link antigo: insistir no id dava 404 no
    // backend e uma caixa vazia sem explicação nenhuma.
    apiFalsa.getWebmailCompanies = () => Promise.resolve(DUAS_EMPRESAS);
    montar("/webmail?company_id=empresa-que-saiu");

    await waitFor(() =>
      expect(estadoDaLista.ultimosFiltros?.companyId).toBe("power"),
    );
  });

  it("com UMA empresa não desenha separador nenhum", async () => {
    apiFalsa.getWebmailCompanies = () =>
      Promise.resolve({
        data: { companies: [DUAS_EMPRESAS.data.companies[0]] },
      });
    montar();

    // Este `findByTestId` só é determinístico porque o rótulo NÃO existe
    // enquanto a lista está vazia (`deveMostrarNomeDaEmpresa`). Enquanto o
    // ramo era o `else` de `length > 1`, o elemento existia logo — vazio —
    // e a asserção seguinte corria contra esse vazio: verde numa máquina
    // rápida, vermelho no CI. Quem garante a regra é
    // `WebmailCompanyTabs.test.jsx`; não voltar a pôr aqui um `waitFor`
    // sobre o texto, que mascara o defeito em vez de o apanhar.
    expect(await screen.findByTestId("webmail-empresa-unica")).toHaveTextContent(
      "Power Real Estate",
    );
    expect(screen.queryAllByRole("tab")).toHaveLength(0);
  });

  it("o indicador de sincronização substitui o painel da barra lateral", async () => {
    apiFalsa.getWebmailCompanies = () => Promise.resolve(DUAS_EMPRESAS);
    montar();

    expect(await screen.findByTestId("webmail-estado-sinc")).toBeInTheDocument();
    // E na barra lateral já não há botão de largura total.
    const barraLateral = screen.getByTestId("webmail-folder-pane");
    expect(
      within(barraLateral).queryByRole("button", { name: /^sincronizar$/i }),
    ).toBeNull();
  });
});

describe("WebmailPage — anexos: descarregar e arquivar no processo (Bloco 2)", () => {
  const ANEXO = { id: "a1", filename: "cc-joana.pdf", size: 4096 };
  const SUGESTAO = {
    process_id: "p-77",
    process_number: 77,
    client_name: "Joana Valente",
    status_label: "Em análise",
    motivo: "endereço do titular",
    ja_indexado: false,
  };

  async function abrirEmailComAnexo(utilizador, anexo = ANEXO) {
    apiFalsa.getWebmailEmail = () =>
      Promise.resolve({ data: { ...email({ attachments: [anexo] }), body: "Segue o CC." } });
    montar();
    await utilizador.click(await screen.findByText("Proposta do banco"));
    return within(screen.getByTestId("webmail-reading-pane"));
  }

  it("«Descarregar» pede o anexo ao servidor e guarda-o sem abrir separador", async () => {
    const utilizador = userEvent.setup();
    apiFalsa.downloadWebmailAttachment = () => Promise.resolve({ data: new Blob(["pdf"]) });
    const abrir = vi.spyOn(window, "open");
    URL.createObjectURL = vi.fn(() => "blob:fake");
    URL.revokeObjectURL = vi.fn();
    const cliques = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    const leitura = await abrirEmailComAnexo(utilizador);
    await utilizador.click(await leitura.findByRole("button", { name: "Descarregar cc-joana.pdf" }));

    await waitFor(() => expect(cliques).toHaveBeenCalled());
    expect(apiFalsa.chamadas.find((c) => c.nome === "downloadWebmailAttachment").args).toEqual([
      "a1",
      { email_id: "e1" },
    ]);
    expect(abrir).not.toHaveBeenCalled();
  });

  it("«Arquivar»: sugere o processo do remetente, arquiva e marca o anexo", async () => {
    const utilizador = userEvent.setup();
    apiFalsa.getEmailArchiveSuggestions = () =>
      Promise.resolve({
        data: { enderecos: ["banco@exemplo.pt"], sugestoes: [SUGESTAO], sugerido: "p-77", ambiguo: false },
      });
    apiFalsa.archiveEmailAttachment = () =>
      Promise.resolve({ data: { success: true, path: "Index/cc.pdf", intake: { fila_ia: true } } });

    const leitura = await abrirEmailComAnexo(utilizador);
    await utilizador.click(await leitura.findByRole("button", { name: "Arquivar cc-joana.pdf no processo" }));

    const radio = await screen.findByRole("radio", { name: /#77 · Joana Valente/ });
    expect(radio).toBeChecked();
    await utilizador.click(screen.getByTestId("arquivar-confirmar"));

    await waitFor(() =>
      expect(apiFalsa.chamadas.find((c) => c.nome === "archiveEmailAttachment").args).toEqual([
        "e1",
        "a1",
        { process_id: "p-77", category: "Outros" },
      ]),
    );
    expect(await leitura.findByText("Arquivado")).toBeInTheDocument();
    expect(screen.queryByTestId("arquivar-dialogo")).not.toBeInTheDocument();
  });

  it.each(["parceiro"])(
    "o perfil %s não vê o botão «Arquivar» (mas pode descarregar)",
    async (papel) => {
      sessao.papel = papel;
      const utilizador = userEvent.setup();
      const leitura = await abrirEmailComAnexo(utilizador);

      expect(await leitura.findByRole("button", { name: "Descarregar cc-joana.pdf" })).toBeInTheDocument();
      expect(leitura.queryByRole("button", { name: /Arquivar cc-joana.pdf/ })).not.toBeInTheDocument();
    },
  );

  it.each(["administrativo", "diretor", "indexacao"])("o perfil %s arquiva", async (papel) => {
    sessao.papel = papel;
    const utilizador = userEvent.setup();
    const leitura = await abrirEmailComAnexo(utilizador);
    expect(await leitura.findByRole("button", { name: "Arquivar cc-joana.pdf no processo" })).toBeInTheDocument();
  });
});

describe("WebmailPage — abrir um rascunho a partir do Dashboard (Bloco 4, ponto 32)", () => {
  /**
   * Os rascunhos automáticos («documento em falta») pertencem a um PROCESSO,
   * não à caixa pessoal: a pasta Rascunhos nunca os traz. O link do
   * Dashboard (`/webmail?folder=drafts&id=…`) abria o Webmail e não abria
   * nada, porque o rascunho não estava na lista carregada.
   */
  const RASCUNHO_AUTOMATICO = {
    id: "auto-1", status: "draft", is_auto_draft: true, process_id: "p-1",
    subject: "Documento necessário: IRS", to_emails: ["cliente@exemplo.pt"],
    body: "Caro Silva, precisamos do IRS.",
  };

  it("um rascunho que não está na lista é pedido pelo id e abre o editor", async () => {
    apiFalsa.getWebmailEmail = () => Promise.resolve({ data: RASCUNHO_AUTOMATICO });
    montar("/webmail?folder=drafts&id=auto-1");

    const assunto = await screen.findByPlaceholderText("Assunto do email");
    expect(assunto).toHaveValue("Documento necessário: IRS");
    expect(screen.getByDisplayValue(/Caro Silva/)).toBeInTheDocument();
    expect(apiFalsa.chamadas.filter((c) => c.nome === "getWebmailEmail")).toHaveLength(1);
  });

  it("um rascunho que ESTÁ na lista abre sem pedir nada ao servidor", async () => {
    estadoDaLista.valor = respostaDaLista([email({ id: "auto-1", status: "draft", subject: "Já na lista" })]);
    montar("/webmail?folder=drafts&id=auto-1");

    expect(await screen.findByDisplayValue("Já na lista")).toBeInTheDocument();
    expect(apiFalsa.chamadas.filter((c) => c.nome === "getWebmailEmail")).toHaveLength(0);
  });

  it("não pede o email enquanto a lista ainda não carregou (podia estar nela)", async () => {
    estadoDaLista.valor = { ...respostaDaLista([]), isFetched: false, isLoading: true };
    montar("/webmail?folder=drafts&id=auto-1");

    await screen.findByTestId("webmail-list-pane");
    expect(apiFalsa.chamadas.filter((c) => c.nome === "getWebmailEmail")).toHaveLength(0);
  });

  it("se o servidor recusar, diz-o e não deixa o editor aberto", async () => {
    apiFalsa.getWebmailEmail = () => Promise.reject(new Error("404"));
    montar("/webmail?folder=drafts&id=auto-1");

    await waitFor(() =>
      expect(apiFalsa.chamadas.filter((c) => c.nome === "getWebmailEmail")).toHaveLength(1),
    );
    expect(screen.queryByPlaceholderText("Assunto do email")).not.toBeInTheDocument();
  });

  it("um email que não é rascunho abre para leitura, não no editor", async () => {
    apiFalsa.getWebmailEmail = () => Promise.resolve({
      data: { ...RASCUNHO_AUTOMATICO, status: "sent", subject: "Já enviado" },
    });
    montar("/webmail?id=auto-1");

    await waitFor(() =>
      expect(apiFalsa.chamadas.filter((c) => c.nome === "getWebmailEmail").length).toBeGreaterThan(0),
    );
    expect(screen.queryByPlaceholderText("Assunto do email")).not.toBeInTheDocument();
  });
});
