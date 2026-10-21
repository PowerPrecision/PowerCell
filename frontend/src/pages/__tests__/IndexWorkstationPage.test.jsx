/**
 * A bancada do Index MONTADA (Lote 12, Fase 4).
 *
 * O que se prova aqui, e porquê:
 *  · «Marcar como Indexado» NUNCA é bloqueado pelo conteúdo da análise — o fixture tem campos
 *    em dúvida, alertas abertos, NIF em falta E um job de IA a correr, e o botão está activo;
 *  · o diálogo dos NIFs é opcional: «Marcar sem confirmar NIF» está sempre à mão;
 *  · só se envia o que mudou na edição (a mutação «envia o formulário inteiro» tem de morrer);
 *  · um erro de LEITURA diz-se, e um 404 não oferece «Tentar de novo».
 *
 * A forma dos dados é a REAL do `GET /api/index/processes/{id}` (`index_api.run_get_index_workstation`).
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));
vi.mock("../../hooks/useTaskEvents", () => ({
  useTaskEvents: () => ({ isConnected: false }),
  TASK_SOURCE: { TASK_LOG: "task_log", BACKGROUND_JOB: "background_job" },
}));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("../../services/api", () => ({
  getIndexWorkstation: vi.fn(),
  claimIndexProcess: vi.fn(),
  releaseIndexProcess: vi.fn(),
  analyzeIndexProcess: vi.fn(),
  extractIndexProcess: vi.fn(),
  editIndexJob: vi.fn(),
  dismissIndexAlert: vi.fn(),
  sanitizeIndexProcess: vi.fn(),
  markIndexProcessIndexed: vi.fn(),
  searchIndexEmployers: vi.fn(),
}));

import * as api from "../../services/api";
import IndexWorkstationPage from "../index/IndexWorkstationPage";

const campo = (value, extra = {}) => ({ value, needs_review: false, edited_by_human: false, confidence: "alta", ...extra });

const BANCADA = {
  process: {
    id: "proc-1", process_number: 4711, client_name: "Marta Quintela", status: "indexacao", created_at: "2026-10-03",
    index_status: "pending", index_skipped: false, has_pending_review: true, index_alerts_open: 2,
    documents_total: 3, documents_to_analyse: 1,
  },
  files: [
    { id: "d1", filename: "recibo_setembro.pdf", category: "Rendimentos", analysis_type: "recibo_vencimento", analysed: true, file_state: "original" },
    { id: "d2", filename: "extrato_setembro.pdf", category: "Bancários", analysis_type: "extrato_bancario", analysed: false, file_state: "original" },
    { id: "d3", filename: "foto.jpg", analysis_type: null, analysed: false, file_state: "original" },
  ],
  professional_metadata: {
    jobs: [
      {
        job_id: "job_a", period: "2026-09",
        employer_nif: campo(null, { needs_review: true }),
        employer_name: campo("Quinta do Sol Lda"),
        job_title: campo(null, { needs_review: true }),
        net_salary: campo("1873.45"),
        contract_type: campo("termo_certo"),
      },
    ],
    has_pending_review: true,
  },
  alerts: [
    { id: "al-1", code: "contas_nao_batem", severity: "aviso", message: "As contas de um recibo não batem certo (bruto, descontos e líquido).", dismissed: false, period: "2026-09" },
    { id: "al-2", code: "nif_invalido", severity: "alerta", message: "O NIF da entidade patronal não é válido.", dismissed: false },
  ],
  active_jobs: { analysis: "t-9", finalize: null, sanitize: null },
};

function montar(bancada = BANCADA) {
  api.getIndexWorkstation.mockResolvedValue({ data: bancada });
  const cliente = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={cliente}>
      <MemoryRouter initialEntries={["/index/proc-1"]}>
        <Routes>
          <Route path="/index/:processId" element={<IndexWorkstationPage />} />
          <Route path="/index" element={<div data-testid="fila" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  Object.values(toast).forEach((f) => f.mockReset());
  api.searchIndexEmployers.mockResolvedValue({ data: { items: [] } });
  api.markIndexProcessIndexed.mockResolvedValue({ data: { success: true, employers: { applied: 0, rejected: [] } } });
  api.editIndexJob.mockResolvedValue({ data: { success: true } });
  api.dismissIndexAlert.mockResolvedValue({ data: { success: true } });
  api.analyzeIndexProcess.mockResolvedValue({ data: { success: true, message: "A correr." } });
});

describe("a bancada monta e mostra o estado do servidor", () => {
  it("cabeçalho, documentos, metadados e matriz", async () => {
    montar();
    expect(await screen.findByRole("heading", { name: /Marta Quintela/ })).toBeInTheDocument();
    expect(screen.getByText("Processo #4711")).toBeInTheDocument();
    expect(screen.getAllByTestId("ficheiro-do-index")).toHaveLength(3);
    expect(screen.getByText("recibo_setembro.pdf")).toBeInTheDocument();
    // o recibo está analisado, o extrato não, a foto nem é analisável
    const lista = screen.getAllByTestId("ficheiro-do-index");
    expect(within(lista[0]).getByText("Analisado")).toBeInTheDocument();
    expect(within(lista[1]).getByText("Por analisar")).toBeInTheDocument();
    expect(within(lista[2]).queryByText(/analisa/i)).not.toBeInTheDocument();
    expect(screen.getByText("Quinta do Sol Lda")).toBeInTheDocument();
    expect(screen.getByText(/2 campo\(s\) a rever/)).toBeInTheDocument();
    expect(screen.getAllByTestId("alerta-do-index")).toHaveLength(2);
  });

  it("os alertas graves vêm primeiro", async () => {
    montar();
    await screen.findByTestId("alert-matrix");
    const itens = screen.getAllByTestId("alerta-do-index");
    expect(within(itens[0]).getByText("Alerta")).toBeInTheDocument();
    expect(within(itens[1]).getByText("Aviso")).toBeInTheDocument();
  });

  it("mostra que há um job a correr", async () => {
    montar();
    expect(await screen.findByTestId("index-job-activo")).toBeInTheDocument();
  });
});

describe("«Marcar como Indexado» nunca é bloqueado", () => {
  it("activo com campos em dúvida, alertas abertos, NIF em falta e um job de IA a correr", async () => {
    montar();
    const botao = await screen.findByRole("button", { name: "Marcar como Indexado" });
    expect(botao).toBeEnabled();
  });

  it("Analisar e Extrair ficam desligados enquanto há job, Marcar não", async () => {
    montar();
    await screen.findByTestId("index-job-activo");
    expect(screen.getByRole("button", { name: "Analisar" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Extrair dados" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Marcar como Indexado" })).toBeEnabled();
  });

  it("sem job activo, Analisar corre sem forçar e Extrair força", async () => {
    montar({ ...BANCADA, active_jobs: { analysis: null, finalize: null, sanitize: null } });
    api.extractIndexProcess.mockResolvedValue({ data: { success: true, message: "A extrair." } });
    await userEvent.click(await screen.findByRole("button", { name: "Analisar" }));
    await waitFor(() => expect(api.analyzeIndexProcess).toHaveBeenCalledWith("proc-1", false));
    await userEvent.click(screen.getByRole("button", { name: "Extrair dados" }));
    await waitFor(() => expect(api.extractIndexProcess).toHaveBeenCalledWith("proc-1"));
  });

  it("com NIFs por confirmar pergunta-se; «Marcar sem confirmar NIF» marca na mesma", async () => {
    montar();
    await userEvent.click(await screen.findByRole("button", { name: "Marcar como Indexado" }));
    const dialogo = await screen.findByRole("dialog");
    expect(within(dialogo).getByText(/É opcional/)).toBeInTheDocument();
    await userEvent.click(within(dialogo).getByRole("button", { name: "Marcar sem confirmar NIF" }));
    await waitFor(() => expect(api.markIndexProcessIndexed).toHaveBeenCalledWith("proc-1", []));
  });

  it("um NIF com forma de NIF vai com o job_id; um sem forma é ignorado", async () => {
    montar();
    await userEvent.click(await screen.findByRole("button", { name: "Marcar como Indexado" }));
    const dialogo = await screen.findByRole("dialog");
    await userEvent.type(within(dialogo).getByLabelText("Quinta do Sol Lda"), "501 964 843");
    await userEvent.click(within(dialogo).getByRole("button", { name: "Marcar como indexado" }));
    await waitFor(() =>
      expect(api.markIndexProcessIndexed).toHaveBeenCalledWith("proc-1", [{ job_id: "job_a", nif: "501964843" }]),
    );
  });

  it("«Marcar sem confirmar NIF» ignora o que se escreveu: é a saída que nunca envia NIFs", async () => {
    montar();
    await userEvent.click(await screen.findByRole("button", { name: "Marcar como Indexado" }));
    const dialogo = await screen.findByRole("dialog");
    await userEvent.type(within(dialogo).getByLabelText("Quinta do Sol Lda"), "501964843");
    await userEvent.click(within(dialogo).getByRole("button", { name: "Marcar sem confirmar NIF" }));
    await waitFor(() => expect(api.markIndexProcessIndexed).toHaveBeenCalledWith("proc-1", []));
  });

  it("um NIF incompleto não é enviado, mas a indexação segue", async () => {
    montar();
    await userEvent.click(await screen.findByRole("button", { name: "Marcar como Indexado" }));
    const dialogo = await screen.findByRole("dialog");
    await userEvent.type(within(dialogo).getByLabelText("Quinta do Sol Lda"), "5019");
    await userEvent.click(within(dialogo).getByRole("button", { name: "Marcar como indexado" }));
    await waitFor(() => expect(api.markIndexProcessIndexed).toHaveBeenCalledWith("proc-1", []));
  });

  it("sem NIFs por confirmar marca logo, sem diálogo", async () => {
    const limpa = {
      ...BANCADA,
      professional_metadata: { jobs: [{ ...BANCADA.professional_metadata.jobs[0], employer_nif: campo("501964843") }], has_pending_review: false },
    };
    montar(limpa);
    await userEvent.click(await screen.findByRole("button", { name: "Marcar como Indexado" }));
    await waitFor(() => expect(api.markIndexProcessIndexed).toHaveBeenCalledWith("proc-1", []));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("um processo já indexado não oferece marcar outra vez", async () => {
    montar({ ...BANCADA, process: { ...BANCADA.process, index_status: "indexed" } });
    expect(await screen.findByRole("button", { name: "Indexado" })).toBeDisabled();
  });

  it("uma recusa do servidor mostra o MOTIVO e a página continua", async () => {
    api.markIndexProcessIndexed.mockRejectedValue({ response: { status: 403, data: { detail: "Apenas utilizadores com perfil de Indexação…" } } });
    montar({ ...BANCADA, professional_metadata: { jobs: [], has_pending_review: false } });
    await userEvent.click(await screen.findByRole("button", { name: "Marcar como Indexado" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Apenas utilizadores com perfil de Indexação…"));
    expect(screen.getByRole("button", { name: "Marcar como Indexado" })).toBeEnabled();
  });
});

describe("edição humana no painel lateral", () => {
  it("só envia o campo que mudou", async () => {
    montar();
    await userEvent.click(await screen.findByRole("button", { name: /Rever/ }));
    const painel = await screen.findByTestId("painel-de-revisao");
    const cargo = within(painel).getByLabelText("Cargo");
    await userEvent.type(cargo, "Analista Sénior");
    await userEvent.click(within(painel).getByRole("button", { name: "Guardar alterações" }));
    await waitFor(() => expect(api.editIndexJob).toHaveBeenCalledTimes(1));
    expect(api.editIndexJob).toHaveBeenCalledWith("proc-1", "job_a", { job_title: "Analista Sénior" });
  });

  it("sem alterações não há nada para guardar", async () => {
    montar();
    await userEvent.click(await screen.findByRole("button", { name: /Rever/ }));
    const painel = await screen.findByTestId("painel-de-revisao");
    expect(within(painel).getByRole("button", { name: "Guardar alterações" })).toBeDisabled();
  });

  it("«Confirmar como está» reenvia os campos em dúvida", async () => {
    montar();
    await userEvent.click(await screen.findByRole("button", { name: /Rever/ }));
    const painel = await screen.findByTestId("painel-de-revisao");
    await userEvent.click(within(painel).getByRole("button", { name: "Confirmar como está" }));
    await waitFor(() =>
      expect(api.editIndexJob).toHaveBeenCalledWith("proc-1", "job_a", { employer_nif: null, job_title: null }),
    );
  });

  it("os campos em dúvida dizem «A rever»", async () => {
    montar();
    await userEvent.click(await screen.findByRole("button", { name: /Rever/ }));
    const painel = await screen.findByTestId("painel-de-revisao");
    expect(within(within(painel).getByTestId("campo-job_a-job_title")).getByText("A rever")).toBeInTheDocument();
    expect(within(within(painel).getByTestId("campo-job_a-employer_name")).queryByText("A rever")).not.toBeInTheDocument();
  });
});

describe("PDF limpo («Apagar metadados»)", () => {
  const COM_FICHEIROS_DO_INDEX = {
    ...BANCADA,
    active_jobs: { analysis: null, finalize: null, sanitize: null },
    files: [
      { id: "d1", filename: "recibo.pdf", analysis_type: "recibo_vencimento", analysed: true, file_state: "original", uploaded_by_index: true },
      { id: "d2", filename: "extrato.pdf", analysis_type: "extrato_bancario", analysed: true, file_state: "sanitizado",
        has_clean_pdf: true, purge_after: "2026-11-20T12:00:00+00:00", uploaded_by_index: true },
      { id: "d3", filename: "extrato_limpo.pdf", file_state: "original", is_clean_pdf: true, has_clean_pdf: false },
    ],
  };

  it("com ficheiros do Index por limpar, o botão chama o servidor", async () => {
    api.sanitizeIndexProcess.mockResolvedValue({ data: { success: true, message: "A gerar." } });
    montar(COM_FICHEIROS_DO_INDEX);
    await userEvent.click(await screen.findByRole("button", { name: "Apagar metadados" }));
    await waitFor(() => expect(api.sanitizeIndexProcess).toHaveBeenCalledWith("proc-1"));
    expect(toast.info).toHaveBeenCalledWith("A gerar.");
  });

  it("sem nada por limpar o botão está desligado e di-lo", async () => {
    montar({ ...COM_FICHEIROS_DO_INDEX, files: COM_FICHEIROS_DO_INDEX.files.slice(1) });
    const botao = await screen.findByRole("button", { name: "Apagar metadados" });
    expect(botao).toBeDisabled();
    expect(botao).toHaveAttribute("title", expect.stringContaining("por limpar"));
  });

  it("os ficheiros que o cliente carregou não contam", async () => {
    montar({ ...COM_FICHEIROS_DO_INDEX, files: [{ ...COM_FICHEIROS_DO_INDEX.files[0], uploaded_by_index: false }] });
    expect(await screen.findByRole("button", { name: "Apagar metadados" })).toBeDisabled();
  });

  it("enquanto há um job activo fica desligado", async () => {
    montar({ ...COM_FICHEIROS_DO_INDEX, active_jobs: { analysis: null, finalize: null, sanitize: "t-5" } });
    expect(await screen.findByRole("button", { name: "Apagar metadados" })).toBeDisabled();
  });

  it("a margem de segurança vê-se: quando o original deixa de existir", async () => {
    montar(COM_FICHEIROS_DO_INDEX);
    await screen.findByText("recibo.pdf");
    const estados = screen.getAllByTestId("estado-do-ficheiro").map((e) => e.textContent);
    expect(estados).toContain("Tem PDF limpo — o original é eliminado a partir de 20/11/2026");
    expect(estados).toContain("PDF limpo (sem metadados)");
  });

  it("o PDF limpo não é «por analisar»", async () => {
    montar({ ...COM_FICHEIROS_DO_INDEX, files: [{ ...COM_FICHEIROS_DO_INDEX.files[2], analysis_type: null }] });
    await screen.findByText("extrato_limpo.pdf");
    expect(screen.queryByText("Por analisar")).not.toBeInTheDocument();
  });

  it("uma recusa mostra o motivo", async () => {
    api.sanitizeIndexProcess.mockRejectedValue({ response: { status: 403, data: { detail: "Sem permissão." } } });
    montar(COM_FICHEIROS_DO_INDEX);
    await userEvent.click(await screen.findByRole("button", { name: "Apagar metadados" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Sem permissão."));
  });
});

describe("alertas", () => {
  it("dispensar chama o servidor com o alerta certo", async () => {
    montar();
    await screen.findByTestId("alert-matrix");
    await userEvent.click(screen.getByRole("button", { name: /Dispensar alerta: O NIF da entidade patronal/ }));
    await waitFor(() => expect(api.dismissIndexAlert).toHaveBeenCalledWith("proc-1", "al-2"));
  });
});

describe("erros de leitura", () => {
  it("um erro de rede diz-se e oferece tentar de novo", async () => {
    api.getIndexWorkstation.mockRejectedValue({ response: { status: 500 } });
    const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={cliente}>
        <MemoryRouter initialEntries={["/index/proc-1"]}>
          <Routes><Route path="/index/:processId" element={<IndexWorkstationPage />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByTestId("index-bancada-erro")).toHaveTextContent("Não foi possível carregar o processo");
    expect(screen.getByRole("button", { name: /tentar de novo/i })).toBeInTheDocument();
  });

  it("um 404 diz que não existe e NÃO oferece tentar de novo", async () => {
    api.getIndexWorkstation.mockRejectedValue({ response: { status: 404 } });
    const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={cliente}>
        <MemoryRouter initialEntries={["/index/proc-1"]}>
          <Routes><Route path="/index/:processId" element={<IndexWorkstationPage />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByTestId("index-bancada-erro")).toHaveTextContent("Processo não encontrado");
    expect(screen.queryByRole("button", { name: /tentar de novo/i })).not.toBeInTheDocument();
  });

  it("voltar à fila navega para /index", async () => {
    montar();
    await userEvent.click(await screen.findByRole("button", { name: /Voltar à fila/ }));
    expect(await screen.findByTestId("fila")).toBeInTheDocument();
  });
});

describe("recusas do servidor nas acções de estado", () => {
  it("reivindicar a falhar mostra o motivo", async () => {
    api.claimIndexProcess.mockRejectedValue({ response: { status: 409, data: { detail: "Já está em tratamento." } } });
    montar();
    await userEvent.click(await screen.findByRole("button", { name: "Reivindicar" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Já está em tratamento."));
  });

  it("editar a falhar (422) mostra o motivo e o painel continua aberto", async () => {
    api.editIndexJob.mockRejectedValue({ response: { status: 422, data: { detail: "O vencimento líquido não é um valor válido." } } });
    montar();
    await userEvent.click(await screen.findByRole("button", { name: /Rever/ }));
    const painel = await screen.findByTestId("painel-de-revisao");
    await userEvent.type(within(painel).getByLabelText("Cargo"), "x");
    await userEvent.click(within(painel).getByRole("button", { name: "Guardar alterações" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("O vencimento líquido não é um valor válido."));
    expect(screen.getByTestId("painel-de-revisao")).toBeInTheDocument();
  });
});

describe("estado do processo", () => {
  it("«Reivindicar» só em pending; «Devolver à fila» só em in_review", async () => {
    api.claimIndexProcess.mockResolvedValue({ data: { success: true } });
    const { unmount } = montar();
    await userEvent.click(await screen.findByRole("button", { name: "Reivindicar" }));
    await waitFor(() => expect(api.claimIndexProcess).toHaveBeenCalledWith("proc-1"));
    expect(screen.queryByRole("button", { name: "Devolver à fila" })).not.toBeInTheDocument();
    unmount();
    montar({ ...BANCADA, process: { ...BANCADA.process, index_status: "in_review" } });
    expect(await screen.findByRole("button", { name: "Devolver à fila" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reivindicar" })).not.toBeInTheDocument();
  });
});
