/**
 * O Dashboard Executivo MONTADO (Bloco 4, pontos 13 e 16).
 *
 * Falseia só a fronteira (`DashboardLayout`, `services/api`, o descarregamento
 * do blob). Os filtros, os gráficos, a tabela e os indicadores são os reais.
 * A forma dos dados é a do servidor (`executive_report.montar_relatorio`).
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

const api = vi.hoisted(() => ({
  getTeamPerformance: vi.fn(),
  downloadTeamPerformancePdf: vi.fn(),
  readBlobErrorBody: vi.fn(async (e) => e?.response?.data || {}),
}));
vi.mock("../../services/api", () => api);

const baixar = vi.hoisted(() => vi.fn());
vi.mock("../../utils/executivo", async (importOriginal) => ({
  ...(await importOriginal()),
  descarregarBlob: baixar,
}));

import { toast } from "sonner";
import TeamPerformanceDashboard from "../TeamPerformanceDashboard";

const ANA = {
  user_id: "u-ana", name: "Ana Silva", email: "a@x.pt", role: "consultor",
  phase_changes: 5, processes_moved: 3, tasks_completed: 7, tasks_pending: 4, tasks_overdue: 1,
  historico_silenciado: false, por_fase: [],
};
const ZE = {
  user_id: "u-ze", name: "Zé Silenciado", email: "z@x.pt", role: "diretor",
  phase_changes: null, processes_moved: null, tasks_completed: 2, tasks_pending: 0, tasks_overdue: 0,
  historico_silenciado: true, por_fase: [],
};
const RELATORIO = {
  start_date: "2026-10-05", end_date: "2026-10-11",
  summary: {
    total_users: 2, total_phase_changes: 5, total_processes_moved: 3,
    total_tasks_completed: 9, total_tasks_pending: 4, total_tasks_overdue: 1,
  },
  users: [ANA, ZE],
  por_fase: [{ fase: "aprovado", rotulo: "Aprovado", n: 5 }],
  serie_diaria: [{ dia: "2026-10-06", mudancas_de_fase: 3, tarefas_concluidas: 2 }],
  serie_omitida: false, truncado: false, limite_de_utilizadores: 500,
  notas: ["Tarefa concluída conta a quem a concluiu."],
};

function montar() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <TeamPerformanceDashboard />
    </QueryClientProvider>,
  );
}
const ultimosParametros = () => api.getTeamPerformance.mock.calls.at(-1)[0];

beforeEach(() => {
  vi.clearAllMocks();
  api.getTeamPerformance.mockResolvedValue({ data: RELATORIO });
  api.downloadTeamPerformancePdf.mockResolvedValue({
    data: new Blob(["%PDF-"]), headers: { "content-disposition": 'attachment; filename="r.pdf"' },
  });
});

describe("a página monta e mostra o relatório do servidor", () => {
  it("pede a semana corrente sem filtros e mostra indicadores e tabela", async () => {
    montar();
    expect(await screen.findByTestId("linha-u-ana")).toBeInTheDocument();
    const p = ultimosParametros();
    expect(p.start_date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(p).not.toHaveProperty("user_ids");
    expect(p).not.toHaveProperty("roles");
    expect(screen.getByTestId("indicador-fases")).toHaveTextContent("5");
    expect(screen.getByTestId("indicador-concluidas")).toHaveTextContent("9");
    expect(screen.getByTestId("indicador-atraso")).toHaveTextContent("1");
  });

  it("o histórico desligado aparece como traço e não como zero", async () => {
    montar();
    const linha = await screen.findByTestId("linha-u-ze");
    const celulas = within(linha).getAllByRole("cell");
    expect(celulas[3]).toHaveTextContent("—");
    expect(celulas[4]).toHaveTextContent("—");
    expect(celulas[5]).toHaveTextContent("2");
  });

  it("mostra os critérios do servidor", async () => {
    montar();
    expect(await screen.findByTestId("criterios")).toHaveTextContent("conta a quem a concluiu");
  });

  it("um relatório sem dados não rebenta (forma inesperada)", async () => {
    api.getTeamPerformance.mockResolvedValue({ data: { summary: {}, users: {}, por_fase: "x" } });
    montar();
    expect(await screen.findByText(/Sem colaboradores/)).toBeInTheDocument();
  });
});

describe("filtros", () => {
  it("escolher um colaborador pede-o ao servidor e mantém a lista completa no seletor", async () => {
    montar();
    await screen.findByTestId("linha-u-ana");
    api.getTeamPerformance.mockResolvedValue({ data: { ...RELATORIO, users: [ANA] } });

    await userEvent.click(screen.getByRole("combobox", { name: "Colaborador" }));
    await userEvent.click(await screen.findByRole("option", { name: "Ana Silva" }));

    await waitFor(() => expect(ultimosParametros().user_ids).toBe("u-ana"));
    // O servidor devolveu só a Ana, mas o seletor continua a oferecer o Zé.
    await userEvent.click(screen.getByRole("combobox", { name: "Colaborador" }));
    expect(await screen.findByRole("option", { name: "Zé Silenciado" })).toBeInTheDocument();
  });

  it("clicar numa linha filtra e clicar de novo limpa", async () => {
    montar();
    await userEvent.click(await screen.findByTestId("linha-u-ana"));
    await waitFor(() => expect(ultimosParametros().user_ids).toBe("u-ana"));
    await userEvent.click(await screen.findByTestId("linha-u-ana"));
    await waitFor(() => expect(ultimosParametros()).not.toHaveProperty("user_ids"));
  });

  it("o filtro por perfil vai como roles e a Indexação não é oferecida", async () => {
    montar();
    await screen.findByTestId("linha-u-ana");
    await userEvent.click(screen.getByRole("combobox", { name: "Perfil" }));
    const opcoes = (await screen.findAllByRole("option")).map((o) => o.textContent);
    expect(opcoes).not.toContain("Indexação");
    await userEvent.click(screen.getByRole("option", { name: "Diretor" }));
    await waitFor(() => expect(ultimosParametros().roles).toBe("diretor"));
  });

  it("o intervalo personalizado mostra as datas e pede-as ao servidor", async () => {
    montar();
    await screen.findByTestId("linha-u-ana");
    expect(screen.queryByLabelText("De")).toBeNull();

    await userEvent.click(screen.getByRole("combobox", { name: "Período" }));
    await userEvent.click(await screen.findByRole("option", { name: "Intervalo personalizado" }));
    const de = await screen.findByLabelText("De");
    const ate = screen.getByLabelText("Até");
    await userEvent.clear(de);
    await userEvent.type(de, "2026-09-01");
    await userEvent.clear(ate);
    await userEvent.type(ate, "2026-09-30");

    await waitFor(() => expect(ultimosParametros()).toMatchObject({
      start_date: "2026-09-01", end_date: "2026-09-30",
    }));
  });

  it("um intervalo inválido diz-o e NÃO chega ao servidor", async () => {
    montar();
    await screen.findByTestId("linha-u-ana");
    await userEvent.click(screen.getByRole("combobox", { name: "Período" }));
    await userEvent.click(await screen.findByRole("option", { name: "Intervalo personalizado" }));
    const ate = await screen.findByLabelText("Até");
    api.getTeamPerformance.mockClear();
    await userEvent.clear(ate);
    await userEvent.type(ate, "2020-01-01");

    expect(await screen.findByRole("alert")).toHaveTextContent(/anterior ou igual/);
    expect(api.getTeamPerformance).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /Gerar PDF/ })).toBeDisabled();
  });

  it("mudar de período repõe a toda a equipa", async () => {
    montar();
    await userEvent.click(await screen.findByTestId("linha-u-ana"));
    await waitFor(() => expect(ultimosParametros().user_ids).toBe("u-ana"));
    await userEvent.click(screen.getByRole("combobox", { name: "Período" }));
    await userEvent.click(await screen.findByRole("option", { name: "Últimos 30 dias" }));
    await waitFor(() => expect(ultimosParametros()).not.toHaveProperty("user_ids"));
  });
});

describe("erros", () => {
  it("o motivo do servidor aparece (503: demorou demasiado)", async () => {
    api.getTeamPerformance.mockRejectedValue({
      response: { data: { detail: "O relatório demorou demasiado a calcular. Reduza o período." } },
    });
    montar();
    expect(await screen.findByRole("alert")).toHaveTextContent(/demorou demasiado/);
  });

  it("avisa quando a lista foi cortada", async () => {
    api.getTeamPerformance.mockResolvedValue({ data: { ...RELATORIO, truncado: true } });
    montar();
    expect(await screen.findByRole("status")).toHaveTextContent(/limitada às primeiras 500/);
  });
});

describe("Gerar PDF", () => {
  it("pede o PDF com os MESMOS parâmetros do ecrã e descarrega-o", async () => {
    montar();
    await userEvent.click(await screen.findByTestId("linha-u-ana"));
    await waitFor(() => expect(ultimosParametros().user_ids).toBe("u-ana"));
    const doEcra = ultimosParametros();

    await userEvent.click(screen.getByRole("button", { name: /Gerar PDF/ }));

    await waitFor(() => expect(baixar).toHaveBeenCalledWith(expect.any(Blob), "r.pdf"));
    expect(api.downloadTeamPerformancePdf).toHaveBeenCalledWith(doEcra);
    expect(toast.success).toHaveBeenCalled();
  });

  it("a falha mostra o motivo do servidor (lido do Blob de erro)", async () => {
    api.downloadTeamPerformancePdf.mockRejectedValue({
      response: { data: { detail: "O relatório demorou demasiado a calcular." } },
    });
    montar();
    await screen.findByTestId("linha-u-ana");
    await userEvent.click(screen.getByRole("button", { name: /Gerar PDF/ }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("O relatório demorou demasiado a calcular."));
    expect(baixar).not.toHaveBeenCalled();
  });

  it("o botão fica desactivado enquanto o PDF é gerado (sem cliques duplos)", async () => {
    let resolver;
    api.downloadTeamPerformancePdf.mockReturnValue(new Promise((r) => { resolver = r; }));
    montar();
    await screen.findByTestId("linha-u-ana");
    const botao = screen.getByRole("button", { name: /Gerar PDF/ });
    await userEvent.click(botao);
    expect(botao).toBeDisabled();
    resolver({ data: new Blob(["x"]), headers: {} });
    await waitFor(() => expect(botao).not.toBeDisabled());
    expect(api.downloadTeamPerformancePdf).toHaveBeenCalledTimes(1);
  });
});
