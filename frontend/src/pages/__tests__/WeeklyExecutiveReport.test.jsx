/**
 * O Relatório Semanal Executivo MONTADO (Bloco 4, ponto 13).
 *
 * Forma dos dados = `executive_weekly.obter_semana` + `listar_semanas`:
 * o relatório do motor acrescido de `registo` e `semanas` (a mais recente primeiro).
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));

const api = vi.hoisted(() => ({
  getExecutiveWeekly: vi.fn(),
  regenerateExecutiveWeekly: vi.fn(),
  downloadExecutiveWeeklyPdf: vi.fn(),
  readBlobErrorBody: vi.fn(async (e) => e?.response?.data || {}),
}));
vi.mock("../../services/api", () => api);
const baixar = vi.hoisted(() => vi.fn());
vi.mock("../../utils/executivo", async (importOriginal) => ({
  ...(await importOriginal()),
  descarregarBlob: baixar,
}));

import { toast } from "sonner";
import WeeklyExecutiveReport from "../WeeklyExecutiveReport";

const SEMANAS = [
  { week_start: "2026-10-12", week_end: "2026-10-18", fechada: false, tem_registo: false },
  { week_start: "2026-10-05", week_end: "2026-10-11", fechada: true, tem_registo: true },
  { week_start: "2026-09-28", week_end: "2026-10-04", fechada: true, tem_registo: false },
];
const ANA = {
  user_id: "u-ana", name: "Ana Silva", role: "consultor", phase_changes: 3, processes_moved: 2,
  tasks_completed: 4, tasks_pending: 1, tasks_overdue: 0, por_fase: [],
};
const base = (inicio, fim, registo) => ({
  start_date: inicio, end_date: fim,
  summary: {
    total_users: 1, total_phase_changes: 3, total_processes_moved: 2,
    total_tasks_completed: 4, total_tasks_pending: 1, total_tasks_overdue: 0,
  },
  users: [ANA], por_fase: [], serie_diaria: [], serie_omitida: false, notas: [],
  movimentos: [{
    user_id: "u-ana", user_name: "Ana Silva", process_id: "p-1", process_number: 12,
    client_name: "Silva & Filhos", de_rotulo: "Fase Documental", para_rotulo: "Aprovado",
    em: "2026-10-07T10:00:00+00:00",
  }],
  semanas: SEMANAS, registo,
});
const FECHADA_COM_REGISTO = base("2026-10-05", "2026-10-11", {
  guardado: true, gerado_em: "2026-10-12T09:00:00+00:00", gerado_por: "Cátia CEO", origem: "manual",
});

function montar() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter><WeeklyExecutiveReport /></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getExecutiveWeekly.mockResolvedValue({ data: FECHADA_COM_REGISTO });
  api.downloadExecutiveWeeklyPdf.mockResolvedValue({ data: new Blob(["%PDF-"]), headers: {} });
});

describe("a semana fechada é um registo", () => {
  it("abre a semana anterior por omissão e diz de quando e de quem é o registo", async () => {
    montar();
    expect(await screen.findByTestId("estado-do-registo")).toHaveTextContent(/Registo de .* · Cátia CEO/);
    expect(api.getExecutiveWeekly).toHaveBeenCalledWith(undefined);
    expect(screen.getByTestId("indicador-fases")).toHaveTextContent("3");
  });

  it("os movimentos têm o número, o cliente e ligam ao processo", async () => {
    montar();
    const ligacao = await screen.findByRole("link", { name: /#12 · Silva & Filhos/ });
    expect(ligacao).toHaveAttribute("href", "/processo/p-1");
    expect(screen.getByText("Fase Documental")).toBeInTheDocument();
    expect(screen.getByText("Aprovado")).toBeInTheDocument();
  });

  it("oferece «Recalcular» num registo guardado de semana fechada", async () => {
    api.regenerateExecutiveWeekly.mockResolvedValue({ data: FECHADA_COM_REGISTO });
    montar();
    await userEvent.click(await screen.findByRole("button", { name: /Recalcular/ }));
    await waitFor(() => expect(api.regenerateExecutiveWeekly).toHaveBeenCalledWith("2026-10-05"));
    expect(toast.success).toHaveBeenCalled();
  });
});

describe("a semana em curso é uma vista", () => {
  const EM_CURSO = base("2026-10-12", "2026-10-18", { guardado: false, gerado_em: "2026-10-14T09:00:00+00:00" });

  it("diz que ainda não é registo e não oferece «Recalcular»", async () => {
    api.getExecutiveWeekly.mockResolvedValue({ data: EM_CURSO });
    montar();
    expect(await screen.findByTestId("estado-do-registo")).toHaveTextContent(/em curso — vista ao vivo/);
    expect(screen.queryByRole("button", { name: /Recalcular/ })).toBeNull();
  });

  it("a semana seguinte está desactivada na mais recente", async () => {
    api.getExecutiveWeekly.mockResolvedValue({ data: EM_CURSO });
    montar();
    await screen.findByTestId("estado-do-registo");
    expect(screen.getByRole("button", { name: "Semana seguinte" })).toBeDisabled();
  });
});

describe("navegar entre semanas", () => {
  it("«Semana anterior» pede a segunda-feira anterior; «seguinte» volta", async () => {
    montar();
    await screen.findByTestId("estado-do-registo");
    api.getExecutiveWeekly.mockResolvedValue({ data: base("2026-09-28", "2026-10-04", { guardado: false }) });

    await userEvent.click(screen.getByRole("button", { name: "Semana anterior" }));
    await waitFor(() => expect(api.getExecutiveWeekly).toHaveBeenLastCalledWith("2026-09-28"));

    api.getExecutiveWeekly.mockResolvedValue({ data: FECHADA_COM_REGISTO });
    await userEvent.click(await screen.findByRole("button", { name: "Semana seguinte" }));
    await waitFor(() => expect(api.getExecutiveWeekly).toHaveBeenLastCalledWith("2026-10-05"));
  });

  it("na semana mais antiga da lista não se recua", async () => {
    api.getExecutiveWeekly.mockResolvedValue({ data: base("2026-09-28", "2026-10-04", { guardado: false }) });
    montar();
    await screen.findByTestId("estado-do-registo");
    expect(screen.getByRole("button", { name: "Semana anterior" })).toBeDisabled();
  });
});

describe("PDF e erros", () => {
  it("o PDF é da semana que está no ecrã", async () => {
    montar();
    await screen.findByTestId("estado-do-registo");
    await userEvent.click(screen.getByRole("button", { name: /Gerar PDF/ }));
    await waitFor(() => expect(api.downloadExecutiveWeeklyPdf).toHaveBeenCalledWith("2026-10-05", { analiseIA: false }));
    expect(baixar).toHaveBeenCalled();
  });

  it("a caixa «Incluir análise de IA» vem desligada e, marcada, vai no pedido", async () => {
    montar();
    await screen.findByTestId("estado-do-registo");
    const caixa = screen.getByRole("checkbox", { name: /Incluir análise de IA/ });
    expect(caixa).not.toBeChecked();
    await userEvent.click(caixa);
    await userEvent.click(screen.getByRole("button", { name: /Gerar PDF/ }));
    await waitFor(() => expect(api.downloadExecutiveWeeklyPdf).toHaveBeenCalledWith("2026-10-05", { analiseIA: true }));
  });

  it("pediu a análise e o servidor não a incluiu: avisa", async () => {
    api.downloadExecutiveWeeklyPdf.mockResolvedValue({
      data: new Blob(["%PDF-"]), headers: { "x-analise-ia": "indisponivel" },
    });
    montar();
    await screen.findByTestId("estado-do-registo");
    await userEvent.click(screen.getByRole("checkbox", { name: /Incluir análise de IA/ }));
    await userEvent.click(screen.getByRole("button", { name: /Gerar PDF/ }));
    await waitFor(() => expect(toast.warning).toHaveBeenCalledWith(expect.stringMatching(/sem a análise de IA/)));
  });

  it("o erro do servidor aparece e não há tabelas vazias a fingir", async () => {
    api.getExecutiveWeekly.mockRejectedValue({ response: { data: { detail: "Não há relatório de uma semana que ainda não começou" } } });
    montar();
    expect(await screen.findByRole("alert")).toHaveTextContent(/ainda não começou/);
    expect(screen.queryByTestId("movimentos-de-fase")).toBeNull();
  });

  it("sem movimentos diz-o", async () => {
    api.getExecutiveWeekly.mockResolvedValue({ data: { ...FECHADA_COM_REGISTO, movimentos: [] } });
    montar();
    expect(await screen.findByText(/Sem movimentos de fase/)).toBeInTheDocument();
  });
});
