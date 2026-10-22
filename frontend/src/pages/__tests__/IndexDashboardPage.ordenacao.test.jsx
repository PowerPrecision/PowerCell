/**
 * A fila do Index MONTADA com ordenação e filtros (Out 2026): cabeçalhos clicáveis, seletores, URL e pedido.
 * A forma dos dados é a REAL do `GET /api/index/queue`, com `facets` e `sort_by`.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
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

const FACETS = {
  companies: [{ id: "c-power", name: "Power", count: 5 }, { id: "c-prec", name: "Precision", count: 2 }],
  statuses: ["pending", "in_review"],
};
const item = (id, nome, extra = {}) => ({
  id, process_number: `P-${id}`, client_name: nome, index_status: "pending", index_skipped: false,
  has_pending_review: false, index_alerts_open: 0, created_at: "2026-10-03T10:00:00Z",
  documents_total: 1, documents_to_analyse: 0, company: { name: "Power", other_network: false }, ...extra,
});
const resposta = (items, extra = {}) => ({ data: { items, total: items.length, page: 1, size: 25, tab: "pending", facets: FACETS, ...extra } });

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
        <Routes><Route path="/index" element={<IndexDashboardPage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
const ultimo = () => getIndexQueue.mock.calls.at(-1)[0];

beforeEach(() => {
  getIndexQueue.mockReset();
  getIndexQueue.mockResolvedValue(resposta([item("1", "Ana"), item("2", "Rui")]));
});

describe("cabeçalhos clicáveis", () => {
  it("por omissão a ordem é a da aba, o pedido não leva sort_by e o URL fica limpo", async () => {
    montar();
    await screen.findByText("Ana");
    expect(ultimo().sort_by).toBeUndefined();
    expect(screen.getByTestId("localizacao").textContent).toBe("/index");
    expect(screen.getByRole("columnheader", { name: /Entrada/ })).toHaveAttribute("aria-sort", "ascending");
  });

  it("carregar em «Processo» ordena por cliente; outra vez inverte; o URL e o pedido acompanham", async () => {
    const user = userEvent.setup();
    montar();
    await screen.findByText("Ana");
    await user.click(screen.getByTestId("ordenar-processo"));
    await waitFor(() => expect(ultimo().sort_by).toBe("client_asc"));
    expect(screen.getByTestId("localizacao")).toHaveTextContent("idx_sort=client_asc");
    expect(screen.getByRole("columnheader", { name: /Processo/ })).toHaveAttribute("aria-sort", "ascending");
    expect(screen.getByRole("columnheader", { name: /Entrada/ })).toHaveAttribute("aria-sort", "none");

    await user.click(screen.getByTestId("ordenar-processo"));
    await waitFor(() => expect(ultimo().sort_by).toBe("client_desc"));
    expect(screen.getByRole("columnheader", { name: /Processo/ })).toHaveAttribute("aria-sort", "descending");
  });

  it("voltar à ordem por omissão tira-a do URL", async () => {
    const user = userEvent.setup();
    montar("/index?idx_sort=client_asc");
    await screen.findByText("Ana");
    await user.click(screen.getByTestId("ordenar-data")); // created_asc = a omissão
    await waitFor(() => expect(screen.getByTestId("localizacao").textContent).not.toContain("idx_sort"));
    expect(ultimo().sort_by).toBeUndefined();
  });

  it("ordenar volta à página 1 numa só escrita e não pisa a pesquisa", async () => {
    const user = userEvent.setup();
    montar("/index?idx_p=3&idx_q=Ana");
    await screen.findByText("Ana");
    await user.click(screen.getByTestId("ordenar-alertas"));
    await waitFor(() => expect(ultimo().sort_by).toBe("alerts_desc"));
    const url = screen.getByTestId("localizacao").textContent;
    expect(url).toContain("idx_sort=alerts_desc");
    expect(url).toContain("idx_q=Ana");
    expect(url).not.toContain("idx_p=");
  });

  it("«Documentos» não é ordenável (não há botão)", async () => {
    montar();
    await screen.findByText("Ana");
    expect(screen.getByRole("columnheader", { name: "Documentos" })).not.toHaveAttribute("aria-sort");
    expect(screen.queryByTestId("ordenar-documentos")).toBeNull();
  });
});

describe("seletores", () => {
  it("«Ordenar por» lista só o que a aba aceita e pede a ordem escolhida", async () => {
    const user = userEvent.setup();
    montar();
    await screen.findByText("Ana");
    const ordem = screen.getByLabelText("Ordenar por");
    expect(within(ordem).queryByText(/Indexado em/)).toBeNull();
    await user.selectOptions(ordem, "client_desc");
    await waitFor(() => expect(ultimo().sort_by).toBe("client_desc"));
  });

  it("Estado, Empresa e Origem viajam com o nome do servidor e vão para o URL", async () => {
    const user = userEvent.setup();
    montar();
    await screen.findByText("Ana");
    await user.selectOptions(screen.getByLabelText("Estado"), "in_review");
    await user.selectOptions(screen.getByLabelText("Empresa"), "c-prec");
    await user.selectOptions(screen.getByLabelText("Origem"), "shared");
    await waitFor(() => expect(ultimo()).toMatchObject({ index_status: "in_review", company_id: "c-prec", origin: "shared" }));
    const url = screen.getByTestId("localizacao").textContent;
    expect(url).toContain("idx_status=in_review");
    expect(url).toContain("idx_company=c-prec");
    expect(url).toContain("idx_origin=shared");
  });

  it("as empresas são as que o SERVIDOR diz que a fila tem, com a contagem", async () => {
    montar();
    await screen.findByText("Ana");
    const empresa = screen.getByLabelText("Empresa");
    expect(within(empresa).getByText("Power (5)")).toBeInTheDocument();
    expect(within(empresa).getByText("Precision (2)")).toBeInTheDocument();
  });

  it("o Estado das Revisões só tem «Indexado»", async () => {
    montar("/index?idx_tab=reviews");
    await screen.findByText("Ana");
    const estado = screen.getByLabelText("Estado");
    expect(within(estado).getAllByRole("option").map((o) => o.textContent)).toEqual(["Todos", "Indexado"]);
    expect(within(screen.getByLabelText("Ordenar por")).queryByText(/^Entrada/)).toBeNull();
  });

  it("limpar filtros tira-os do URL e mantém a ordem", async () => {
    const user = userEvent.setup();
    montar("/index?idx_sort=client_asc&idx_status=pending&idx_company=c-power");
    await screen.findByText("Ana");
    expect(ultimo()).toMatchObject({ sort_by: "client_asc", index_status: "pending", company_id: "c-power" });
    await user.click(screen.getByTestId("limpar-filtros-da-fila"));
    await waitFor(() => expect(ultimo().company_id).toBeUndefined());
    expect(ultimo()).toMatchObject({ sort_by: "client_asc" });
    expect(screen.getByTestId("localizacao")).toHaveTextContent("idx_sort=client_asc");
    expect(screen.getByTestId("localizacao").textContent).not.toContain("idx_status");
    expect(screen.queryByTestId("limpar-filtros-da-fila")).toBeNull();
  });
});

describe("o URL manda", () => {
  it("abrir já com ordem e filtros pede-os e pré-selecciona os controlos", async () => {
    montar("/index?idx_sort=number_desc&idx_origin=own&idx_company=c-power");
    await screen.findByText("Ana");
    expect(ultimo()).toMatchObject({ sort_by: "number_desc", origin: "own", company_id: "c-power" });
    expect(screen.getByLabelText("Ordenar por")).toHaveValue("number_desc");
    expect(screen.getByLabelText("Origem")).toHaveValue("own");
    expect(screen.getByLabelText("Empresa")).toHaveValue("c-power");
  });

  it("valores inventados no URL caem na omissão e nunca vão ao servidor", async () => {
    montar("/index?idx_sort=hacker&idx_status=indexed&idx_origin=todas");
    await screen.findByText("Ana");
    expect(ultimo().sort_by).toBeUndefined();
    expect(ultimo().index_status).toBeUndefined();
    expect(ultimo().origin).toBeUndefined();
  });

  it("uma ordem de outra aba (indexed_* na Fila) cai na omissão em vez de dar 422", async () => {
    montar("/index?idx_sort=indexed_asc");
    await screen.findByText("Ana");
    expect(ultimo().sort_by).toBeUndefined();
  });

  it("mudar de aba larga a ordem e o estado (são de cada aba) e mantém empresa e origem", async () => {
    const user = userEvent.setup();
    montar("/index?idx_sort=client_asc&idx_status=pending&idx_company=c-power&idx_origin=own");
    await screen.findByText("Ana");
    await user.click(screen.getByRole("tab", { name: "Revisões Pendentes" }));
    await waitFor(() => expect(ultimo().tab).toBe("reviews"));
    const url = screen.getByTestId("localizacao").textContent;
    expect(url).not.toContain("idx_sort");
    expect(url).not.toContain("idx_status");
    expect(url).toContain("idx_company=c-power");
    expect(url).toContain("idx_origin=own");
  });
});

describe("sem resultados", () => {
  it("com um filtro ligado diz que são os filtros, não que a fila está vazia", async () => {
    getIndexQueue.mockResolvedValue(resposta([]));
    montar("/index?idx_origin=shared");
    expect(await screen.findByText("Nenhum processo com estes filtros")).toBeInTheDocument();
    expect(screen.queryByText("Nada por tratar")).toBeNull();
  });

  it("sem filtros continua a ser «Nada por tratar»", async () => {
    getIndexQueue.mockResolvedValue(resposta([]));
    montar();
    expect(await screen.findByText("Nada por tratar")).toBeInTheDocument();
  });

  it("um filtro de empresa que já não está nas opções continua visível", async () => {
    getIndexQueue.mockResolvedValue(resposta([item("1", "Ana")]));
    montar("/index?idx_company=c-velha");
    await screen.findByText("Ana");
    expect(screen.getByLabelText("Empresa")).toHaveValue("c-velha");
    expect(within(screen.getByLabelText("Empresa")).getByText("Empresa do filtro activo")).toBeInTheDocument();
  });
});
