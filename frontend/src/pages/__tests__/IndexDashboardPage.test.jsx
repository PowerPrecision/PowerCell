/**
 * A fila do Index MONTADA (Lote 12, Fase 4) — a regra do `WebmailPage`/`VisitsPage`: um ecrã só
 * está coberto quando a PÁGINA é montada num teste.
 *
 * A forma dos dados é a REAL do `GET /api/index/queue` (`services/index_api.run_get_index_queue`):
 * `{items: [{id, process_number, client_name, index_status, ..., documents_total,
 * documents_to_analyse}], total, page, size, tab}`. Os valores do fixture são DIFERENTES das
 * omissões, senão um erro de leitura é indistinguível de uma leitura correcta.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));
vi.mock("../../hooks/useTaskEvents", () => ({
  useTaskEvents: () => ({ isConnected: false }),
  TASK_SOURCE: { TASK_LOG: "task_log", BACKGROUND_JOB: "background_job" },
}));
vi.mock("../../services/api", () => ({ getIndexQueue: vi.fn() }));

import { getIndexQueue } from "../../services/api";
import IndexDashboardPage from "../index/IndexDashboardPage";

const FILA = {
  items: [
    {
      id: "proc-aaaa1111", process_number: 4711, client_name: "Marta Quintela", index_status: "pending",
      index_skipped: false, has_pending_review: false, index_alerts_open: 3, created_at: "2026-10-03T10:00:00Z",
      documents_total: 7, documents_to_analyse: 2,
    },
    {
      id: "proc-bbbb2222", process_number: 4712, client_name: "Rui Calado", index_status: "in_review",
      index_skipped: false, has_pending_review: false, index_alerts_open: 0, created_at: "2026-10-04T10:00:00Z",
      documents_total: 4, documents_to_analyse: 0,
    },
  ],
  total: 57, page: 1, size: 25, tab: "pending",
};
const REVISOES = {
  items: [
    {
      id: "proc-cccc3333", process_number: 4001, client_name: "Teresa Louro", index_status: "indexed",
      has_pending_review: true, index_alerts_open: 1, indexed_at: "2026-10-09T09:00:00Z", documents_total: 5,
    },
  ],
  total: 1, page: 1, size: 25, tab: "reviews",
};

function Localizacao() {
  const l = useLocation();
  return <div data-testid="localizacao">{l.pathname}{l.search}</div>;
}

function montar(entrada = "/index") {
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={[entrada]}>
        <Localizacao />
        <Routes>
          <Route path="/index" element={<IndexDashboardPage />} />
          <Route path="/index/:processId" element={<div data-testid="bancada" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  getIndexQueue.mockReset();
  getIndexQueue.mockImplementation(async (params) => ({ data: params.tab === "reviews" ? REVISOES : FILA }));
});

describe("IndexDashboardPage", () => {
  it("monta e mostra a Fila de Espera com os dados REAIS do servidor", async () => {
    montar();
    expect(await screen.findByText("Marta Quintela")).toBeInTheDocument();
    expect(screen.getByText("Rui Calado")).toBeInTheDocument();
    expect(screen.getByText("#4711")).toBeInTheDocument();
    expect(screen.getByText(/2 por analisar/)).toBeInTheDocument();
    expect(screen.getAllByTestId("index-queue-row")).toHaveLength(2);
    expect(screen.getByTestId("paginacao-intervalo")).toHaveTextContent("1–25 de 57");
  });

  it("pede a aba por omissão ao servidor", async () => {
    montar();
    await screen.findByText("Marta Quintela");
    expect(getIndexQueue).toHaveBeenCalledWith(expect.objectContaining({ tab: "pending", page: 1 }));
  });

  it("as duas abas existem com os nomes da direcção", async () => {
    montar();
    expect(await screen.findByRole("tab", { name: "Fila de Espera" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Revisões Pendentes" })).toBeInTheDocument();
  });

  it("mudar de aba pede outra fila e a chave de cache não as mistura", async () => {
    montar();
    await screen.findByText("Marta Quintela");
    await userEvent.click(screen.getByRole("tab", { name: "Revisões Pendentes" }));
    expect(await screen.findByText("Teresa Louro")).toBeInTheDocument();
    expect(screen.queryByText("Marta Quintela")).not.toBeInTheDocument();
    expect(getIndexQueue).toHaveBeenLastCalledWith(expect.objectContaining({ tab: "reviews" }));
    expect(screen.getByTestId("localizacao")).toHaveTextContent("idx_tab=reviews");
  });

  it("mudar de aba volta à página 1 numa só escrita (duas escritas seguidas pisavam-se)", async () => {
    montar("/index?idx_p=2&idx_q=Marta");
    await screen.findByText("Marta Quintela");
    await userEvent.click(screen.getByRole("tab", { name: "Revisões Pendentes" }));
    await screen.findByText("Teresa Louro");
    const url = screen.getByTestId("localizacao").textContent;
    expect(url).toContain("idx_tab=reviews");
    expect(url).not.toContain("idx_p=");
    expect(url).toContain("idx_q=Marta"); // o resto do URL não se perde
  });

  it("o separador vive no URL: abrir já em «reviews» pede reviews", async () => {
    montar("/index?idx_tab=reviews");
    expect(await screen.findByText("Teresa Louro")).toBeInTheDocument();
    expect(getIndexQueue).toHaveBeenCalledWith(expect.objectContaining({ tab: "reviews" }));
  });

  it("um separador inventado no URL cai na Fila de Espera, não num ecrã vazio", async () => {
    montar("/index?idx_tab=hacker");
    expect(await screen.findByText("Marta Quintela")).toBeInTheDocument();
    expect(getIndexQueue).toHaveBeenCalledWith(expect.objectContaining({ tab: "pending" }));
  });

  it("abrir um processo leva à bancada", async () => {
    montar();
    await userEvent.click(await screen.findByRole("button", { name: "Abrir Marta Quintela" }));
    expect(await screen.findByTestId("bancada")).toBeInTheDocument();
    expect(screen.getByTestId("localizacao")).toHaveTextContent("/index/proc-aaaa1111");
  });

  it("mudar de página pede essa página", async () => {
    montar();
    await screen.findByText("Marta Quintela");
    await userEvent.click(screen.getByRole("button", { name: /seguinte/i }));
    await waitFor(() => expect(getIndexQueue).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 })));
  });

  it("a pesquisa vai ao servidor depois de assentar", async () => {
    montar();
    await screen.findByText("Marta Quintela");
    await userEvent.type(screen.getByLabelText("Pesquisar processos"), "Marta");
    await waitFor(() => expect(getIndexQueue).toHaveBeenLastCalledWith(expect.objectContaining({ q: "Marta" })), {
      timeout: 2000,
    });
  });

  it("um erro de LEITURA diz-se e nunca é «fila vazia»", async () => {
    getIndexQueue.mockRejectedValue({ response: { status: 500 } });
    montar();
    expect(await screen.findByTestId("index-erro-de-leitura")).toHaveTextContent("Não foi possível carregar a fila");
    expect(screen.queryByText("Nada por tratar")).not.toBeInTheDocument();
    getIndexQueue.mockResolvedValue({ data: FILA });
    await userEvent.click(screen.getByRole("button", { name: /tentar de novo/i }));
    expect(await screen.findByText("Marta Quintela")).toBeInTheDocument();
  });

  it("uma fila realmente vazia diz-se vazia", async () => {
    getIndexQueue.mockResolvedValue({ data: { items: [], total: 0, page: 1, size: 25, tab: "pending" } });
    montar();
    expect(await screen.findByText("Nada por tratar")).toBeInTheDocument();
  });

  it("um corpo com a forma errada não rebenta a página", async () => {
    getIndexQueue.mockResolvedValue({ data: { items: { a: 1 }, total: "x" } });
    montar();
    expect(await screen.findByText("Nada por tratar")).toBeInTheDocument();
  });
});
