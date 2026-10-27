/**
 * A Listagem de Processos MONTADA (D-20).
 *
 * Esta página de 1236 linhas nunca tinha sido montada num teste. É a regra
 * do `WebmailPage`, da `UsersAccessAdminTab` e da Pool outra vez: nem o
 * eslint, nem o build, nem os testes de componente apanham um `const` na
 * zona morta temporal, porque nada avalia o render. No Lote 6 escrevi
 * exactamente esse defeito na Pool (`canAssign` acima de `papelActivo`) e
 * só não foi para produção porque a Pool TEM teste montado. Esta página e
 * o Kanban não tinham — e foi isso que ficou registado como D-20.
 *
 * Daí o primeiro teste ser o mais estúpido possível: montar e sobreviver.
 *
 * A FORMA DOS DADOS É A REAL, lida no backend antes de escrever isto:
 * `GET /processes` devolve `{items, total, page, size, pages, view_mode}`
 * (`build_process_list_response`) e cada linha traz os campos de
 * `PROCESS_LIST_PROJECTION` (`services/process_service.py`), incluindo
 * `under_35` calculado ao servir e `latest_note*` do ponto único das
 * notas. Um mock com a forma inventada é pior do que nenhum — é a
 * armadilha do `/portal/status` e do `{config, fields}` dos SLAs.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children, title }) => (
    <div data-testid="layout" data-title={title}>{children}</div>
  ),
}));

vi.mock("../../components/CreateProcessModal", () => ({
  default: ({ isOpen }) => (isOpen ? <div data-testid="modal-criar" /> : null),
}));
vi.mock("../../components/ClientDetailsModal", () => ({
  default: ({ open }) => (open ? <div data-testid="modal-cliente" /> : null),
}));

const navegar = vi.fn();
let caminho = "/lista-processos";
let parametros = new URLSearchParams();
const definirParametros = vi.fn();
vi.mock("react-router-dom", () => ({
  useNavigate: () => navegar,
  useLocation: () => ({ pathname: caminho, search: "" }),
  useSearchParams: () => [parametros, definirParametros],
}));

let papelActivo = "diretor";
let capacidadesPorPapel = null;
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: {
      id: "u1",
      name: "Quem Lista",
      role: "consultor",
      ...(capacidadesPorPapel
        ? { capabilities_por_papel: capacidadesPorPapel }
        : {}),
    },
    token: "t",
    // O papel do PERFIL ACTIVO difere do papel base de propósito: é o caso
    // que um gate por `user.role` decide mal (forma do `_is_stealth_user`).
    effectiveRole: papelActivo,
    activeRole: papelActivo,
    activeCompanyId: "empresa-1",
    effectiveCompanyId: "empresa-1",
  }),
}));

vi.mock("../../hooks/queries/useProcessQuery", () => ({
  useWorkflowStatusesQuery: () => ({
    data: [
      { name: "pre_registo", label: "Pré-Registo", order: 0, color: "#888" },
      { name: "analise", label: "Análise", order: 1, color: "#888" },
    ],
    isLoading: false,
  }),
}));

vi.mock("../../services/api", () => ({
  getProcesses: vi.fn(),
  getMyProcesses: vi.fn(),
  markProcessIndexed: vi.fn(),
  restoreProcess: vi.fn(),
  getProcessLabels: vi.fn(),
  updateProcess: vi.fn(),
  markProcessFinancesPaid: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

import ProcessesPage from "../ProcessesPage";
import * as api from "../../services/api";
import { toast } from "sonner";

/**
 * A página tem de ser montada DENTRO de um `QueryClientProvider`: o
 * `ProcessFilters` usa `useAssignmentUsersQuery`. Em produção o provider
 * vem do `App`; num teste sem ele a página rebenta com "No QueryClient
 * set" — e foi assim que este teste começou, o que já prova o que ele
 * veio provar (um componente novo com um `useQuery` só se descobre quando
 * a PÁGINA é montada).
 */
function montar() {
  const clienteDeQueries = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={clienteDeQueries}>
      <ProcessesPage />
    </QueryClientProvider>,
  );
}

/**
 * Duas linhas com a forma que `PROCESS_LIST_PROJECTION` + os
 * enriquecimentos produzem. Os valores são deliberadamente DIFERENTES das
 * omissões da página (a lição do fixture dos SLAs): com valores iguais aos
 * defaults, um erro de leitura é indistinguível de uma leitura correcta.
 */
const LINHAS = [
  {
    id: "p1",
    client_id: "c1",
    process_number: "PROC-0101",
    client_name: "Ana Martins",
    client_email: "ana@exemplo.pt",
    client_phone: "910000001",
    status: "analise",
    priority: "alta",
    process_type: "credito_habitacao",
    property_value: 250000,
    property_location: "Porto",
    is_indexed: true,
    indexed_at: "2026-09-01T10:00:00Z",
    assigned_consultor_ids: ["u1"],
    consultor_name: "Quem Lista",
    created_at: "2026-09-01T10:00:00Z",
    updated_at: "2026-09-20T10:00:00Z",
    labels: ["urgente"],
    notes: "Nota antiga",
    observation_notes: [
      { text: "Aguarda avaliação do banco", created_at: "2026-09-20T09:00:00Z" },
    ],
    under_35: true,
    // D-25 — os campos que o servidor CALCULA ao servir
    // (`process_sharing.aplicar_flag_a_processos`). Valores reais, não
    // inventados: `is_partilhado` + `partilha_com` com o NOME da
    // empresa, mais o registo cru de onde derivam.
    is_partilhado: true,
    partilha_com: ["Precision Crédito"],
    partner_companies: [
      {
        company_id: "cmp-precision",
        company_name: "Precision Crédito",
        network_id: "grupo_power_precision",
      },
    ],
  },
  {
    id: "p2",
    client_id: "c2",
    process_number: "PROC-0102",
    client_name: "Rui Pereira",
    client_email: "rui@exemplo.pt",
    client_phone: "910000002",
    status: "pre_registo",
    priority: "normal",
    process_type: "credito_habitacao",
    is_indexed: false,
    assigned_consultor_ids: [],
    created_at: "2026-09-02T10:00:00Z",
    updated_at: "2026-09-02T10:00:00Z",
    labels: [],
    under_35: false,
  },
];

const RESPOSTA = {
  data: {
    items: LINHAS,
    total: 2,
    page: 1,
    size: 20,
    pages: 1,
    view_mode: "active_only",
  },
};

beforeEach(() => {
  vi.clearAllMocks();
  caminho = "/lista-processos";
  parametros = new URLSearchParams();
  papelActivo = "diretor";
  capacidadesPorPapel = null;
  api.getProcesses.mockResolvedValue(RESPOSTA);
  api.getMyProcesses.mockResolvedValue(RESPOSTA);
  api.getProcessLabels.mockResolvedValue({ data: { labels: ["urgente"] } });
});

describe("ProcessesPage — montar e sobreviver", () => {
  it("monta sem rebentar e mostra as linhas servidas", async () => {
    montar();
    expect(await screen.findByText("Ana Martins")).toBeInTheDocument();
    expect(screen.getByText("Rui Pereira")).toBeInTheDocument();
  });

  it("não deixa nenhum erro no render escapar para a consola", async () => {
    // Um `console.error` do React é a assinatura de um aviso de chave, de
    // um hook condicional ou de uma prop inválida — coisas que passam no
    // build e aparecem no browser do utilizador.
    const espia = vi.spyOn(console, "error").mockImplementation(() => {});
    montar();
    await screen.findByText("Ana Martins");
    expect(espia).not.toHaveBeenCalled();
    espia.mockRestore();
  });

  it("pede a listagem GLOBAL em /lista-processos e a MINHA em /processos", async () => {
    montar();
    await waitFor(() => expect(api.getProcesses).toHaveBeenCalled());
    expect(api.getMyProcesses).not.toHaveBeenCalled();
  });

  it("em /processos usa getMyProcesses", async () => {
    caminho = "/processos";
    montar();
    await waitFor(() => expect(api.getMyProcesses).toHaveBeenCalled());
    expect(api.getProcesses).not.toHaveBeenCalled();
  });

  it("o cabeçalho e o rodapé anunciam o MESMO total do servidor", async () => {
    // A página escreve o total em dois sítios (resumo da paginação e
    // cabeçalho do cartão). Confundir `items.length` com `total` faz um
    // contradizer o outro a partir da segunda página — é o defeito do
    // `total` na eliminação optimista de utilizadores, noutro ecrã. Por
    // isso a asserção é sobre a CONCORDÂNCIA, não sobre uma ocorrência.
    api.getProcesses.mockResolvedValue({
      data: { ...RESPOSTA.data, total: 137, pages: 7 },
    });
    montar();
    await screen.findByText("Ana Martins");
    const sitios = screen.getAllByText(/137 processos/);
    expect(sitios.length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText(/de 2 processos/)).not.toBeInTheDocument();
  });
});

describe("ProcessesPage — a forma dos dados reais", () => {
  it("sobrevive a uma resposta sem envelope de paginação", async () => {
    // Há caminhos que devolvem a lista crua (`response.data` sem `items`).
    api.getProcesses.mockResolvedValue({ data: LINHAS });
    montar();
    expect(await screen.findByText("Ana Martins")).toBeInTheDocument();
  });

  it("sobrevive a uma lista vazia sem rebentar", async () => {
    api.getProcesses.mockResolvedValue({
      data: { items: [], total: 0, page: 1, size: 20, pages: 0 },
    });
    montar();
    await waitFor(() => expect(api.getProcesses).toHaveBeenCalled());
    expect(screen.queryByText("Ana Martins")).not.toBeInTheDocument();
  });

  it("sobrevive a campos em falta nas linhas", async () => {
    // Um processo legado não tem `labels`, nem `under_35`, nem
    // `observation_notes`. Uma cascata de `||` sobre campos ausentes é a
    // forma como a coluna "Notas do Consultor" ficou vazia em TODOS os
    // processos sem ninguém dar por isso.
    api.getProcesses.mockResolvedValue({
      data: {
        items: [{ id: "p9", client_name: "Legado Sem Campos", status: "analise" }],
        total: 1, page: 1, size: 20, pages: 1,
      },
    });
    montar();
    expect(await screen.findByText("Legado Sem Campos")).toBeInTheDocument();
  });

  it("sobrevive a um erro do servidor sem ecrã em branco", async () => {
    api.getProcesses.mockRejectedValue({
      response: { status: 500, data: { detail: "boom" } },
    });
    montar();
    await waitFor(() => expect(api.getProcesses).toHaveBeenCalled());
    expect(screen.getByTestId("layout")).toBeInTheDocument();
  });
});

describe("ProcessesPage — os botões fantasma (ligação do Lote 6)", () => {
  it("um perfil sem a capacidade de criar não vê o botão activo", async () => {
    // (o Index tem a sua própria tabela — `OsMeusProcessosDoIndex.test.jsx` — e PODE criar processos)
    papelActivo = "administrativo";
    capacidadesPorPapel = { administrativo: { PROCESS_CREATE: false } };
    montar();
    await screen.findByText("Ana Martins");
    const botao = screen.queryByRole("button", { name: /novo processo/i });
    // Cadeado visível (modo por omissão) ou ausente — nunca activo.
    expect(botao === null || botao.disabled).toBe(true);
  });

  it("o diretor vê o botão de criar utilizável", async () => {
    // Contraprova: sem ela, esconder o botão a todos passava o teste acima.
    papelActivo = "diretor";
    capacidadesPorPapel = { diretor: { PROCESS_CREATE: true } };
    montar();
    await screen.findByText("Ana Martins");
    const botao = screen.getByRole("button", { name: /novo processo/i });
    expect(botao).toBeEnabled();
  });

  it("sem contrato de capacidades o botão continua utilizável", async () => {
    // Falha ABERTA de propósito: uma sessão anterior ao deploy não tem o
    // mapa, e esconder tudo a todos não produz erro nenhum — parece
    // apenas um ecrã estragado. A parede é o servidor.
    papelActivo = "consultor";
    capacidadesPorPapel = null;
    montar();
    await screen.findByText("Ana Martins");
    expect(
      screen.getByRole("button", { name: /novo processo/i }),
    ).toBeEnabled();
  });
});

describe("ProcessesPage — interacção", () => {
  it("clicar numa linha navega para os detalhes do processo", async () => {
    const utilizador = userEvent.setup();
    montar();
    const celula = await screen.findByText("Ana Martins");
    await utilizador.click(celula);
    await waitFor(() => {
      const navegou = navegar.mock.calls.some(
        ([destino]) => typeof destino === "string" && destino.includes("p1"),
      );
      const abriuModal = screen.queryByTestId("modal-cliente") !== null;
      expect(navegou || abriuModal).toBe(true);
    });
  });

  it("o Index NÃO usa esta tabela: tem a sua (colunas de triagem)", async () => {
    papelActivo = "indexacao";
    caminho = "/processos";
    montar();
    // a tabela de acompanhamento de negócios não se desenha para o Index
    await waitFor(() => expect(screen.queryByText("Notas do Consultor")).not.toBeInTheDocument());
    expect(api.getMyProcesses).not.toHaveBeenCalled();
    expect(api.getProcesses).not.toHaveBeenCalled();
  });

  it("«Todos os Processos» é a Visão Global da rede também para o Index (Out 2026)", async () => {
    // O Index caía na sua lista de atribuídos nos dois endereços e não via o resto da rede.
    papelActivo = "indexacao";
    caminho = "/lista-processos";
    montar();
    await waitFor(() => expect(api.getProcesses).toHaveBeenCalled());
    expect(api.getProcesses.mock.calls[0][0]).toMatchObject({ show_all: true });
    expect(api.getMyProcesses).not.toHaveBeenCalled();
  });

  it("o Index não marca como indexado o processo de outro indexador (Out 2026)", async () => {
    // Sem acções cruzadas: na Visão Global a prancheta fica desligada no processo de um colega; no
    // que não tem indexador (ou é seu) continua activa. O servidor recusa na mesma (403).
    papelActivo = "indexacao";
    caminho = "/lista-processos";
    api.getProcesses.mockResolvedValue({
      data: {
        ...RESPOSTA.data,
        items: [
          { ...LINHAS[1], id: "p-colega", client_name: "Do Colega", assigned_indexacao_id: "u-rui" },
          { ...LINHAS[1], id: "p-livre", client_name: "Sem Ninguém", assigned_indexacao_id: null },
          { ...LINHAS[1], id: "p-meu", client_name: "Do Próprio", assigned_indexacao_id: "u1" },
        ],
      },
    });
    montar();
    await screen.findByText("Do Colega");
    expect(screen.getByTestId("marcar-indexado-p-colega")).toBeDisabled();
    expect(screen.getByTestId("marcar-indexado-p-colega")).toHaveAttribute("title", expect.stringMatching(/Atribuir a mim/));
    expect(screen.getByTestId("marcar-indexado-p-livre")).toBeEnabled();
    expect(screen.getByTestId("marcar-indexado-p-meu")).toBeEnabled();
  });

  it("o Index abre o processo de um colega na vista normal de detalhes; o seu continua na bancada", async () => {
    papelActivo = "indexacao";
    caminho = "/lista-processos";
    api.getProcesses.mockResolvedValue({
      data: {
        ...RESPOSTA.data,
        items: [
          { ...LINHAS[1], id: "p-colega", client_name: "Do Colega", assigned_indexacao_id: "u-rui" },
          { ...LINHAS[1], id: "p-meu", client_name: "Do Próprio", assigned_indexacao_id: "u1" },
        ],
      },
    });
    const utilizador = userEvent.setup();
    montar();
    await utilizador.click((await screen.findByText("Do Colega")).closest("tr"));
    await waitFor(() => expect(navegar).toHaveBeenCalled());
    expect(navegar.mock.calls[0][0]).toBe("/process/p-colega");
    navegar.mockClear();
    await utilizador.click(screen.getByText("Do Próprio").closest("tr"));
    await waitFor(() => expect(navegar).toHaveBeenCalled());
    expect(navegar.mock.calls[0][0]).toBe("/index/p-meu");
  });

  it("contraprova: a gestão marca o processo de qualquer indexador", async () => {
    papelActivo = "admin";
    caminho = "/lista-processos";
    api.getProcesses.mockResolvedValue({
      data: { ...RESPOSTA.data, items: [{ ...LINHAS[1], id: "p-colega", client_name: "Do Colega", assigned_indexacao_id: "u-rui" }] },
    });
    montar();
    await screen.findByText("Do Colega");
    expect(screen.getByTestId("marcar-indexado-p-colega")).toBeEnabled();
  });

  it("contraprova: os outros perfis continuam a abrir o detalhe do processo", async () => {
    papelActivo = "consultor";
    caminho = "/processos";
    const utilizador = userEvent.setup();
    montar();
    const linha = (await screen.findByText("Ana Martins")).closest("tr");
    await utilizador.click(linha);
    await waitFor(() => expect(navegar).toHaveBeenCalled());
    expect(navegar.mock.calls[0][0]).toBe("/process/p1");
    expect(navegar.mock.calls[0][1]).toHaveProperty("state.contextoDeNavegacao");
    expect(navegar.mock.calls.some(([d]) => String(d).startsWith("/index/"))).toBe(false);
  });

  it("escrever na pesquisa não rebenta a página", async () => {
    const utilizador = userEvent.setup();
    montar();
    await screen.findByText("Ana Martins");
    const campos = screen.getAllByPlaceholderText(/pesquisar/i);
    await utilizador.type(campos[0], "Ana");
    expect(campos[0]).toHaveValue("Ana");
  });
});


describe("ProcessesPage — a partilha (D-25)", () => {
  it("mostra a etiqueta [Partilha: …] na linha partilhada", async () => {
    // A partilha é Via Rápida: abre-se uma fronteira sem aprovação, e
    // esta etiqueta é a única coisa que a torna visível. A `Sub35Badge`
    // ensinou a forma de defeito — a etiqueta existia em três cópias e
    // nunca apareceu, porque o campo que liam não era escrito por
    // ninguém no servidor. Aqui o fixture usa o campo REAL.
    montar();
    await screen.findByText("Ana Martins");

    const etiquetas = screen.getAllByTestId("etiqueta-partilha");
    expect(etiquetas).toHaveLength(1);
    expect(etiquetas[0]).toHaveTextContent("Partilha: Precision Crédito");
  });

  it("e NÃO a mostra na linha exclusiva da casa", async () => {
    // A contraprova: sem ela, uma etiqueta sempre visível passava o
    // teste de cima e mentia em todas as outras linhas.
    montar();
    await screen.findByText("Rui Pereira");

    expect(screen.getAllByTestId("etiqueta-partilha")).toHaveLength(1);
  });

  it("o filtro rápido está no topo, com os dois valores", async () => {
    montar();
    await screen.findByText("Ana Martins");

    const grupo = screen.getByTestId("process-partilha-filter");
    expect(grupo).toBeInTheDocument();
    expect(
      screen.getByRole("radio", { name: /exclusivos da casa/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("radio", { name: /^partilhados$/i }),
    ).toBeInTheDocument();
  });

  it("clicar em «Partilhados» escreve o filtro no URL", async () => {
    // O filtro vive no URL como os outros: um link já filtrado é metade
    // da utilidade da segmentação. E é o `setSearchParams` que o teste
    // observa, porque é ele que dispara o pedido novo.
    const utilizador = userEvent.setup();
    montar();
    await screen.findByText("Ana Martins");

    definirParametros.mockClear();
    await utilizador.click(screen.getByRole("radio", { name: /^partilhados$/i }));

    await waitFor(() => {
      expect(definirParametros).toHaveBeenCalled();
    });
    // O `setSearchParams` recebe um updater: corre-se com os parâmetros
    // actuais para ver o que ele escreveria.
    const [updater] = definirParametros.mock.calls.at(-1);
    const resultado = updater(new URLSearchParams());
    expect(resultado.get("partilha")).toBe("partilhados");
  });
});


// ====================================================================
// «Marcar como Pago» — o atalho de quem fecha as contas (excepção ao D-34)
// ====================================================================
describe("ProcessesPage — «Marcar como Pago» num processo fechado", () => {
  // Forma que `enriquecer_comissoes_pendentes` acrescenta (calculada ao servir).
  const FECHADA_COM_COMISSOES = {
    ...LINHAS[1],
    id: "p-fechado",
    process_number: "PROC-0999",
    client_name: "Carla Fechada",
    status: "concluido",
    is_indexed: true,
    processo_fechado: true,
    comissoes_pendentes: 2,
  };

  function servir(...linhas) {
    api.getProcesses.mockResolvedValue({
      data: { items: linhas, total: linhas.length, page: 1, size: 20, pages: 1, view_mode: "active_only" },
    });
  }

  it("mostra o botão numa linha fechada com comissões por pagar", async () => {
    servir(FECHADA_COM_COMISSOES);
    montar();
    expect(await screen.findByTestId("marcar-pago-p-fechado")).toBeInTheDocument();
  });

  it.each([
    ["aberta, mesmo com comissões", { processo_fechado: false, comissoes_pendentes: 2 }],
    ["fechada mas sem nada por pagar", { processo_fechado: true, comissoes_pendentes: 0 }],
    ["sem as chaves (perfil que não paga)", { processo_fechado: undefined, comissoes_pendentes: undefined }],
  ])("não mostra o botão numa linha %s", async (_nome, chaves) => {
    servir({ ...FECHADA_COM_COMISSOES, ...chaves });
    montar();
    await screen.findByText("Carla Fechada");
    expect(screen.queryByTestId("marcar-pago-p-fechado")).toBeNull();
  });

  it("confirma, paga sem reabrir e tira o botão da linha", async () => {
    servir(FECHADA_COM_COMISSOES);
    api.markProcessFinancesPaid.mockResolvedValue({ data: { process_id: "p-fechado", updated: 2 } });
    montar();

    await userEvent.click(await screen.findByTestId("marcar-pago-p-fechado"));
    const dialogo = await screen.findByTestId("marcar-pago-dialogo");
    expect(dialogo).toHaveTextContent(/2 comissões/);
    expect(dialogo).toHaveTextContent(/PROC-0999/);
    expect(api.markProcessFinancesPaid).not.toHaveBeenCalled();

    await userEvent.click(screen.getByTestId("marcar-pago-confirmar"));

    await waitFor(() => expect(api.markProcessFinancesPaid).toHaveBeenCalledWith("p-fechado"));
    await waitFor(() => expect(screen.queryByTestId("marcar-pago-p-fechado")).toBeNull());
    expect(toast.success).toHaveBeenCalled();
    // NÃO reabre o processo, nem o move de fase.
    expect(api.updateProcess).not.toHaveBeenCalled();
  });

  it("cancelar não paga nada", async () => {
    servir(FECHADA_COM_COMISSOES);
    montar();
    await userEvent.click(await screen.findByTestId("marcar-pago-p-fechado"));
    await userEvent.click(await screen.findByRole("button", { name: /cancelar/i }));

    expect(api.markProcessFinancesPaid).not.toHaveBeenCalled();
    expect(screen.getByTestId("marcar-pago-p-fechado")).toBeInTheDocument();
  });

  it("se o servidor recusar, o botão fica e o erro diz-se", async () => {
    servir(FECHADA_COM_COMISSOES);
    api.markProcessFinancesPaid.mockRejectedValue({
      response: { data: { detail: "Sem permissão para alterar o estado financeiro." } },
    });
    montar();

    await userEvent.click(await screen.findByTestId("marcar-pago-p-fechado"));
    await userEvent.click(await screen.findByTestId("marcar-pago-confirmar"));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(
      expect.stringMatching(/sem permissão/i),
    ));
    expect(screen.getByTestId("marcar-pago-p-fechado")).toBeInTheDocument();
  });

  it("o botão da linha não abre o processo (clicar nele não navega)", async () => {
    servir(FECHADA_COM_COMISSOES);
    montar();
    await userEvent.click(await screen.findByTestId("marcar-pago-p-fechado"));
    expect(navegar).not.toHaveBeenCalled();
  });
});
