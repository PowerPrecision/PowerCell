/**
 * «Os Meus Processos» com o perfil Index — a PÁGINA montada (`ProcessesPage` decide, `OsMeusProcessosDoIndex` desenha).
 *
 * Falseia só as fronteiras: `DashboardLayout`, `AuthContext`, o router e o cliente HTTP (`getIndexQueue`, com a
 * forma REAL de `GET /index/queue`: `{items, total, page, size, facets}`, lida em `run_get_index_queue`). A tabela,
 * o hook da fila, a paginação, as chaves de cache e a decisão por perfil são os REAIS.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../layouts/DashboardLayout", () => ({ default: ({ children }) => <div data-testid="layout">{children}</div> }));
vi.mock("../../components/CreateProcessModal", () => ({
  default: ({ open }) => (open ? <div data-testid="modal-criar" /> : null),
}));
vi.mock("../../hooks/useTaskEvents", () => ({ useTaskEvents: () => ({ isConnected: false }), TASK_SOURCE: { TASK_LOG: "task_log" } }));

const navegar = vi.fn();
let parametros = new URLSearchParams();
const ouvintes = new Set();
vi.mock("react-router-dom", async () => {
  const react = await import("react");
  return {
    useNavigate: () => navegar,
    // STATEFUL e PARTILHADO: um mock que ignorasse a escrita deixava o ecrã parado (a lição do `KanbanPage.test`),
    // e hooks com estado próprio não veriam o que o outro escreveu (como o router a sério: um URL só).
    useSearchParams: () => {
      const [, forcar] = react.useReducer((n) => n + 1, 0);
      react.useEffect(() => {
        ouvintes.add(forcar);
        return () => ouvintes.delete(forcar);
      }, []);
      const escrever = (seguinte) => {
        parametros = new URLSearchParams(typeof seguinte === "function" ? seguinte(parametros) : seguinte);
        ouvintes.forEach((f) => f());
      };
      return [parametros, escrever];
    },
    useLocation: () => ({ pathname: "/processos", search: "" }),
    Link: ({ children, to }) => <a href={to}>{children}</a>,
  };
});

let papelActivo = "indexacao";
let capacidades = { indexacao: { PROCESS_CREATE: true } };
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: "ix1", name: "Ana Index", role: "consultor", capabilities_por_papel: capacidades },
    token: "t",
    effectiveRole: papelActivo,
    activeRole: papelActivo,
    activeCompanyId: "c1",
    effectiveCompanyId: "c1",
  }),
}));

vi.mock("../../hooks/queries/useProcessQuery", () => ({ useWorkflowStatusesQuery: () => ({ data: [], isLoading: false }) }));

vi.mock("../../services/api", () => ({
  getIndexQueue: vi.fn(),
  getProcesses: vi.fn(),
  getMyProcesses: vi.fn(),
  getProcessLabels: vi.fn(),
}));

import ProcessesPage from "../ProcessesPage";
import * as api from "../../services/api";

const LINHAS = [
  {
    id: "p-7", client_name: "Marta Quintela", process_number: 4821, index_status: "in_review",
    documents_total: 9, documents_to_analyse: 3, index_alerts_open: 2, created_at: "2026-10-19T09:15:00+00:00",
    company: { name: "Casa Verde, Lda", other_network: true }, has_pending_review: false, stagnant: true,
  },
  {
    id: "p-8", client_name: "Rui Tavares", process_number: 4822, index_status: "pending",
    documents_total: 0, documents_to_analyse: 0, index_alerts_open: 0, created_at: "2026-10-21T14:00:00+00:00",
    company: null,
  },
];

function montar() {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={cliente}>
      <ProcessesPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  parametros = new URLSearchParams();
  papelActivo = "indexacao";
  capacidades = { indexacao: { PROCESS_CREATE: true } };
  api.getIndexQueue.mockResolvedValue({ data: { items: LINHAS, total: 2, page: 1, size: 25, facets: { companies: [], statuses: [] } } });
  api.getProcessLabels.mockResolvedValue({ data: { labels: [] } });
});

describe("Os Meus Processos — perfil Index", () => {
  it("desenha as seis colunas de triagem, por esta ordem", async () => {
    montar();
    const tabela = await screen.findByTestId("index-queue-table");
    const colunas = within(tabela).getAllByRole("columnheader").map((c) => c.textContent.trim());
    // a sétima é a das acções (só para leitores de ecrã)
    expect(colunas.slice(0, 6)).toEqual(["Processo", "Empresa/Origem", "Estado", "Documentos", "Alertas", "Entrada"]);
    expect(colunas[6]).toBe("Acções");
  });

  it("pede ao servidor SÓ os meus (mine=true) e a fila por tratar", async () => {
    montar();
    await screen.findByTestId("index-queue-table");
    expect(api.getIndexQueue).toHaveBeenCalled();
    const params = api.getIndexQueue.mock.calls[0][0];
    expect(params).toMatchObject({ tab: "pending", mine: true, page: 1 });
  });

  it("cada linha mostra processo, empresa de origem, estado, documentos, alertas e entrada", async () => {
    montar();
    const linhas = await screen.findAllByTestId("index-queue-row");
    const primeira = within(linhas[0]);
    expect(primeira.getByText("Marta Quintela")).toBeInTheDocument();
    expect(primeira.getByText("#4821")).toBeInTheDocument();
    expect(primeira.getByText("Casa Verde, Lda")).toBeInTheDocument();
    expect(primeira.getByText("Partilhado")).toBeInTheDocument();
    expect(primeira.getByText("Em tratamento")).toBeInTheDocument();
    expect(within(primeira.getAllByRole("cell")[3]).getByText(/^9/)).toBeInTheDocument();     // documentos
    expect(primeira.getByText("(3 por analisar)")).toBeInTheDocument();
    expect(within(primeira.getAllByRole("cell")[4]).getByText("2")).toBeInTheDocument();   // alertas abertos
    expect(primeira.getByText("Sem actividade")).toBeInTheDocument();
    expect(within(linhas[1]).getByTestId("index-queue-origem")).toHaveTextContent("—");
  });

  it("clicar em «Abrir» leva à bancada do processo", async () => {
    montar();
    await userEvent.click(await screen.findByRole("button", { name: "Abrir Marta Quintela" }));
    expect(navegar).toHaveBeenCalledWith("/index/p-7");
  });

  it("não desenha a tabela de acompanhamento de negócios nem pede /processes/me", async () => {
    montar();
    await screen.findByTestId("index-queue-table");
    expect(screen.queryByText("Notas do Consultor")).not.toBeInTheDocument();
    expect(api.getMyProcesses).not.toHaveBeenCalled();
    expect(api.getProcesses).not.toHaveBeenCalled();
  });

  it("o botão «Novo Processo» não se perde (o Index cria processos)", async () => {
    montar();
    const botao = await screen.findByRole("button", { name: /novo processo/i });
    expect(botao).toBeEnabled();
    await userEvent.click(botao);
    expect(await screen.findByTestId("modal-criar")).toBeInTheDocument();
  });

  it("sem a capacidade de criar, o botão fica visível mas bloqueado", async () => {
    capacidades = { indexacao: { PROCESS_CREATE: false } };
    montar();
    await screen.findByTestId("index-queue-table");
    const botao = screen.getByRole("button", { name: /novo processo/i });
    expect(botao).toBeDisabled();
  });

  it("um erro de leitura diz-se e deixa tentar de novo (nunca «sem processos»)", async () => {
    api.getIndexQueue.mockRejectedValueOnce(new Error("boom"));
    montar();
    expect(await screen.findByTestId("meus-processos-erro")).toBeInTheDocument();
    expect(screen.queryByText(/sem processos/i)).not.toBeInTheDocument();
    api.getIndexQueue.mockResolvedValue({ data: { items: LINHAS, total: 2, page: 1, size: 25 } });
    await userEvent.click(screen.getByRole("button", { name: /tentar de novo/i }));
    expect(await screen.findByTestId("index-queue-table")).toBeInTheDocument();
  });

  it("a lista vazia diz que não há processos atribuídos", async () => {
    api.getIndexQueue.mockResolvedValue({ data: { items: [], total: 0, page: 1, size: 25 } });
    montar();
    expect(await screen.findByText(/sem processos por tratar/i)).toBeInTheDocument();
  });

  it("mudar de separador pede as revisões, também só as minhas", async () => {
    montar();
    await screen.findByTestId("index-queue-table");
    await userEvent.click(screen.getByRole("tab", { name: "Indexados a rever" }));
    await waitFor(() => expect(api.getIndexQueue.mock.calls.some(([p]) => p.tab === "reviews" && p.mine === true)).toBe(true));
  });

  it("pesquisar vai para o servidor com a posse intacta", async () => {
    montar();
    await screen.findByTestId("index-queue-table");
    await userEvent.type(screen.getByRole("textbox", { name: "Pesquisar nos meus processos" }), "Tavares");
    await waitFor(() => expect(api.getIndexQueue.mock.calls.some(([p]) => p.q === "Tavares" && p.mine === true)).toBe(true));
  });

  it("clicar no cabeçalho ordena sem perder a posse", async () => {
    montar();
    await screen.findByTestId("index-queue-table");
    await userEvent.click(screen.getByRole("button", { name: /alertas/i }));
    await waitFor(() => expect(api.getIndexQueue.mock.calls.some(([p]) => p.sort_by === "alerts_desc" && p.mine === true)).toBe(true));
  });
});

describe("Os Meus Processos — os outros perfis", () => {
  it("contraprova: o consultor NÃO vê a tabela do Index nem pede a fila do Index", async () => {
    papelActivo = "consultor";
    api.getMyProcesses.mockResolvedValue({ data: { items: [], total: 0, page: 1, size: 25, pages: 0 } });
    montar();
    await waitFor(() => expect(api.getMyProcesses).toHaveBeenCalled());
    expect(screen.queryByTestId("index-queue-table")).not.toBeInTheDocument();
    expect(api.getIndexQueue).not.toHaveBeenCalled();
  });
});
