/**
 * O editor de fases com a automação «Ao entrar nesta fase» — montado a sério.
 *
 * Só se falseia a fronteira (`services/api`). O que se afirma é o que SAI
 * para o servidor, porque é aí que `null` (herdar) e `[]` (nada) deixam de
 * poder confundir-se.
 */
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({
  getWorkflowEditor: vi.fn(),
  createWorkflowStatus: vi.fn(),
  updateWorkflowStatus: vi.fn(),
  deleteWorkflowStatus: vi.fn(),
}));

vi.mock("../../services/api", () => api);
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import WorkflowEditor from "../WorkflowEditor";
import { toast } from "sonner";

const FASES = [
  { id: "w-1", name: "fase_index", label: "Fase Index", order: 1, color: "blue",
    auto_assign_roles: null, task_templates: null },
  { id: "w-2", name: "fase_documental", label: "Fase Documental", order: 2, color: "green",
    auto_assign_roles: ["intermediario"],
    task_templates: [
      { id: "t1", title: "Pedir IRS", priority: "Alta", due_in_days: 5, assigned_role: "intermediario" },
    ] },
  { id: "w-3", name: "fase_vazia", label: "Fase Vazia", order: 3, color: "red",
    auto_assign_roles: [], task_templates: [] },
];

beforeEach(() => {
  vi.clearAllMocks();
  api.getWorkflowEditor.mockResolvedValue({
    data: {
      network_id: "grupo_a", empresas: ["Empresa A", "Empresa B"],
      tem_workflow_proprio: true, statuses: FASES,
    },
  });
  api.updateWorkflowStatus.mockResolvedValue({ data: {} });
  api.createWorkflowStatus.mockResolvedValue({ data: {} });
});

async function abrirEdicao(rotulo) {
  render(<WorkflowEditor />);
  const linha = (await screen.findByText(rotulo)).closest("div.flex");
  const botoes = within(linha.parentElement.parentElement).getAllByRole("button");
  // O botão «editar» é o penúltimo (o último elimina).
  await userEvent.click(botoes[botoes.length - 2]);
  return screen.findByTestId("edit-fase-automacao");
}

describe("Editor de fases — resumo na lista", () => {
  it("só as fases configuradas mostram o resumo, e distingue «nada» de «herdar»", async () => {
    render(<WorkflowEditor />);
    await screen.findByText("Fase Index");
    expect(screen.queryByTestId("resumo-automacao-fase_index")).not.toBeInTheDocument();
    expect(screen.getByTestId("resumo-automacao-fase_documental"))
      .toHaveTextContent("Ao entrar: atribui intermediario · 1 tarefa");
    expect(screen.getByTestId("resumo-automacao-fase_vazia"))
      .toHaveTextContent("Ao entrar: não atribui · sem tarefas");
  });
});

describe("Editor de fases — editar a automação", () => {
  it("uma fase que herda abre com os dois interruptores desligados", async () => {
    const seccao = await abrirEdicao("Fase Index");
    expect(within(seccao).getByRole("switch", { name: /personalizar a atribuição/i }))
      .not.toBeChecked();
    expect(within(seccao).getByRole("switch", { name: /personalizar as tarefas/i }))
      .not.toBeChecked();
    expect(within(seccao).getAllByText(/a herdar o comportamento por omissão/i)).toHaveLength(2);
  });

  it("gravar sem tocar envia null nas duas chaves (continua a herdar)", async () => {
    await abrirEdicao("Fase Index");
    await userEvent.click(screen.getByRole("button", { name: /guardar|atualizar/i }));
    await waitFor(() => expect(api.updateWorkflowStatus).toHaveBeenCalled());
    const [id, corpo] = api.updateWorkflowStatus.mock.calls[0];
    expect(id).toBe("w-1");
    expect(corpo.auto_assign_roles).toBeNull();
    expect(corpo.task_templates).toBeNull();
  });

  it("uma fase configurada abre com os valores e devolve o MESMO id ao gravar", async () => {
    const seccao = await abrirEdicao("Fase Documental");
    expect(within(seccao).getByLabelText("Título da tarefa 1")).toHaveValue("Pedir IRS");
    expect(within(seccao).getByRole("checkbox", { name: "Intermediário" })).toBeChecked();
    expect(within(seccao).getByRole("checkbox", { name: "Consultor" })).not.toBeChecked();

    await userEvent.click(screen.getByRole("button", { name: /guardar|atualizar/i }));
    await waitFor(() => expect(api.updateWorkflowStatus).toHaveBeenCalled());
    const corpo = api.updateWorkflowStatus.mock.calls[0][1];
    expect(corpo.auto_assign_roles).toEqual(["intermediario"]);
    expect(corpo.task_templates).toEqual([
      { id: "t1", title: "Pedir IRS", priority: "Alta", due_in_days: 5, assigned_role: "intermediario" },
    ]);
  });

  it("desligar o interruptor volta a herdar (null), não a «nada» ([])", async () => {
    const seccao = await abrirEdicao("Fase Vazia");
    // A fase estava configurada como «nada» ([]): interruptores ligados.
    const sw = within(seccao).getByRole("switch", { name: /personalizar as tarefas/i });
    expect(sw).toBeChecked();
    await userEvent.click(sw);
    await userEvent.click(screen.getByRole("button", { name: /guardar|atualizar/i }));
    await waitFor(() => expect(api.updateWorkflowStatus).toHaveBeenCalled());
    const corpo = api.updateWorkflowStatus.mock.calls[0][1];
    expect(corpo.task_templates).toBeNull();
    expect(corpo.auto_assign_roles).toEqual([]); // o outro não foi tocado
  });

  it("acrescentar uma tarefa envia-a sem id (o servidor gera-o)", async () => {
    const seccao = await abrirEdicao("Fase Index");
    await userEvent.click(within(seccao).getByRole("switch", { name: /personalizar as tarefas/i }));
    await userEvent.click(within(seccao).getByRole("button", { name: /adicionar tarefa/i }));
    await userEvent.type(within(seccao).getByLabelText("Título da tarefa 1"), "Chamar o cliente");
    await userEvent.type(within(seccao).getByLabelText(/prazo \(dias\)/i), "0");
    await userEvent.click(screen.getByRole("button", { name: /guardar|atualizar/i }));
    await waitFor(() => expect(api.updateWorkflowStatus).toHaveBeenCalled());
    const [tarefa] = api.updateWorkflowStatus.mock.calls[0][1].task_templates;
    expect(tarefa).toEqual({
      title: "Chamar o cliente", priority: "Média", due_in_days: 0, assigned_role: "todos",
    });
  });

  it("um título em branco impede a gravação e diz qual tarefa", async () => {
    const seccao = await abrirEdicao("Fase Index");
    await userEvent.click(within(seccao).getByRole("switch", { name: /personalizar as tarefas/i }));
    await userEvent.click(within(seccao).getByRole("button", { name: /adicionar tarefa/i }));
    await userEvent.click(screen.getByRole("button", { name: /guardar|atualizar/i }));
    expect(toast.error).toHaveBeenCalledWith(expect.stringMatching(/Tarefa 1/));
    expect(api.updateWorkflowStatus).not.toHaveBeenCalled();
  });

  it("remover a tarefa tira-a do pedido", async () => {
    const seccao = await abrirEdicao("Fase Documental");
    await userEvent.click(within(seccao).getByRole("button", { name: "Remover a tarefa 1" }));
    await userEvent.click(screen.getByRole("button", { name: /guardar|atualizar/i }));
    await waitFor(() => expect(api.updateWorkflowStatus).toHaveBeenCalled());
    expect(api.updateWorkflowStatus.mock.calls[0][1].task_templates).toEqual([]);
  });
});

describe("Editor de fases — workflow POR REDE", () => {
  it("diz de que rede é o workflow que se está a editar", async () => {
    render(<WorkflowEditor />);
    await screen.findByText("Fase Index");
    const aviso = screen.getByTestId("workflow-rede");
    expect(aviso).toHaveTextContent("Empresa A, Empresa B");
    expect(aviso).toHaveTextContent("as outras redes não são afetadas");
    expect(screen.queryByTestId("workflow-rede-modelo")).not.toBeInTheDocument();
  });

  it("avisa que a rede ainda usa o modelo base (a 1.ª alteração cria a cópia)", async () => {
    api.getWorkflowEditor.mockResolvedValue({
      data: { network_id: "grupo_b", empresas: [], tem_workflow_proprio: false, statuses: FASES },
    });
    render(<WorkflowEditor />);
    await screen.findByText("Fase Index");
    expect(screen.getByTestId("workflow-rede")).toHaveTextContent("grupo_b");
    expect(screen.getByTestId("workflow-rede-modelo")).toHaveTextContent("modelo base");
  });

  it("uma resposta sem `statuses` em lista não rebenta o ecrã", async () => {
    api.getWorkflowEditor.mockResolvedValue({ data: { network_id: "x", statuses: { a: 1 } } });
    render(<WorkflowEditor />);
    expect(await screen.findByTestId("add-workflow-status-btn")).toBeInTheDocument();
    // Sem a guarda, o erro era engolido pelo `catch` e o ecrã vinha vazio com um toast.
    expect(toast.error).not.toHaveBeenCalled();
  });
});
