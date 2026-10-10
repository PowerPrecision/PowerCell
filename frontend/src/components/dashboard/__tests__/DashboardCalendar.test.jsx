/**
 * O calendário do Dashboard MONTADO (Bloco 4, ponto 29).
 * Forma dos dados = `dashboard_calendar.run_dashboard_calendar`.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ getDashboardCalendar: vi.fn() }));
vi.mock("../../../services/api", () => api);

import DashboardCalendar from "../DashboardCalendar";

const OUTUBRO = {
  month: "2026-10", dias_no_mes: 31, truncado: false,
  contagens: { escritura: 1, cpcv: 1, marcacao: 1, ausencia: 1, prazo: 0 },
  itens: [
    { id: "p1:data_escritura_prevista", dia: "2026-10-20", categoria: "escritura", titulo: "Escritura · processo #12",
      hora: null, origem: "processo", process_id: "p1", client_id: "c1", client_name: "Silva", responsavel: null },
    { id: "p1:data_cpcv", dia: "2026-10-20", categoria: "cpcv", titulo: "CPCV · processo #12",
      hora: null, origem: "processo", process_id: "p1", client_id: "c1", client_name: "Silva", responsavel: null },
    { id: "e1:2026-10-07", dia: "2026-10-07", categoria: "marcacao", titulo: "Visita ao imóvel",
      hora: "14:30", origem: "evento", process_id: null, client_id: null, client_name: "", responsavel: "Ana Silva" },
    { id: "e2:2026-10-07", dia: "2026-10-07", categoria: "ausencia", titulo: "Férias",
      hora: null, origem: "evento", process_id: "p9", client_id: "c9", client_name: "", responsavel: "Rui Costa" },
  ],
};

function montar() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter><DashboardCalendar /></MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date("2026-10-07T10:00:00Z"));
  api.getDashboardCalendar.mockReset();
  api.getDashboardCalendar.mockResolvedValue({ data: OUTUBRO });
});
afterEach(() => vi.useRealTimers());

describe("o calendário monta e mostra o mês", () => {
  it("pede o mês actual e mostra o título, a legenda e as contagens", async () => {
    montar();
    expect(await screen.findByTestId("mes-do-calendario")).toHaveTextContent("Outubro de 2026");
    await waitFor(() => expect(screen.getByTestId("contagem-escritura")).toHaveTextContent("1"));
    expect(api.getDashboardCalendar).toHaveBeenCalledWith("2026-10");
    for (const rotulo of ["Escrituras", "CPCV", "Marcações", "Ausências", "Prazos"]) {
      expect(screen.getByText(rotulo)).toBeInTheDocument();
    }
  });

  it("hoje vem seleccionado e lista os eventos do dia por extenso", async () => {
    montar();
    const lista = await screen.findByTestId("itens-do-dia");
    await waitFor(() => expect(within(lista).getByText("Visita ao imóvel")).toBeInTheDocument());
    expect(within(lista).getByText(/Marcações · 14:30/)).toBeInTheDocument();
    expect(within(lista).getByText(/Férias/)).toBeInTheDocument();
    expect(within(lista).getByText(/Ausências/)).toBeInTheDocument();
    expect(within(lista).getByText(/Ana Silva/)).toBeInTheDocument();
  });

  it("clicar noutro dia lista os eventos dele; a escritura liga ao processo", async () => {
    montar();
    await screen.findByTestId("itens-do-dia");
    await waitFor(() => expect(screen.getByTestId("dia-2026-10-20")).toHaveAccessibleName(/2 eventos/));
    await userEvent.click(screen.getByTestId("dia-2026-10-20"));

    const lista = screen.getByTestId("itens-do-dia");
    expect(within(lista).getByRole("link", { name: "Escritura · processo #12" })).toHaveAttribute("href", "/processo/p1");
    expect(within(lista).getByRole("link", { name: "CPCV · processo #12" })).toHaveAttribute("href", "/processo/p1");
  });

  it("uma ausência não é uma ligação (não é de um cliente)", async () => {
    montar();
    const lista = await screen.findByTestId("itens-do-dia");
    await waitFor(() => expect(within(lista).getByText(/Férias/)).toBeInTheDocument());
    expect(within(lista).queryByRole("link", { name: /Férias/ })).toBeNull();
  });

  it("um dia sem eventos diz-o", async () => {
    montar();
    await screen.findByTestId("itens-do-dia");
    await userEvent.click(screen.getByTestId("dia-2026-10-15"));
    expect(screen.getByText("Sem eventos neste dia.")).toBeInTheDocument();
  });

  it("cada categoria tem letra E cor: os marcadores do dia levam a letra", async () => {
    montar();
    await waitFor(() => expect(screen.getByTestId("dia-2026-10-20")).toHaveAccessibleName(/2 eventos/));
    const celula = screen.getByTestId("dia-2026-10-20");
    // aria-hidden nas marcas: o nome acessível já diz quantos; os títulos têm o rótulo.
    expect(celula.querySelectorAll("[title='Escrituras'], [title='CPCV']")).toHaveLength(2);
    expect(celula.textContent).toContain("E");
    expect(celula.textContent).toContain("C");
  });
});

describe("navegar entre meses", () => {
  it("«Mês seguinte» pede o mês seguinte e passa ao dia 1", async () => {
    montar();
    await screen.findByTestId("itens-do-dia");
    api.getDashboardCalendar.mockResolvedValue({ data: { ...OUTUBRO, month: "2026-11", itens: [], contagens: {} } });
    await userEvent.click(screen.getByRole("button", { name: "Mês seguinte" }));

    await waitFor(() => expect(api.getDashboardCalendar).toHaveBeenLastCalledWith("2026-11"));
    expect(screen.getByTestId("mes-do-calendario")).toHaveTextContent("Novembro de 2026");
    expect(screen.getByTestId("dia-2026-11-01")).toHaveAttribute("aria-pressed", "true");
  });

  it("«Hoje» volta ao mês actual com hoje seleccionado", async () => {
    montar();
    await screen.findByTestId("itens-do-dia");
    await userEvent.click(screen.getByRole("button", { name: "Mês anterior" }));
    await userEvent.click(screen.getByRole("button", { name: "Hoje" }));
    expect(screen.getByTestId("mes-do-calendario")).toHaveTextContent("Outubro de 2026");
    expect(screen.getByTestId("dia-2026-10-07")).toHaveAttribute("aria-pressed", "true");
  });
});

describe("estados", () => {
  it("o erro do servidor aparece e a grelha continua utilizável", async () => {
    api.getDashboardCalendar.mockRejectedValue({ response: { data: { detail: "month inválido. Use AAAA-MM" } } });
    montar();
    expect(await screen.findByRole("alert")).toHaveTextContent(/month inválido/);
    expect(screen.getByTestId("dia-2026-10-07")).toBeInTheDocument();
  });

  it("forma inesperada não rebenta", async () => {
    api.getDashboardCalendar.mockResolvedValue({ data: { itens: {}, contagens: null } });
    montar();
    expect(await screen.findByText("Sem eventos neste dia.")).toBeInTheDocument();
    expect(screen.getByTestId("contagem-cpcv")).toHaveTextContent("0");
  });

  it("avisa quando os processos foram cortados", async () => {
    api.getDashboardCalendar.mockResolvedValue({ data: { ...OUTUBRO, truncado: true } });
    montar();
    expect(await screen.findByText(/mais processos neste mês/)).toBeInTheDocument();
  });
});
