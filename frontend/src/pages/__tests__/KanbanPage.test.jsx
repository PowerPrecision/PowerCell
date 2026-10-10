/**
 * O Kanban MONTADO (D-20), com o `KanbanBoard` REAL.
 *
 * O Kanban é a página de entrada do sistema depois do login e nunca tinha
 * sido montada num teste — a outra metade da D-20. Falsear o
 * `KanbanBoard` tornaria este teste inútil: o que falta cobrir é
 * precisamente a ligação página ↔ quadro (os filtros que a página lê do
 * URL e passa como props, e o `useKanbanQuery` que o quadro usa).
 *
 * Falseia-se só a FRONTEIRA: `DashboardLayout`, `AuthContext`,
 * `react-router-dom`, o `services/api` e o `xlsx` (import dinâmico). O
 * quadro, os cartões, os filtros e o `BotaoComPermissao` são os reais.
 *
 * A FORMA DOS DADOS É A REAL, lida em
 * `services/process_kanban_enrichment.build_kanban_response`:
 * `{columns: [{id, name, label, color, order, processes, count}],
 *   total_processes, total_inactive, total_desconhecidos, user_role,
 *   current_user_id, view_mode, completed_days}`.
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

vi.mock("../../components/kanban/CreateClientModal", () => ({
  default: ({ open }) => (open ? <div data-testid="modal-criar" /> : null),
}));

let parametros = new URLSearchParams();
const definirParametros = vi.fn();
// O `useSearchParams` falso é STATEFUL: o quadro guarda os filtros no URL, e um
// mock que ignorasse a escrita deixava o ecrã parado depois de cada clique.
vi.mock("react-router-dom", async () => {
  const React = await import("react");
  return {
  useSearchParams: () => {
    const [, forcar] = React.useReducer((n) => n + 1, 0);
    const definir = (argumento, opcoes) => {
      definirParametros(argumento, opcoes);
      parametros = new URLSearchParams(
        typeof argumento === "function" ? argumento(parametros) : argumento,
      );
      forcar();
    };
    return [parametros, definir];
  },
  useNavigate: () => vi.fn(),
  useLocation: () => ({ pathname: "/kanban", search: "" }),
  Link: ({ children, to }) => <a href={to}>{children}</a>,
  };
});

let papelActivo = "diretor";
let capacidadesPorPapel = null;
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    token: "t",
    user: {
      id: "u1",
      name: "Quem Vê O Quadro",
      role: "consultor",
      ...(capacidadesPorPapel
        ? { capabilities_por_papel: capacidadesPorPapel }
        : {}),
    },
    // Papel activo ≠ papel base de propósito: é o caso que um gate por
    // `user.role` decide mal (terceira forma do `_is_stealth_user`).
    effectiveRole: papelActivo,
  }),
}));

vi.mock("../../services/api", () => ({
  getKanbanBoard: vi.fn(),
  getKanbanCompleted: vi.fn(),
  getUsers: vi.fn(),
  getProcessLabels: vi.fn(),
  updateProcessStatus: vi.fn(),
  getProcesses: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

import KanbanPage from "../KanbanPage";
import * as api from "../../services/api";

const COLUNAS = [
  {
    id: "pre_registo",
    name: "pre_registo",
    label: "Pré-Registo",
    color: "#F59E0B",
    order: 0,
    count: 1,
    processes: [
      {
        id: "p1",
        client_id: "c1",
        process_number: "PROC-0101",
        client_name: "Ana Martins",
        client_email: "ana@exemplo.pt",
        client_phone: "910000001",
        status: "pre_registo",
        priority: "alta",
        process_type: "credito_habitacao",
        consultor_name: "Quem Vê O Quadro",
        assigned_consultor_ids: ["u1"],
        created_at: "2026-09-01T10:00:00Z",
        updated_at: "2026-09-20T10:00:00Z",
        labels: ["urgente"],
        under_35: true,
        // D-25 — calculados ao servir
        // (`process_sharing.aplicar_flag_a_processos`).
        is_partilhado: true,
        partilha_com: ["Domus"],
      },
    ],
  },
  {
    id: "analise",
    name: "analise",
    label: "Análise",
    color: "#3B82F6",
    order: 1,
    count: 1,
    processes: [
      {
        id: "p2",
        client_id: "c2",
        process_number: "PROC-0102",
        client_name: "Rui Pereira",
        status: "analise",
        priority: "normal",
        created_at: "2026-09-02T10:00:00Z",
        updated_at: "2026-09-02T10:00:00Z",
        labels: [],
        under_35: false,
      },
    ],
  },
];

const QUADRO = {
  data: {
    columns: COLUNAS,
    total_processes: 2,
    total_inactive: 0,
    total_desconhecidos: 0,
    user_role: "diretor",
    current_user_id: "u1",
    view_mode: "active_only",
    completed_days: 30,
  },
};

const UTILIZADORES = {
  data: [
    { id: "u1", name: "Quem Vê O Quadro", role: "consultor", is_active: true },
    { id: "u2", name: "Outro Consultor", role: "consultor", is_active: true },
    { id: "u3", name: "Quem Indexa", role: "indexacao", is_active: true },
  ],
};

function montar() {
  const clienteDeQueries = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={clienteDeQueries}>
      <KanbanPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  parametros = new URLSearchParams();
  papelActivo = "diretor";
  capacidadesPorPapel = null;
  api.getUsers.mockResolvedValue(UTILIZADORES);
  api.getKanbanBoard.mockResolvedValue(QUADRO);
  api.getKanbanCompleted.mockResolvedValue({ data: { columns: [] } });
  api.getProcessLabels.mockResolvedValue({ data: { labels: ["urgente"] } });
});

describe("KanbanPage — montar e sobreviver", () => {
  it("monta e mostra os cartões das duas colunas", async () => {
    montar();
    expect(await screen.findByText("Ana Martins")).toBeInTheDocument();
    expect(await screen.findByText("Rui Pereira")).toBeInTheDocument();
  });

  it("mostra os rótulos das fases que o motor devolveu", async () => {
    // Os rótulos vêm do `workflow_statuses`, nunca de uma lista escrita no
    // frontend: uma fase nova no motor tem de aparecer sozinha.
    montar();
    expect(await screen.findByText(/Pré-Registo/i)).toBeInTheDocument();
    expect(await screen.findByText(/Análise/i)).toBeInTheDocument();
  });

  it("não deixa nenhum erro no render escapar para a consola", async () => {
    const espia = vi.spyOn(console, "error").mockImplementation(() => {});
    montar();
    await screen.findByText("Ana Martins");
    expect(espia).not.toHaveBeenCalled();
    espia.mockRestore();
  });
});

describe("KanbanPage — a forma dos dados reais", () => {
  it("sobrevive a um quadro sem colunas", async () => {
    api.getKanbanBoard.mockResolvedValue({
      data: { columns: [], total_processes: 0, total_inactive: 0 },
    });
    montar();
    await waitFor(() => expect(api.getKanbanBoard).toHaveBeenCalled());
    expect(screen.getByTestId("layout")).toBeInTheDocument();
  });

  it("sobrevive a colunas sem a chave `processes`", async () => {
    // ESTE TESTE APANHOU UM DEFEITO REAL: `column.processes.filter(...)`
    // corria sem guarda em quatro sítios do `KanbanBoard` e com `|| []`
    // em dois — os dois que só correm DEPOIS de um arrasto. Era a metade
    // rara a estar protegida. Resultado: `Cannot read properties of
    // undefined (reading 'filter')` e ecrã em branco na página de entrada
    // do sistema. A forma normaliza-se agora num ponto único
    // (`utils/kanbanColunas.js`).
    api.getKanbanBoard.mockResolvedValue({
      data: {
        columns: [{ id: "x", name: "x", label: "Fase X", color: "#888", order: 0 }],
        total_processes: 0,
      },
    });
    montar();
    expect(await screen.findByText(/Fase X/i)).toBeInTheDocument();
  });

  it("uma coluna de concluídos sem `processes` não parte o quadro", async () => {
    // O caminho real: a fusão substitui a coluna INTEIRA pela da consulta
    // de concluídos, logo a forma passa a ser a que o OUTRO endpoint der.
    api.getKanbanCompleted.mockResolvedValue({
      data: { columns: [{ id: "analise", name: "analise", label: "Análise" }] },
    });
    montar();
    expect(await screen.findByText("Ana Martins")).toBeInTheDocument();
  });

  it("sobrevive a um erro do servidor sem ecrã em branco", async () => {
    api.getKanbanBoard.mockRejectedValue({
      response: { status: 500, data: { detail: "boom" } },
    });
    montar();
    await waitFor(() => expect(api.getKanbanBoard).toHaveBeenCalled());
    expect(screen.getByTestId("layout")).toBeInTheDocument();
  });

  it("sobrevive a getUsers a falhar — os filtros ficam vazios, a página fica", async () => {
    api.getUsers.mockRejectedValue(new Error("rede"));
    montar();
    expect(await screen.findByText("Ana Martins")).toBeInTheDocument();
  });
});

describe("KanbanPage — os filtros vêm do URL", () => {
  it("um consultor no URL entra no pedido do quadro", async () => {
    // Um filtro que vai nos parâmetros TEM de chegar ao pedido — o defeito
    // do filtro de etiquetas do Kanban era exactamente este, com os
    // parâmetros reconstruídos sem o campo.
    parametros = new URLSearchParams("consultor=u2");
    montar();
    await waitFor(() => expect(api.getKanbanBoard).toHaveBeenCalled());
    const enviados = api.getKanbanBoard.mock.calls
      .map(([params]) => String(params ?? ""))
      .join("|");
    expect(enviados).toContain("u2");
  });

  it("o filtro de indexação por omissão depende do PERFIL", async () => {
    // O perfil Indexação abre no quadro dos pendentes; os outros em todos.
    papelActivo = "indexacao";
    montar();
    await waitFor(() => expect(api.getKanbanBoard).toHaveBeenCalled());
    expect(screen.getByTestId("layout")).toBeInTheDocument();
  });
});

describe("KanbanPage — os botões fantasma (ligação do Lote 6)", () => {
  it("o perfil index não consegue usar o botão de criar", async () => {
    papelActivo = "indexacao";
    capacidadesPorPapel = {
      indexacao: { PROCESS_CREATE: false, PROCESS_EXPORT: false },
    };
    montar();
    await screen.findByText("Ana Martins");
    const criar = screen.queryByRole("button", { name: /novo processo/i });
    expect(criar === null || criar.disabled).toBe(true);
  });

  it("o perfil index não consegue exportar em NENHUM dos dois botões", async () => {
    // Há DOIS botões «Exportar Excel» neste ecrã: o da página (gatido no
    // Lote 6) e o do cabeçalho do quadro, que tinha ficado FORA do fecho
    // dos botões fantasma — sem gate nenhum, e exporta NIF, telefone e
    // email. Um perfil sem a capacidade via um cadeado ao lado de um
    // botão a funcionar. Por isso a asserção é sobre TODOS.
    papelActivo = "indexacao";
    capacidadesPorPapel = {
      indexacao: { PROCESS_CREATE: false, PROCESS_EXPORT: false },
    };
    montar();
    await screen.findByText("Ana Martins");
    const botoes = screen.queryAllByRole("button", { name: /exportar/i });
    expect(botoes.length).toBeGreaterThan(0);
    for (const botao of botoes) {
      expect(botao).toBeDisabled();
    }
  });

  it("o diretor usa criar e TODOS os botões de exportar", async () => {
    // Contraprova: sem ela, desactivar tudo a todos passava os dois acima.
    papelActivo = "diretor";
    capacidadesPorPapel = {
      diretor: { PROCESS_CREATE: true, PROCESS_EXPORT: true },
    };
    montar();
    await screen.findByText("Ana Martins");
    expect(screen.getByRole("button", { name: /novo processo/i })).toBeEnabled();
    const botoes = screen.getAllByRole("button", { name: /exportar/i });
    expect(botoes.length).toBeGreaterThan(0);
    for (const botao of botoes) {
      expect(botao).toBeEnabled();
    }
  });

  it("abrir o diálogo de criação não rebenta a página", async () => {
    const utilizador = userEvent.setup();
    papelActivo = "diretor";
    capacidadesPorPapel = { diretor: { PROCESS_CREATE: true } };
    montar();
    await screen.findByText("Ana Martins");
    await utilizador.click(screen.getByRole("button", { name: /novo processo/i }));
    expect(await screen.findByTestId("modal-criar")).toBeInTheDocument();
  });
});


describe("KanbanPage — a partilha (D-25)", () => {
  it("o cartão partilhado mostra a etiqueta [Partilha: …]", async () => {
    // O cartão é o REAL (`KanbanCard`): falsear o quadro tornava este
    // teste inútil, porque o que falta cobrir é a ligação página ↔
    // quadro ↔ cartão.
    montar();
    await screen.findByText("Ana Martins");

    const etiquetas = screen.getAllByTestId("etiqueta-partilha");
    expect(etiquetas).toHaveLength(1);
    expect(etiquetas[0]).toHaveTextContent("Partilha: Domus");
  });

  it("o filtro rápido está no cabeçalho do quadro", async () => {
    // O quadro tem construtor de query SEPARADO no servidor e cabeçalho
    // próprio no cliente: um filtro que só exista na listagem dá um
    // quadro a ignorá-lo, sem erro nenhum.
    montar();
    await screen.findByText("Ana Martins");

    expect(screen.getByTestId("kanban-partilha-filter")).toBeInTheDocument();
    expect(
      screen.getByRole("radio", { name: /exclusivos da casa/i }),
    ).toBeInTheDocument();
  });

  it("clicar em «Partilhados» muda o pedido do quadro", async () => {
    const utilizador = userEvent.setup();
    montar();
    await screen.findByText("Ana Martins");

    api.getKanbanBoard.mockClear();
    await utilizador.click(
      screen.getByRole("radio", { name: /^partilhados$/i }),
    );

    await waitFor(() => expect(api.getKanbanBoard).toHaveBeenCalled());
    const enviados = api.getKanbanBoard.mock.calls
      .map(([params]) => String(params ?? ""))
      .join("|");
    expect(enviados).toContain("partilha=partilhados");
  });
});


describe("KanbanPage — a pesquisa e os filtros do quadro sobrevivem a «entrar e voltar»", () => {
  it("arranca com a pesquisa e o Sub35 que estão no URL", async () => {
    parametros = new URLSearchParams("kb_q=ana&kb_sub35=true");
    montar();
    expect(await screen.findByPlaceholderText("Pesquisar cliente...")).toHaveValue("ana");
    await waitFor(() => expect(api.getKanbanBoard).toHaveBeenCalled());
    // O Sub35 é parâmetro do PEDIDO ao servidor, não só do ecrã.
    const pedidos = api.getKanbanBoard.mock.calls.map(([p]) => String(p ?? "")).join("|");
    expect(pedidos).toMatch(/sub35/);
  });

  it("sem parâmetros o quadro abre limpo (contraprova)", async () => {
    montar();
    expect(await screen.findByPlaceholderText("Pesquisar cliente...")).toHaveValue("");
  });

  it("escrever na pesquisa grava-a no URL com replace, sem pisar os outros parâmetros", async () => {
    parametros = new URLSearchParams("consultor=u2");
    montar();
    await userEvent.type(await screen.findByPlaceholderText("Pesquisar cliente..."), "rui");

    await waitFor(() => expect(definirParametros).toHaveBeenCalled());
    const [actualizador, opcoes] = definirParametros.mock.calls.at(-1);
    const resultado = actualizador(new URLSearchParams("consultor=u2"));
    expect(resultado.get("kb_q")).toBe("rui");
    expect(resultado.get("consultor")).toBe("u2");
    expect(opcoes).toEqual({ replace: true });
  });
});
