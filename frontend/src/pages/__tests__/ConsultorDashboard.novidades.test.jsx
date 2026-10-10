/**
 * O separador «Novidades» do Dashboard MONTADO, com a lista real de novidades.
 *
 * É aqui que quem ainda não tem um módulo Premium o vê anunciado. O teste da
 * ligação página ↔ componente: os dados vêm do endpoint e o destaque chega ao
 * ecrã mesmo quando a novidade Premium não é a mais recente.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../../layouts/DashboardLayout", () => ({
  default: ({ children }) => <div data-testid="layout">{children}</div>,
}));
vi.mock("../../contexts/AuthContext", () => ({
  useAuth: () => ({
    token: "t", user: { id: "u1", name: "Carla", role: "consultor" }, effectiveRole: "consultor",
  }),
}));
vi.mock("../../components/TasksPanel", () => ({ default: () => <div /> }));
vi.mock("../../components/TeamMural", () => ({ default: () => <div /> }));
vi.mock("../../components/dashboard/DashboardCalendar", () => ({ default: () => <div /> }));
vi.mock("../../components/calendar/AgendaCalendar", () => ({ default: () => <div /> }));

vi.mock("../../components/dashboard/DashboardShared", async (original) => {
  const real = await original();
  return {
    ...real,
    useDashboardData: () => ({
      processes: [], filteredProcesses: [], workflowStatuses: [], upcomingExpiries: [], loading: false,
      searchTerm: "", setSearchTerm: vi.fn(), statusFilter: "all", setStatusFilter: vi.fn(), fetchData: vi.fn(),
    }),
    useDocumentManagement: () => ({
      isAddExpiryOpen: false, setIsAddExpiryOpen: vi.fn(), expiryFormData: {}, setExpiryFormData: vi.fn(),
      formLoading: false, handleAddExpiry: vi.fn(), openAddExpiryDialog: vi.fn(), isAnalyzing: false,
      isLoadingFiles: false, oneDriveFiles: [], selectedClient: null, analysisResult: null, aiSummary: null,
      aiAnalysisDate: null, aiError: null, loadClientAndAnalyze: vi.fn(), refreshAiAnalysis: vi.fn(),
      analyzeDocumentWithAI: vi.fn(),
    }),
  };
});

const api = vi.hoisted(() => ({
  getWebmailStats: vi.fn(),
  getCalendarDeadlines: vi.fn(),
  getCommunicationsFeed: vi.fn(),
  getSystemChangelogs: vi.fn(),
  getAutoDrafts: vi.fn(),
}));
vi.mock("../../services/api", async (original) => ({ ...(await original()), ...api }));

import ConsultorDashboard from "../ConsultorDashboard";

const RECENTE_NORMAL = { id: "1", version: "2026-10-05", published_at: "2026-10-05T10:00:00+00:00", content_markdown: "**Correcções** diversas", is_premium: false };
const ANTERIOR_PREMIUM = { id: "2", version: "2026-09-20", published_at: "2026-09-20T10:00:00+00:00", content_markdown: "Novo módulo de simulação", is_premium: true };

function montar() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter><ConsultorDashboard /></MemoryRouter>
    </QueryClientProvider>,
  );
}

async function abrirNovidades() {
  await userEvent.click(await screen.findByRole("tab", { name: /Novidades/ }));
}

beforeEach(() => {
  vi.clearAllMocks();
  api.getWebmailStats.mockResolvedValue({ data: { unread_count: 0, sent_today_count: 0, drafts_count: 0 } });
  api.getCalendarDeadlines.mockResolvedValue({ data: [] });
  api.getCommunicationsFeed.mockResolvedValue({ data: { portal_messages: [], unread_emails: [], portal_unread_count: 0, email_unread_count: 0 } });
  api.getAutoDrafts.mockResolvedValue({ data: { drafts: [] } });
  api.getSystemChangelogs.mockResolvedValue({ data: [RECENTE_NORMAL, ANTERIOR_PREMIUM] });
});

describe("Dashboard — Novidades do CRM", () => {
  it("pede várias novidades e não apenas a última", async () => {
    montar();
    await waitFor(() => expect(api.getSystemChangelogs).toHaveBeenCalled());
    expect(api.getSystemChangelogs.mock.calls[0][0]).toBeGreaterThan(1);
  });

  it("uma novidade Premium é destacada, mesmo atrás de uma mais recente que não o é", async () => {
    montar();
    await abrirNovidades();
    const cartoes = await screen.findAllByTestId("novidade");
    expect(cartoes).toHaveLength(2);
    expect(cartoes[0]).toHaveAttribute("data-premium", "false");
    expect(within(cartoes[1]).getByTestId("badge-premium")).toHaveTextContent("Módulo Premium");
    expect(within(cartoes[1]).getByTestId("convite-premium")).toBeInTheDocument();
  });

  it("sem novidades diz-se", async () => {
    api.getSystemChangelogs.mockResolvedValue({ data: [] });
    montar();
    await abrirNovidades();
    expect(await screen.findByText("Ainda não há novidades publicadas")).toBeInTheDocument();
  });

  it("uma resposta com a forma errada não rebenta o dashboard", async () => {
    api.getSystemChangelogs.mockResolvedValue({ data: { erro: "x" } });
    montar();
    await abrirNovidades();
    expect(await screen.findByText("Ainda não há novidades publicadas")).toBeInTheDocument();
  });

  it("uma falha do endpoint não rebenta o dashboard", async () => {
    api.getSystemChangelogs.mockRejectedValue(new Error("rede"));
    montar();
    await abrirNovidades();
    expect(await screen.findByText("Ainda não há novidades publicadas")).toBeInTheDocument();
  });
});
