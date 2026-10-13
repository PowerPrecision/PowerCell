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
 * As duas consultas (activa e concluídos) pedem o MESMO `GET /processes/kanban`
 * e não se distinguem pelos parâmetros; distinguem-se pela ORDEM em que o
 * quadro as arranca (a activa primeiro) — daí o `pedido` ser por ordem.
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

  it("enquanto a consulta de concluídos não respondeu, Concluídos NÃO se recolhe", async () => {
    // A consulta activa devolve Concluídos com count 0 («ainda não carregou»).
    let responderConcluidos;
    servir(
      quadro(ANALISE, CONCLUIDOS_VAZIO, DESISTENCIAS_VAZIO),
      () => new Promise((resolve) => { responderConcluidos = resolve; }),
    );
    montar();

    expect(await screen.findByText("Rui Pereira")).toBeInTheDocument();
    await waitFor(() => expect(responderConcluidos).toBeTypeOf("function"));
    expect(recolhidas()).toHaveLength(0);

    // Quando responde com cartões, Concluídos chega aberta com eles.
    responderConcluidos(quadro(
      ANALISE,
      col("concluidos", "Concluídos", 8, [cartao("9", "Maria Concluída", "concluidos")]),
      DESISTENCIAS_VAZIO,
    ));
    expect(await screen.findByText("Maria Concluída")).toBeInTheDocument();
    await waitFor(() => expect(recolhidas()).toHaveLength(1)); // só Desistências
  });

  it("se a consulta de concluídos falha, Concluídos fica aberta (não se esconde o que não se sabe)", async () => {
    servir(
      quadro(ANALISE, CONCLUIDOS_VAZIO, DESISTENCIAS_VAZIO),
      () => Promise.reject({ response: { status: 500, data: { detail: "boom" } } }),
    );
    montar();

    expect(await screen.findByText("Rui Pereira")).toBeInTheDocument();
    await waitFor(() => expect(api.getKanbanBoard).toHaveBeenCalledTimes(2));
    await new Promise((r) => setTimeout(r, 50));
    expect(recolhidas()).toHaveLength(0);
  });
});
