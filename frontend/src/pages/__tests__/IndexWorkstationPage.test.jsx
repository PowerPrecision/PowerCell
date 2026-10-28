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
const sessao = vi.hoisted(() => ({ papel: null }));
vi.mock("../../contexts/AuthContext", () => ({
  useAuthOpcional: () => (sessao.papel ? { effectiveRole: sessao.papel, user: { role: "consultor" } } : null),
}));
const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock("sonner", () => ({ toast }));
vi.mock("../../services/api", () => ({
  getIndexWorkstation: vi.fn(),
  startIndexWork: vi.fn(),
  assumirIndexProcess: vi.fn(),
  getIndexProcessFileContent: vi.fn(),
  getIndexDocumentContent: vi.fn(),
  uploadProcessS3File: vi.fn(),
  readBlobErrorBody: vi.fn(async () => null),
  analyzeIndexProcess: vi.fn(),
  analyzeIndexFile: vi.fn(),
  extractIndexProcess: vi.fn(),
  editIndexJob: vi.fn(),
  dismissIndexAlert: vi.fn(),
  setIndexFileTitular: vi.fn(),
  sanitizeIndexProcess: vi.fn(),
  markIndexProcessIndexed: vi.fn(),
  searchIndexEmployers: vi.fn(),
  getIndexConversa: vi.fn(async () => ({ data: { interlocutor: null, messages: [] } })),
  sendIndexConversa: vi.fn(),
  getProcessConversaIndex: vi.fn(),
  sendProcessConversaIndex: vi.fn(),
}));

import * as api from "../../services/api";
import apiFonte from "../../services/api.js?raw";
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
    { id: "al-1", code: "contas_nao_batem", severity: "aviso", message: "As contas de um recibo não batem certo (bruto, descontos e líquido).", detail: "Recibo de 09/2026: ilíquido 2.100,00 € − descontos 200,00 € dá 1.900,00 €, mas o líquido indicado é 1.873,45 € (diferença de 26,55 €).", dismissed: false, period: "2026-09" },
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
  sessao.papel = null;
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
    expect(screen.getByTestId("ligacao-numero")).toHaveTextContent("#4711");
    expect(screen.getAllByTestId("ficheiro-do-index")).toHaveLength(3);
    expect(screen.getByText("recibo_setembro.pdf")).toBeInTheDocument();
    // o recibo está analisado, o extrato não, a foto nem é analisável
    const lista = screen.getAllByTestId("ficheiro-do-index");
    expect(within(lista[0]).getByText("Analisado")).toBeInTheDocument();
    expect(within(lista[1]).getByText("Por analisar")).toBeInTheDocument();
    expect(within(lista[2]).queryByText(/^(Por analisar|Analisado)$/)).not.toBeInTheDocument();
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

  it("o ecrã de erro também já não oferece «Voltar à fila»", async () => {
    sessao.papel = "diretor";
    api.getIndexWorkstation.mockRejectedValue({ response: { status: 500 } });
    const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={cliente}>
        <MemoryRouter initialEntries={["/index/proc-1"]}>
          <Routes><Route path="/index/:processId" element={<IndexWorkstationPage />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    await screen.findByTestId("index-bancada-erro");
    expect(screen.queryByText(/Voltar à fila/i)).not.toBeInTheDocument();
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
});

describe("recusas do servidor nas acções de estado", () => {
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

describe("já não há «Reivindicar» nem «Devolver à fila» (Out 2026)", () => {
  it.each(["pending", "in_review"])("em %s a bancada não tem nenhum dos dois botões", async (estado) => {
    montar({ ...BANCADA, process: { ...BANCADA.process, index_status: estado } });
    await screen.findByRole("heading", { name: /Marta Quintela/ });
    expect(screen.queryByRole("button", { name: /reivindicar/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /devolver à fila/i })).not.toBeInTheDocument();
  });

  it("o cliente da API já não tem o claim/release (apagados, não escondidos)", () => {
    const fonte = apiFonte.split("\n").filter((l) => !l.trim().startsWith("//")).join("\n");
    expect(fonte).not.toMatch(/claimIndexProcess|releaseIndexProcess|\/claim`|\/release`/);
    expect(fonte).toMatch(/startIndexWork/); // contraprova: o leitor vê o módulo
  });
});

describe("abrir a bancada é começar a trabalhar", () => {
  const DELE = { ...BANCADA, process: { ...BANCADA.process, index_status: "pending", assigned_to_me: true } };

  it("o indexador a quem o processo está atribuído arranca o tratamento, uma só vez", async () => {
    api.startIndexWork.mockResolvedValue({ data: { success: true, iniciado: true, registado: true } });
    const { rerender } = montar(DELE);
    await screen.findByRole("heading", { name: /Marta Quintela/ });
    await waitFor(() => expect(api.startIndexWork).toHaveBeenCalledTimes(1));
    expect(api.startIndexWork).toHaveBeenCalledWith("proc-1");
    expect(rerender).toBeDefined();
  });

  it("depois de arrancar refaz a leitura da bancada (o estado passou a «em tratamento»)", async () => {
    api.startIndexWork.mockResolvedValue({ data: { success: true, iniciado: true, registado: true } });
    montar(DELE);
    await screen.findByRole("heading", { name: /Marta Quintela/ });
    await waitFor(() => expect(api.getIndexWorkstation.mock.calls.length).toBeGreaterThan(1));
  });

  it("quem não é o atribuído (um diretor a espreitar) NÃO inicia nada", async () => {
    montar({ ...BANCADA, process: { ...BANCADA.process, index_status: "pending", assigned_to_me: false } });
    await screen.findByRole("heading", { name: /Marta Quintela/ });
    expect(api.startIndexWork).not.toHaveBeenCalled();
  });

  it("um processo que já está em tratamento não pede outra vez", async () => {
    montar({ ...BANCADA, process: { ...BANCADA.process, index_status: "in_review", assigned_to_me: true } });
    await screen.findByRole("heading", { name: /Marta Quintela/ });
    expect(api.startIndexWork).not.toHaveBeenCalled();
  });

  it("uma falha do pedido não estraga a bancada nem mostra erro", async () => {
    api.startIndexWork.mockRejectedValue({ response: { status: 500 } });
    montar(DELE);
    expect(await screen.findByRole("heading", { name: /Marta Quintela/ })).toBeInTheDocument();
    await waitFor(() => expect(api.startIndexWork).toHaveBeenCalled());
    expect(toast.error).not.toHaveBeenCalled();
  });
});

describe("documentos: Ver, Download e Upload sem sair da bancada", () => {
  let descargas;
  beforeEach(() => {
    descargas = [];
    URL.createObjectURL = vi.fn(() => "blob:teste");
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function click() {
      descargas.push({ href: this.href, download: this.download });
    });
  });

  it("cada linha tem «Ver documento» e «Download» com o nome do ficheiro", async () => {
    montar();
    const linhas = await screen.findAllByTestId("ficheiro-do-index");
    expect(linhas).toHaveLength(3);
    for (const [i, nome] of ["recibo_setembro.pdf", "extrato_setembro.pdf", "foto.jpg"].entries()) {
      expect(within(linhas[i]).getByRole("button", { name: `Ver documento — ${nome}` })).toBeInTheDocument();
      expect(within(linhas[i]).getByRole("button", { name: `Download — ${nome}` })).toBeInTheDocument();
    }
  });

  it("«Download» pede o ficheiro DESTE processo com download:true e guarda-o", async () => {
    api.getIndexProcessFileContent.mockResolvedValue({
      data: new Blob(["x"], { type: "application/pdf" }), headers: { "content-type": "application/pdf" },
    });
    montar();
    const linha = (await screen.findAllByTestId("ficheiro-do-index"))[0];
    await userEvent.click(within(linha).getByTestId("ficheiro-download"));
    await waitFor(() => expect(api.getIndexProcessFileContent).toHaveBeenCalledWith("proc-1", "d1", { download: true }));
    await waitFor(() => expect(descargas).toHaveLength(1));
    expect(descargas[0].download).toMatch(/recibo_setembro.*\.pdf$/);
    expect(api.getIndexDocumentContent).not.toHaveBeenCalled(); // o endpoint da pesquisa não serve a bancada
  });

  it("«Ver» abre o ficheiro DESTE processo num diálogo sem sair da página", async () => {
    api.getIndexProcessFileContent.mockResolvedValue({
      data: new Blob(["x"], { type: "application/pdf" }), headers: { "content-type": "application/pdf" },
    });
    montar();
    const linha = (await screen.findAllByTestId("ficheiro-do-index"))[1];
    await userEvent.click(within(linha).getByTestId("ficheiro-ver"));
    await waitFor(() => expect(api.getIndexProcessFileContent).toHaveBeenCalledWith("proc-1", "d2"));
    expect(await screen.findByTestId("visualizador-corpo")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /Marta Quintela/, hidden: true })).toBeInTheDocument(); // continua na bancada
  });

  it("um erro do servidor ao descarregar di-lo", async () => {
    api.getIndexProcessFileContent.mockRejectedValue({ response: { status: 404 } });
    montar();
    const linha = (await screen.findAllByTestId("ficheiro-do-index"))[0];
    await userEvent.click(within(linha).getByTestId("ficheiro-download"));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
  });

  it("o upload directo está na aba: escolher um ficheiro envia-o para ESTE processo e refaz a lista", async () => {
    api.uploadProcessS3File.mockResolvedValue({ data: { success: true } });
    montar();
    await screen.findAllByTestId("ficheiro-do-index");
    const chamadasAntes = api.getIndexWorkstation.mock.calls.length;
    const entrada = screen.getByTestId("upload-bancada-entrada");
    await userEvent.upload(entrada, new File(["%PDF"], "novo_recibo.pdf", { type: "application/pdf" }));
    await waitFor(() => expect(api.uploadProcessS3File).toHaveBeenCalledTimes(1));
    expect(api.uploadProcessS3File.mock.calls[0][0]).toBe("proc-1");
    expect(api.uploadProcessS3File.mock.calls[0][1].get("file").name).toBe("novo_recibo.pdf");
    await waitFor(() => expect(api.getIndexWorkstation.mock.calls.length).toBeGreaterThan(chamadasAntes));
    expect(await screen.findByText(/1 ficheiro adicionado/)).toBeInTheDocument();
  });
});

describe("a equipa do Index trabalha a partir de «Os Meus Processos»", () => {
  it.each(["diretor", "admin", "ceo", "master", "indexacao"])(
    "o botão «Voltar à fila» foi extinto — nem o perfil %s o vê",
    async (papel) => {
      sessao.papel = papel;
      montar();
      await screen.findAllByTestId("ficheiro-do-index");
      expect(screen.queryByRole("button", { name: /Voltar à fila/i })).not.toBeInTheDocument();
      expect(screen.queryByRole("link", { name: /Voltar à fila/i })).not.toBeInTheDocument();
      expect(screen.queryByText(/Voltar à fila/i)).not.toBeInTheDocument();
    },
  );

  it("a gestão não tem botão de regresso (volta pelo menu ou pelo «Voltar» do browser)", async () => {
    sessao.papel = "diretor";
    montar();
    await screen.findAllByTestId("ficheiro-do-index");
    expect(screen.queryByRole("button", { name: /Os meus processos/i })).not.toBeInTheDocument();
  });

  it("contraprova: o perfil Index continua a ter «Os meus processos»", async () => {
    sessao.papel = "indexacao";
    montar();
    await screen.findAllByTestId("ficheiro-do-index");
    expect(screen.getByRole("button", { name: /Os meus processos/i })).toBeInTheDocument();
  });

  it("o perfil Index volta a «Os meus processos» (a fila já não é dele)", async () => {
    sessao.papel = "indexacao";
    api.getIndexWorkstation.mockResolvedValue({ data: BANCADA });
    const cliente = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={cliente}>
        <MemoryRouter initialEntries={["/index/proc-1"]}>
          <Routes>
            <Route path="/index/:processId" element={<IndexWorkstationPage />} />
            <Route path="/processos" element={<div data-testid="meus-processos" />} />
            <Route path="/index" element={<div data-testid="fila" />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(screen.queryByRole("button", { name: /Voltar à fila/ })).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: /Os meus processos/ }));
    expect(await screen.findByTestId("meus-processos")).toBeInTheDocument();
    expect(screen.queryByTestId("fila")).not.toBeInTheDocument();
  });

  it("um processo parado há dias mostra o selo «Sem actividade»", async () => {
    montar({ ...BANCADA, process: { ...BANCADA.process, index_status: "in_review", stagnant: true } });
    expect(await screen.findByTestId("badge-estagnado")).toHaveTextContent("Sem actividade");
  });

  it("e não mostra o selo num processo normal", async () => {
    montar();
    await screen.findByRole("heading", { name: /Marta Quintela/ });
    expect(screen.queryByTestId("badge-estagnado")).not.toBeInTheDocument();
  });
});


describe("atalho para o processo original (QA Index, Out 2026)", () => {
  it("o nome do cliente e o número abrem o detalhe do processo NUM NOVO separador", async () => {
    montar();
    await screen.findByRole("heading", { name: /Marta Quintela/ });
    for (const id of ["ligacao-cliente", "ligacao-numero"]) {
      const ligacao = screen.getByTestId(id);
      expect(ligacao.tagName).toBe("A");
      expect(ligacao).toHaveAttribute("href", "/processo/proc-1");
      expect(ligacao).toHaveAttribute("target", "_blank");
      // sem `noopener` o separador aberto pode mexer na bancada (window.opener)
      expect(ligacao.getAttribute("rel")).toMatch(/noopener/);
      expect(ligacao.getAttribute("rel")).toMatch(/noreferrer/);
    }
  });

  it("diz a quem usa um leitor de ecrã que abre noutro separador", async () => {
    montar();
    await screen.findByRole("heading", { name: /Marta Quintela/ });
    expect(screen.getByRole("link", { name: /Marta Quintela.*novo separador/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /#4711.*novo separador/ })).toBeInTheDocument();
  });

  it("sem número de processo não há ligação do número (nem texto solto)", async () => {
    montar({ ...BANCADA, process: { ...BANCADA.process, process_number: null } });
    await screen.findByRole("heading", { name: /Marta Quintela/ });
    expect(screen.queryByTestId("ligacao-numero")).not.toBeInTheDocument();
    expect(screen.getByTestId("ligacao-cliente")).toBeInTheDocument();
  });

  it("clicar na ligação não navega esta página (o separador é outro)", async () => {
    montar();
    await userEvent.click(await screen.findByTestId("ligacao-cliente"));
    expect(screen.getByRole("heading", { name: /Marta Quintela/ })).toBeInTheDocument();
    expect(screen.queryByTestId("fila")).not.toBeInTheDocument();
  });
});

describe("a justificação exacta de cada alerta", () => {
  it("aparece debaixo da mensagem, com o valor e a diferença", async () => {
    montar();
    const matriz = await screen.findByTestId("alert-matrix");
    const alertas = within(matriz).getAllByTestId("alerta-do-index");
    const comDetalhe = alertas.find((a) => within(a).queryByTestId("alerta-detalhe"));
    expect(comDetalhe).toBeDefined();
    const detalhe = within(comDetalhe).getByTestId("alerta-detalhe");
    expect(detalhe).toHaveTextContent("diferença de 26,55 €");
    // por baixo da mensagem genérica, não no lugar dela
    expect(within(comDetalhe).getByText(/As contas de um recibo não batem certo/)).toBeInTheDocument();
    expect(comDetalhe.textContent.indexOf("As contas de um recibo")).toBeLessThan(comDetalhe.textContent.indexOf("diferença de"));
  });

  it("um alerta sem justificação (histórico) continua a mostrar-se, sem caixa vazia", async () => {
    montar();
    const matriz = await screen.findByTestId("alert-matrix");
    const alertas = within(matriz).getAllByTestId("alerta-do-index");
    const sem = alertas.find((a) => !within(a).queryByTestId("alerta-detalhe"));
    expect(sem).toBeDefined();
    expect(sem).toHaveTextContent("O NIF da entidade patronal não é válido.");
  });

  it("o texto do servidor é texto: um detalhe com HTML não se interpreta", async () => {
    const bancada = { ...BANCADA, alerts: [{ ...BANCADA.alerts[0], detail: "<img src=x onerror=alert(1)> 100 €" }] };
    montar(bancada);
    const detalhe = await screen.findByTestId("alerta-detalhe");
    expect(detalhe.querySelector("img")).toBeNull();
    expect(detalhe.textContent).toContain("<img src=x");
  });
});

// Out 2026 — «Atribuir a mim»: o Index puxa um processo «Por indexar» que o colega ainda não abriu.
describe("«Atribuir a mim» na bancada", () => {
  const deOutro = (estado = "pending") => ({ ...BANCADA, process: { ...BANCADA.process, index_status: estado, assigned_to_me: false } });

  it("o Index vê o botão num processo por indexar de outro e assume-o", async () => {
    sessao.papel = "indexacao";
    api.assumirIndexProcess.mockResolvedValue({ data: { success: true } });
    const utilizador = userEvent.setup();
    montar(deOutro());
    await utilizador.click(await screen.findByTestId("botao-atribuir-a-mim"));
    await waitFor(() => expect(api.assumirIndexProcess).toHaveBeenCalledWith("proc-1"));
    expect(toast.success).toHaveBeenCalled();
  });

  it("não aparece num processo já em tratamento, nem no que já é seu, nem à gestão", async () => {
    sessao.papel = "indexacao";
    api.startIndexWork.mockResolvedValue({ data: { iniciado: false } });
    const { unmount } = montar(deOutro("in_review"));
    await screen.findByRole("heading", { name: /Marta Quintela/ });
    expect(screen.queryByTestId("botao-atribuir-a-mim")).not.toBeInTheDocument();
    unmount();

    const meu = montar({ ...BANCADA, process: { ...BANCADA.process, assigned_to_me: true } });
    await screen.findByRole("heading", { name: /Marta Quintela/ });
    expect(screen.queryByTestId("botao-atribuir-a-mim")).not.toBeInTheDocument();
    meu.unmount();

    sessao.papel = "diretor";
    montar(deOutro());
    await screen.findByRole("heading", { name: /Marta Quintela/ });
    expect(screen.queryByTestId("botao-atribuir-a-mim")).not.toBeInTheDocument();
  });
});

describe("sem acções cruzadas entre indexadores (Out 2026)", () => {
  const doColega = (estado = "in_review") => ({
    ...BANCADA,
    active_jobs: { analysis: null, finalize: null, sanitize: null },
    process: {
      ...BANCADA.process, index_status: estado, assigned_to_me: false, assigned_to_other: true,
      assigned_indexacao_name: "Rui Teixeira",
    },
  });
  const accoes = () => ["Analisar", "Extrair dados", "Apagar metadados", "Marcar como Indexado"]
    .map((nome) => screen.getByRole("button", { name: new RegExp(`^${nome}$`) }));

  it("no processo de um colega o Index lê tudo; só as acções ficam desligadas, com o motivo em tooltip", async () => {
    sessao.papel = "indexacao";
    api.startIndexWork.mockResolvedValue({ data: { iniciado: false } });
    montar(doColega());
    await screen.findByRole("heading", { name: /Marta Quintela/ });
    // a leitura é a normal: documentos, metadados e alertas, sem aviso a mudar o ecrã
    expect(screen.getAllByTestId("ficheiro-do-index")).toHaveLength(3);
    expect(screen.getByText("Quinta do Sol Lda")).toBeInTheDocument();
    expect(screen.getAllByTestId("alerta-do-index")).toHaveLength(2);
    expect(screen.queryByTestId("aviso-processo-de-outro")).not.toBeInTheDocument();
    accoes().forEach((b) => {
      expect(b).toBeDisabled();
      expect(b).toHaveAttribute("title", expect.stringContaining("Rui Teixeira"));
    });
    expect(screen.getByRole("toolbar", { name: "Acções do Index" })).toHaveAttribute("title", expect.stringContaining("Rui Teixeira"));
    expect(screen.getByRole("button", { name: /Rever/ })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Dispensar alerta/ })).not.toBeInTheDocument();
    // «Ver» continua à mão
    expect(screen.getAllByRole("button", { name: /Ver/ }).length).toBeGreaterThan(0);
  });

  it("por indexar, a tooltip aponta para «Atribuir a mim»", async () => {
    sessao.papel = "indexacao";
    montar(doColega("pending"));
    await screen.findByTestId("botao-atribuir-a-mim");
    expect(screen.getByRole("button", { name: /^Analisar$/ })).toHaveAttribute("title", expect.stringContaining("Atribuir a mim"));
  });

  it("contraprova: num processo sem indexador o Index age", async () => {
    sessao.papel = "indexacao";
    montar({ ...doColega("pending"), process: { ...doColega("pending").process, assigned_to_other: false } });
    await screen.findByRole("heading", { name: /Marta Quintela/ });
    expect(screen.getByRole("button", { name: /^Analisar$/ })).not.toHaveAttribute("title");
    expect(screen.getByRole("button", { name: /^Analisar$/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /^Marcar como Indexado$/ })).toBeEnabled();
  });

  it("contraprova: a gestão age no processo de qualquer indexador", async () => {
    sessao.papel = "diretor";
    montar(doColega());
    await screen.findByRole("heading", { name: /Marta Quintela/ });
    expect(screen.getByRole("button", { name: /^Marcar como Indexado$/ })).toBeEnabled();
    expect(screen.getAllByRole("button", { name: /Dispensar alerta/ }).length).toBeGreaterThan(0);
  });
});

describe("comprovativos do cliente substituídos pelos do Index (Out 2026)", () => {
  const COM_SUBSTITUIDO = {
    ...BANCADA,
    process: {
      ...BANCADA.process,
      titulares: [
        { id: "titular1", label: "1.º titular", nome: "Marta Quintela" },
        { id: "titular2", label: "2.º titular", nome: "Rui Quintela" },
      ],
    },
    files: [
      { ...BANCADA.files[0], id: "c1", filename: "scan_do_cliente.pdf", superseded: true, titular: "titular1" },
      { ...BANCADA.files[0], id: "i1", filename: "recibo_validado.pdf", uploaded_by_index: true, titular: "titular1" },
      { ...BANCADA.files[1], titular: "titular2" },
    ],
  };

  it("o substituído não aparece até o Index o pedir, e aí vem marcado", async () => {
    montar(COM_SUBSTITUIDO);
    await screen.findByRole("heading", { name: /Marta Quintela/ });
    expect(screen.getAllByTestId("ficheiro-do-index")).toHaveLength(2);
    expect(screen.queryByText("scan_do_cliente.pdf")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Ver os documentos do cliente substituídos (1)" }));
    expect(screen.getAllByTestId("ficheiro-do-index")).toHaveLength(3);
    const linha = screen.getByText("scan_do_cliente.pdf").closest("li");
    expect(within(linha).getByTestId("badge-substituido")).toHaveTextContent("Substituído");
    await userEvent.click(screen.getByRole("button", { name: "Esconder os documentos do cliente substituídos" }));
    expect(screen.getAllByTestId("ficheiro-do-index")).toHaveLength(2);
  });

  it("com 2.º titular cada ficheiro diz de quem é e o upload pergunta", async () => {
    montar(COM_SUBSTITUIDO);
    await screen.findByRole("heading", { name: /Marta Quintela/ });
    const seletores = screen.getAllByTestId("ficheiro-titular");
    expect(seletores.map((s) => s.value)).toEqual(["titular1", "titular2"]);
    expect(screen.getByRole("button", { name: "2.º titular · Rui Quintela" })).toBeInTheDocument();
  });

  it("o Index corrige o titular de um ficheiro (manda sobre a conta que o enviou)", async () => {
    sessao.papel = "indexacao";
    api.setIndexFileTitular.mockResolvedValue({ data: { success: true } });
    api.startIndexWork.mockResolvedValue({ data: { success: true } });
    montar({ ...COM_SUBSTITUIDO, process: { ...COM_SUBSTITUIDO.process, assigned_to_me: true } });
    await screen.findByRole("heading", { name: /Marta Quintela/ });
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "De quem é — recibo_validado.pdf" }), "titular2");
    await waitFor(() => expect(api.setIndexFileTitular).toHaveBeenCalledWith("proc-1", "i1", "titular2"));
    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining("Analisar"));
  });

  it("no processo de um colega o titular não se muda", async () => {
    sessao.papel = "indexacao";
    montar({ ...COM_SUBSTITUIDO, process: { ...COM_SUBSTITUIDO.process, assigned_to_other: true } });
    await screen.findByRole("heading", { name: /Marta Quintela/ });
    screen.getAllByTestId("ficheiro-titular").forEach((s) => expect(s).toBeDisabled());
  });

  it("cada emprego diz de que titular é", async () => {
    const comTitular = {
      ...COM_SUBSTITUIDO,
      professional_metadata: {
        ...BANCADA.professional_metadata,
        jobs: [{ ...BANCADA.professional_metadata.jobs[0], titular: "titular2" }],
      },
    };
    montar(comTitular);
    await screen.findByRole("heading", { name: /Marta Quintela/ });
    expect(screen.getByTestId("emprego-titular")).toHaveTextContent("2.º titular");
  });

  it("sem substituídos não há opção nenhuma", async () => {
    montar();
    await screen.findByRole("heading", { name: /Marta Quintela/ });
    expect(screen.queryByTestId("ver-substituidos")).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "De quem são os documentos" })).not.toBeInTheDocument();
  });
});

describe("«Analisar» na linha de cada ficheiro (QA Index, Out 2026)", () => {
  const SEM_JOB = { ...BANCADA, active_jobs: { analysis: null, finalize: null, sanitize: null } };
  const linhaDe = async (nome) =>
    (await screen.findByText(nome)).closest("[data-testid='ficheiro-do-index']");

  beforeEach(() => {
    api.analyzeIndexFile.mockResolvedValue({ data: { success: true, started: true, message: "A analisar o documento." } });
  });

  it("um ficheiro sem tipo reconhecido analisa-se aqui: o servidor deteta o tipo", async () => {
    montar(SEM_JOB);
    const linha = await linhaDe("foto.jpg");
    await userEvent.click(within(linha).getByRole("button", { name: "Analisar — foto.jpg" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Detetar o tipo e analisar" }));
    await waitFor(() => expect(api.analyzeIndexFile).toHaveBeenCalledWith("proc-1", "d3", null));
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith("A analisar o documento."));
  });

  it("«Analisar como…» envia o tipo escolhido pela pessoa", async () => {
    montar(SEM_JOB);
    const linha = await linhaDe("foto.jpg");
    await userEvent.click(within(linha).getByRole("button", { name: "Analisar — foto.jpg" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Recibo de vencimento" }));
    await waitFor(() => expect(api.analyzeIndexFile).toHaveBeenCalledWith("proc-1", "d3", "recibo_vencimento"));
  });

  it("um ficheiro com tipo oferece analisá-lo de novo", async () => {
    montar(SEM_JOB);
    const linha = await linhaDe("extrato_setembro.pdf");
    await userEvent.click(within(linha).getByRole("button", { name: "Analisar — extrato_setembro.pdf" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Analisar de novo (extrato bancário)" }));
    await waitFor(() => expect(api.analyzeIndexFile).toHaveBeenCalledWith("proc-1", "d2", null));
  });

  it("quando a última análise falhou, a linha di-lo", async () => {
    montar({ ...SEM_JOB, files: [{ ...SEM_JOB.files[1], analysis_failed: true }] });
    const linha = await linhaDe("extrato_setembro.pdf");
    expect(within(linha).getByTestId("badge-analise-falhou")).toHaveTextContent("Análise falhou");
    expect(within(linha).queryByText("Por analisar")).not.toBeInTheDocument();
  });

  it("com uma análise a correr fica desligado, com o motivo", async () => {
    montar(BANCADA);
    const linha = await linhaDe("foto.jpg");
    const botao = within(linha).getByRole("button", { name: "Analisar — foto.jpg" });
    expect(botao).toBeDisabled();
    expect(botao).toHaveAttribute("title", "Já há uma análise a correr neste processo.");
  });

  it("no processo de um colega fica desligado, como as outras acções", async () => {
    sessao.papel = "indexacao";
    api.startIndexWork.mockResolvedValue({ data: { iniciado: false } });
    montar({ ...SEM_JOB, process: { ...SEM_JOB.process, index_status: "in_review", assigned_to_other: true,
      assigned_indexacao_name: "Rui Teixeira" } });
    const linha = await linhaDe("foto.jpg");
    const botao = within(linha).getByRole("button", { name: "Analisar — foto.jpg" });
    expect(botao).toBeDisabled();
    expect(botao).toHaveAttribute("title", expect.stringContaining("Rui Teixeira"));
  });

  it("uma recusa mostra o motivo do servidor", async () => {
    api.analyzeIndexFile.mockRejectedValue({ response: { status: 422, data: { detail: "O PDF limpo não se analisa." } } });
    montar(SEM_JOB);
    const linha = await linhaDe("foto.jpg");
    await userEvent.click(within(linha).getByRole("button", { name: "Analisar — foto.jpg" }));
    await userEvent.click(await screen.findByRole("menuitem", { name: "Detetar o tipo e analisar" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("O PDF limpo não se analisa."));
  });

  it("a chamada passa pelo Axios (nunca um fetch cru)", () => {
    expect(apiFonte).toMatch(/export const analyzeIndexFile[\s\S]{0,200}api\.post\(/);
  });
});
