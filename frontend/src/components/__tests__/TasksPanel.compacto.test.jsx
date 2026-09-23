/**
 * Painel de Tarefas: densidade e atribuições órfãs (Lote 4, pontos 12 e 13).
 *
 * PONTO 13 — O PROBLEMA NÃO É O CARTÃO, É O CARTÃO DENTRO DO CARTÃO.
 *   O `TasksPanel` já É um `Card` completo (CardHeader, CardTitle
 *   "Tarefas", Badge de contagem, CardDescription e ScrollArea próprio).
 *   O `ProcessDetails` envolvia-o noutro `Card`, com outro `CardHeader`,
 *   outro título "Tarefas" e outro `ScrollArea` — dois cartões, dois
 *   cabeçalhos com o mesmo texto, duas áreas de scroll encaixadas. E
 *   passava `compact={false}`, desligando o modo compacto que já existia.
 *
 * PONTO 12 — UMA TAREFA ÓRFÃ NÃO É UMA TAREFA POR ATRIBUIR.
 *   Ambas mostravam "Sem atribuição". Só a primeira exige uma decisão
 *   humana: alguém trabalhava nela e saiu do processo.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const sessao = vi.hoisted(() => ({
  valor: { user: { id: "u-1", name: "Ana", role: "diretor" }, token: "t" },
}));
vi.mock("../../contexts/AuthContext", () => ({ useAuth: () => sessao.valor }));
vi.mock("../../hooks/useTaskEvents", () => ({
  useTaskEvents: () => ({ isConnected: false }),
}));

const api = vi.hoisted(() => ({
  tarefas: [],
  processo: {},
  utilizadores: [],
}));

vi.mock("../../services/api", () => ({
  getTasks: vi.fn(async () => ({ data: api.tarefas })),
  getMyTasks: vi.fn(async () => ({ data: api.tarefas })),
  getProcessTasks: vi.fn(async () => ({ data: api.tarefas })),
  getProcess: vi.fn(async () => ({ data: api.processo })),
  getStaffUsers: vi.fn(async () => ({ data: api.utilizadores })),
  createTask: vi.fn(async () => ({ data: {} })),
  completeTask: vi.fn(async () => ({ data: {} })),
  reopenTask: vi.fn(async () => ({ data: {} })),
  deleteTask: vi.fn(async () => ({ data: {} })),
  getActiveBackgroundTasks: vi.fn(async () => ({ data: [] })),
  acknowledgeBackgroundTask: vi.fn(async () => ({ data: {} })),
  cancelBackgroundTask: vi.fn(async () => ({ data: {} })),
}));

import TasksPanel from "../TasksPanel";

const TAREFA = {
  id: "t-1",
  title: "[PROC-012] Rever a minuta",
  description: "Confirmar os dados do notário",
  assigned_to: ["u-2"],
  assigned_to_names: ["Rita"],
  completed: false,
  created_at: "2026-09-20T10:00:00+00:00",
};

beforeEach(() => {
  api.tarefas = [{ ...TAREFA }];
  api.processo = { id: "p-1", assigned_consultor_ids: ["u-2"] };
  api.utilizadores = [{ id: "u-2", name: "Rita", role: "consultor" }];
});

afterEach(() => vi.clearAllMocks());

const esperarPelaTarefa = async () =>
  await screen.findByText(/Rever a minuta/);

describe("Ponto 13 — descascar o cartão-dentro-do-cartão", () => {
  it("por omissão desenha a sua própria moldura", async () => {
    // O `Card` do shadcn não expõe atributo nenhum que o identifique, e
    // consultar por classe CSS é proibido pelas normas do projecto — daí
    // o `data-testid` na moldura, que é o que está sob teste aqui.
    render(<TasksPanel processId="p-1" />);
    await esperarPelaTarefa();
    expect(screen.getByTestId("tasks-panel-card")).toBeTruthy();
  });

  it("com asCard=false não desenha moldura nenhuma", async () => {
    // Sem isto, quem o embute num cartão fica com dois cabeçalhos
    // "Tarefas" e duas áreas de scroll encaixadas.
    render(<TasksPanel processId="p-1" asCard={false} />);
    await esperarPelaTarefa();
    expect(screen.queryByTestId("tasks-panel-card")).toBeNull();
  });

  it("com asCard=false não repete o título do cartão que o embute", async () => {
    render(<TasksPanel processId="p-1" asCard={false} />);
    await esperarPelaTarefa();
    expect(screen.queryByText("Tarefas")).toBeNull();
  });

  it("o botão de criar sobrevive a perder a moldura", async () => {
    // É a acção principal do painel: escondê-la ao descascar o cartão
    // seria trocar um problema de densidade por um de funcionalidade.
    render(<TasksPanel processId="p-1" asCard={false} />);
    await esperarPelaTarefa();
    expect(screen.getByRole("button", { name: /nova tarefa/i })).toBeTruthy();
  });

  it("em modo compacto esconde a data de criação", async () => {
    // Numa coluna de 1/3 do ecrã é ruído: não se decide nada com ela.
    render(<TasksPanel processId="p-1" compact />);
    await esperarPelaTarefa();
    expect(screen.queryByText("20/09/2026")).toBeNull();
  });

  it("fora do modo compacto a data de criação continua lá", async () => {
    // Contraprova: sem ela, esconder tudo passava no teste acima.
    render(<TasksPanel processId="p-1" />);
    await esperarPelaTarefa();
    expect(screen.getByText("20/09/2026")).toBeTruthy();
  });

  it("em modo compacto esconde os filtros da listagem", async () => {
    render(<TasksPanel processId="p-1" compact />);
    await esperarPelaTarefa();
    expect(screen.queryByLabelText(/concluídas/i)).toBeNull();
  });

  it("em modo compacto continua a mostrar o essencial", async () => {
    // A compactação não pode comer a informação: título e responsável
    // são o que faz a linha valer a pena.
    render(<TasksPanel processId="p-1" compact />);
    await esperarPelaTarefa();
    expect(screen.getByText(/Rever a minuta/)).toBeTruthy();
    expect(screen.getByText(/Rita/)).toBeTruthy();
  });
});

describe("Ponto 12 — a atribuição fantasma vista pelo utilizador", () => {
  it("uma tarefa órfã diz que ficou sem responsável", async () => {
    api.tarefas = [{
      ...TAREFA,
      assigned_to: [],
      assigned_to_names: [],
      assignment_orphaned: true,
    }];
    render(<TasksPanel processId="p-1" />);
    await esperarPelaTarefa();
    expect(screen.getByText(/sem responsável/i)).toBeTruthy();
  });

  it("uma tarefa que nunca teve responsável não é marcada como órfã", async () => {
    // Contraprova: a distinção só tem valor se as duas NÃO se parecerem.
    api.tarefas = [{ ...TAREFA, assigned_to: [], assigned_to_names: [] }];
    render(<TasksPanel processId="p-1" />);
    await esperarPelaTarefa();
    expect(screen.queryByText(/sem responsável/i)).toBeNull();
    expect(screen.getByText(/sem atribuição/i)).toBeTruthy();
  });

  it("aguenta o assigned_to escalar que o motor de automação gravava", async () => {
    // O backend normaliza, mas os documentos antigos existem e a UI não
    // pode rebentar por causa de um `.join` sobre uma string.
    api.tarefas = [{ ...TAREFA, assigned_to: "u-2", assigned_to_names: ["Rita"] }];
    render(<TasksPanel processId="p-1" />);
    expect(await esperarPelaTarefa()).toBeTruthy();
  });
});

describe("O selector de responsáveis", () => {
  it("não cai silenciosamente para o staff todo quando o processo falha", async () => {
    // O `catch` avisava só no console e passava a oferecer TODA a gente.
    // Num processo sem ninguém atribuído é assim que nascem as tarefas
    // fantasma.
    const { getProcess } = await import("../../services/api");
    getProcess.mockRejectedValueOnce(new Error("500"));
    api.utilizadores = [
      { id: "u-2", name: "Rita", role: "consultor" },
      { id: "u-9", name: "Alheio", role: "consultor" },
    ];

    render(<TasksPanel processId="p-1" />);
    await esperarPelaTarefa();
    const botao = screen.getByRole("button", { name: /nova tarefa/i });
    botao.click();

    await waitFor(() => expect(screen.getByRole("dialog")).toBeTruthy());
    const dialogo = within(screen.getByRole("dialog"));
    expect(dialogo.getByText(/fora da equipa do processo/i)).toBeTruthy();
  });
});
