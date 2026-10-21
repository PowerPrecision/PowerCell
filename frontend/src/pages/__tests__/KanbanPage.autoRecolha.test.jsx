/**
 * Auto-recolher do Kanban: colunas vazias recolhem-se — também Concluído e Desistência.
 *
 * O Kanban excluía `concluidos`/`desistencias` da auto-recolha «porque os
 * utilizadores precisam de as ver». Fazia sentido enquanto o quadro podia
 * mostrar cartões de OUTRAS redes (cartões-fantasma que o detalhe recusa com
 * «Processo não encontrado»): uma coluna «com conteúdo» sem nada seu. Com as
 * listagens limpas (o servidor isola; a cache já não atravessa sessões), uma
 * coluna vazia é vazia.
 *
 * A armadilha que o desenho evita: o `count` de Concluídos é 0 ENQUANTO a
 * consulta própria não responde. Recolher aí fechava-a para sempre com
 * cartões por chegar, por isso estas duas só se decidem depois dela.
 *
 * Com o período por omissão (30 dias) há UM só pedido: o quadro já traz as
 * colunas de concluídos. Ao mudar o período faz-se um segundo pedido, só para
 * essas colunas — distinguem-se pela ORDEM (o do quadro é sempre o primeiro).
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
  getPartnerOptions: vi.fn(() => Promise.resolve({ data: { partners: [] } })),
  getProcessLabels: vi.fn(),
  updateProcessStatus: vi.fn(),
  getProcesses: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

import KanbanPage from "../KanbanPage";
import * as api from "../../services/api";

const col = (id, label, order, processes = []) => ({
  id, name: id, label, color: "#3B82F6", order, count: processes.length, processes,
});
const cartao = (id, nome, status) => ({
  id, client_id: `c-${id}`, process_number: `PROC-${id}`, client_name: nome, status,
  priority: "normal", created_at: "2026-09-01T10:00:00Z", updated_at: "2026-09-02T10:00:00Z",
  labels: [], under_35: false,
});
const quadro = (...colunas) => ({
  data: {
    columns: colunas, total_processes: 1, total_inactive: 0, total_desconhecidos: 0,
    user_role: "diretor", current_user_id: "u1", view_mode: "all", completed_days: 30,
  },
});

const ANALISE = col("analise", "Análise", 1, [cartao("1", "Rui Pereira", "analise")]);
const CONCLUIDOS_VAZIO = col("concluidos", "Concluídos", 8);
const DESISTENCIAS_VAZIO = col("desistencias", "Desistências", 9);

/** `pedidos[0]` é a consulta activa, `pedidos[1]` a de concluídos. */
function servir(...respostas) {
  let n = 0;
  api.getKanbanBoard.mockImplementation(() => {
    const r = respostas[Math.min(n, respostas.length - 1)];
    n += 1;
    return typeof r === "function" ? r() : Promise.resolve(r);
  });
}

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

const recolhidas = () => screen.queryAllByTitle("Clique para expandir");

beforeEach(() => {
  vi.clearAllMocks();
  parametros = new URLSearchParams();
  papelActivo = "diretor";
  capacidadesPorPapel = null;
  api.getUsers.mockResolvedValue({ data: [{ id: "u1", name: "Quem Vê O Quadro", role: "consultor", is_active: true }] });
  api.getProcessLabels.mockResolvedValue({ data: { labels: [] } });
});

describe("Kanban — auto-recolher colunas vazias", () => {
  it("Concluídos e Desistências vazias recolhem-se quando a consulta delas respondeu", async () => {
    servir(quadro(ANALISE, CONCLUIDOS_VAZIO, DESISTENCIAS_VAZIO));
    montar();

    expect(await screen.findByText("Rui Pereira")).toBeInTheDocument();
    await waitFor(() => expect(recolhidas()).toHaveLength(2));
    // A coluna com cartões continua aberta.
    expect(screen.getByText("Rui Pereira")).toBeInTheDocument();
  });

  it("contraprova: Concluídos COM cartões fica aberta; só a vazia se recolhe", async () => {
    const comCartao = col("concluidos", "Concluídos", 8, [cartao("9", "Maria Concluída", "concluidos")]);
    servir(quadro(ANALISE, comCartao, DESISTENCIAS_VAZIO));
    montar();

    expect(await screen.findByText("Maria Concluída")).toBeInTheDocument();
    await waitFor(() => expect(recolhidas()).toHaveLength(1));
  });

  it("com o período por omissão o quadro basta: UM só pedido ao servidor", async () => {
    // Dívida técnica: a consulta de Concluídos (30 dias) era IDÊNTICA à do quadro
    // e o servidor respondia duas vezes à mesma pergunta em toda a primeira carga.
    servir(quadro(ANALISE, CONCLUIDOS_VAZIO, DESISTENCIAS_VAZIO));
    montar();

    expect(await screen.findByText("Rui Pereira")).toBeInTheDocument();
    await waitFor(() => expect(recolhidas()).toHaveLength(2));
    expect(api.getKanbanBoard).toHaveBeenCalledTimes(1);
    expect(api.getKanbanBoard.mock.calls[0][0].get("completed_days")).toBe("30");
  });

  it("os cartões de Concluídos vêm da resposta do quadro quando só há um pedido", async () => {
    const comCartao = col("concluidos", "Concluídos", 8, [cartao("9", "Maria Concluída", "concluidos")]);
    servir(quadro(ANALISE, comCartao, DESISTENCIAS_VAZIO));
    montar();

    expect(await screen.findByText("Maria Concluída")).toBeInTheDocument();
    expect(api.getKanbanBoard).toHaveBeenCalledTimes(1);
  });

  it("mudar o período faz o SEGUNDO pedido (só o de Concluídos) e mostra o que ele traz", async () => {
    let responderConcluidos;
    servir(
      quadro(ANALISE, CONCLUIDOS_VAZIO, DESISTENCIAS_VAZIO),
      () => new Promise((resolve) => { responderConcluidos = resolve; }),
    );
    montar();
    expect(await screen.findByText("Rui Pereira")).toBeInTheDocument();
    expect(api.getKanbanBoard).toHaveBeenCalledTimes(1);

    const utilizador = userEvent.setup();
    await utilizador.click(screen.getByTestId("kanban-completed-filter"));
    await utilizador.click(await screen.findByRole("option", { name: "Últimos 90 dias" }));

    await waitFor(() => expect(api.getKanbanBoard).toHaveBeenCalledTimes(2));
    expect(api.getKanbanBoard.mock.calls[1][0].get("completed_days")).toBe("90");

    responderConcluidos(quadro(
      ANALISE,
      col("concluidos", "Concluídos", 8, [cartao("9", "Maria Concluída", "concluidos")]),
      DESISTENCIAS_VAZIO,
    ));
    expect(await screen.findByText("Maria Concluída")).toBeInTheDocument();
  });

  it("mudar o período reabre Concluídos e volta a decidir: continua vazia → recolhe-se outra vez", async () => {
    let responderConcluidos;
    servir(
      quadro(ANALISE, CONCLUIDOS_VAZIO, DESISTENCIAS_VAZIO),
      () => new Promise((resolve) => { responderConcluidos = resolve; }),
    );
    montar();
    await waitFor(() => expect(recolhidas()).toHaveLength(2));

    const utilizador = userEvent.setup();
    await utilizador.click(screen.getByTestId("kanban-completed-filter"));
    await utilizador.click(await screen.findByRole("option", { name: "Últimos 90 dias" }));
    await waitFor(() => expect(api.getKanbanBoard).toHaveBeenCalledTimes(2));

    // Enquanto o novo período não responde, nada está recolhido (não se decide às cegas).
    await waitFor(() => expect(recolhidas()).toHaveLength(0));

    responderConcluidos(quadro(ANALISE, CONCLUIDOS_VAZIO, DESISTENCIAS_VAZIO));
    await waitFor(() => expect(recolhidas()).toHaveLength(2));
  });

  it("se o pedido do período falha, o quadro mantém o que já tinha", async () => {
    servir(
      quadro(ANALISE, CONCLUIDOS_VAZIO, DESISTENCIAS_VAZIO),
      () => Promise.reject({ response: { status: 500, data: { detail: "boom" } } }),
    );
    montar();
    expect(await screen.findByText("Rui Pereira")).toBeInTheDocument();

    const utilizador = userEvent.setup();
    await utilizador.click(screen.getByTestId("kanban-completed-filter"));
    await utilizador.click(await screen.findByRole("option", { name: "Últimos 7 dias" }));

    await waitFor(() => expect(api.getKanbanBoard).toHaveBeenCalledTimes(2));
    expect(screen.getByText("Rui Pereira")).toBeInTheDocument();
  });

  it("se o quadro falha, nada se recolhe (não se esconde o que não se sabe)", async () => {
    servir(() => Promise.reject({ response: { status: 500, data: { detail: "boom" } } }));
    montar();

    await waitFor(() => expect(api.getKanbanBoard).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 50));
    expect(recolhidas()).toHaveLength(0);
  });
});
