/**
 * Testes de INTEGRAÇÃO da página de Estatísticas (Dashboard, Camada 2).
 *
 * O QUE ESTES TESTES DEFENDEM
 *   1. **Que a página deixou de puxar os processos crus.** Era o ponto de
 *      partida deste lote: `getProcesses()` sem filtro trazia os 12.450
 *      processos de produção para o browser. A asserção é sobre
 *      COMPORTAMENTO — o módulo de transporte é falso e conta as chamadas —
 *      e não sobre o texto do ficheiro, que uma refactorização inocente
 *      satisfazia.
 *   2. **Que as barras vêm do funil do servidor**, incluindo as macro-fases
 *      que resolvem fases legadas. Sem isto, voltávamos a ter duas verdades:
 *      uma no Kanban e outra no gráfico.
 *   3. **Que o filtro por utilizador vai para o SERVIDOR.** Fazia-se no
 *      cliente sobre `p.assigned_consultor`, um campo que não existe nos
 *      processos — escolher um utilizador esvaziava todos os gráficos sem
 *      dar erro.
 *   4. **Que os avisos sobre a amostra aparecem.** Um gráfico que mistura
 *      medido com estimado sem o dizer é pior do que um gráfico vazio.
 *
 * Falso aqui: o `DashboardLayout` (arrastava a app inteira), o
 * `AuthContext` e o `services/api`. O estado, os `utils` e os gráficos são
 * os reais — o `recharts` monta no jsdom dentro do `SafeChartContainer`.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));

vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { id: "u-1", name: "Ana", role: "admin" },
  }),
}));

const chamadas = vi.hoisted(() => ({
  getProcesses: 0,
  funil: [],
}));

const FUNIL = {
  etapas: [
    { macro_fase: "novo", label: "Novo", processos: 10, alcancaram: 37, conversao_para_seguinte: 73.0, valor_imovel: 1_500_000 },
    { macro_fase: "analise", label: "Análise", processos: 20, alcancaram: 27, conversao_para_seguinte: 25.9, valor_imovel: 3_200_000 },
    { macro_fase: "aprovado", label: "Aprovado", processos: 5, alcancaram: 7, conversao_para_seguinte: 28.6, valor_imovel: 900_000 },
    { macro_fase: "concluido", label: "Concluído", processos: 2, alcancaram: 2, conversao_para_seguinte: null, valor_imovel: 400_000 },
  ],
  perdidos: { macro_fase: "perdido", label: "Perdido", processos: 8 },
  desconhecidos: { macro_fase: "__desconhecidas__", label: "Fases desconhecidas", processos: 3 },
  total_processos: 48,
  taxa_de_conclusao: 4.2,
  por_prioridade: { alta: 4, media: 0, baixa: 7, sem: 37 },
  macro_fases_sem_classificacao: ["renegociacao"],
};

const SLA = {
  macro_fases: [
    {
      macro_fase: "analise",
      limiar_dias: 15,
      em_curso: 20,
      acima_do_limiar: 6,
      dias_medios_em_curso: 18.4,
      banda_mediana_em_curso: "8-15",
      dias_medios_historico: null,
      amostra_historico: 0,
      bandas: [
        { banda: "0-7", processos: 4 },
        { banda: "8-15", processos: 10 },
        { banda: "16-30", processos: 0 },
        { banda: "31-60", processos: 0 },
        { banda: "61+", processos: 6 },
      ],
    },
  ],
  bandas: ["0-7", "8-15", "16-30", "31-60", "61+"],
  excluidos_da_amostra: ["nunca_tocado", "tocado_apos_fecho"],
};

vi.mock("../../services/api", () => ({
  getStats: vi.fn(async () => ({ data: {} })),
  getStatsFunil: vi.fn(async (params) => {
    chamadas.funil.push(params);
    return { data: FUNIL };
  }),
  getStatsSla: vi.fn(async () => ({ data: SLA })),
  getStatsLeads: vi.fn(async () => ({ data: { leads_by_status: {}, funnel_data: [], top_consultors: [] } })),
  getStatsConversion: vi.fn(async () => ({ data: { avg_conversion_days: 3 } })),
  getUsers: vi.fn(async () => ({ data: [{ id: "u-2", name: "Bruno" }] })),
  getProcesses: vi.fn(async () => {
    chamadas.getProcesses += 1;
    return { data: [] };
  }),
}));

import StatisticsPage from "../StatisticsPage";

beforeEach(() => {
  chamadas.getProcesses = 0;
  chamadas.funil = [];
  vi.clearAllMocks();
});

describe("StatisticsPage", () => {
  it("NÃO puxa os processos crus", async () => {
    // O ponto de partida deste lote: 12.450 processos pela rede para
    // desenhar barras.
    render(<StatisticsPage />);

    await waitFor(() => expect(chamadas.funil.length).toBeGreaterThan(0));
    expect(chamadas.getProcesses).toBe(0);
  });

  it("desenha as macro-fases que o servidor devolveu", async () => {
    render(<StatisticsPage />);

    await waitFor(() =>
      expect(screen.getByText("Distribuição por Macro-Fase")).toBeInTheDocument(),
    );
    expect(screen.getByText(/48/)).toBeInTheDocument();
  });

  it("mostra os concluídos e os perdidos do funil", async () => {
    render(<StatisticsPage />);

    await waitFor(() =>
      expect(screen.getByText(/2 concluídos vs 8 perdidos/)).toBeInTheDocument(),
    );
  });

  it("avisa sobre as fases sem grupo atribuído", async () => {
    render(<StatisticsPage />);

    await waitFor(() =>
      expect(screen.getByText("Sobre estes números")).toBeInTheDocument(),
    );
    expect(screen.getByText(/renegociacao/)).toBeInTheDocument();
  });

  it("avisa que ainda não há histórico medido", async () => {
    render(<StatisticsPage />);

    await waitFor(() =>
      expect(screen.getByText(/de agora em diante/)).toBeInTheDocument(),
    );
  });

  it("o separador de gargalos mostra a mediana ao lado da média", async () => {
    render(<StatisticsPage />);

    await waitFor(() =>
      expect(screen.getByRole("tab", { name: "Gargalos" })).toBeInTheDocument(),
    );
    await userEvent.click(screen.getByRole("tab", { name: "Gargalos" }));

    await waitFor(() =>
      expect(
        screen.getByText(/mediana na banda 8-15 dias/),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText(/6 acima de 15 dias/)).toBeInTheDocument();
  });

  it("quem vê tudo arranca em Todos os Utilizadores", async () => {
    // Arrancava com o próprio `user.id` e o filtro era feito no cliente
    // sobre um campo que não existe: a página abria vazia para um admin.
    const { getStatsFunil } = await import("../../services/api");
    render(<StatisticsPage />);

    await waitFor(() => expect(getStatsFunil).toHaveBeenCalled());
    expect(chamadas.funil[0]).toEqual({});
  });

  it("escolher um utilizador manda o filtro para o SERVIDOR", async () => {
    render(<StatisticsPage />);

    // Pelo PAPEL e não pelo texto: o texto do `Select` do Radix está num
    // elemento com `pointer-events: none` e o clique morre em silêncio.
    const seletores = await waitFor(() => {
      const encontrados = screen.getAllByRole("combobox");
      expect(encontrados.length).toBeGreaterThan(0);
      return encontrados;
    });
    await userEvent.click(seletores[0]);
    await userEvent.click(await screen.findByRole("option", { name: "Bruno" }));

    await waitFor(() =>
      expect(chamadas.funil.at(-1)).toEqual({ consultor_id: "u-2" }),
    );
  });
});
