/**
 * Cancelar uma tarefa em background que o servidor recusa (QA, Out 2026).
 *
 * `DELETE /tasks/{id}/cancel` responde 400 quando a tarefa já terminou/falhou —
 * resposta correcta — e o painel engolia-a (`.catch(() => {})`): o botão
 * «Cancelar» parecia morto e a tarefa ficava na lista. Hoje diz o motivo e
 * ressincroniza.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const sessao = vi.hoisted(() => ({
  valor: { user: { id: "u-1", name: "Ana", role: "diretor" }, token: "t" },
}));
vi.mock("../../contexts/AuthContext", () => ({ useAuth: () => sessao.valor }));
vi.mock("../../hooks/useTaskEvents", () => ({
  useTaskEvents: () => ({ isConnected: false }),
}));

const aviso = vi.hoisted(() => ({
  error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn(), loading: vi.fn(), dismiss: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: aviso }));

const api = vi.hoisted(() => ({
  trabalhos: [],
}));

vi.mock("../../services/api", () => ({
  getTasks: vi.fn(async () => ({ data: [] })),
  getMyTasks: vi.fn(async () => ({ data: [] })),
  getProcessTasks: vi.fn(async () => ({ data: [] })),
  getProcess: vi.fn(async () => ({ data: {} })),
  getStaffUsers: vi.fn(async () => ({ data: [] })),
  createTask: vi.fn(),
  completeTask: vi.fn(),
  reopenTask: vi.fn(),
  deleteTask: vi.fn(),
  getActiveBackgroundTasks: vi.fn(async () => ({ data: { tasks: api.trabalhos } })),
  acknowledgeBackgroundTask: vi.fn(),
  cancelBackgroundTask: vi.fn(),
}));

import * as servicos from "../../services/api";
import TasksPanel from "../TasksPanel";

const TRABALHO = { task_id: "task_1", title: "Gerar proposta", status: "running", progress: 40 };

beforeEach(() => {
  api.trabalhos = [{ ...TRABALHO }];
});
afterEach(() => vi.clearAllMocks());

const botaoCancelar = async () => await screen.findByRole("button", { name: /^Cancelar$/ });

describe("TasksPanel — cancelar uma tarefa em background", () => {
  it("o servidor recusa (400): diz o MOTIVO, ressincroniza e a tarefa não fica «morta»", async () => {
    servicos.cancelBackgroundTask.mockRejectedValueOnce({
      response: { status: 400, data: { detail: "Apenas tarefas pendentes/em execução podem ser canceladas" } },
    });
    render(<TasksPanel />);
    const botao = await botaoCancelar();   // a lista inicial já carregou
    const pedidosAntes = servicos.getActiveBackgroundTasks.mock.calls.length;

    await userEvent.click(botao);

    await waitFor(() => expect(aviso.error).toHaveBeenCalledTimes(1));
    expect(aviso.error).toHaveBeenCalledWith("Não foi possível cancelar a tarefa", {
      description: "Apenas tarefas pendentes/em execução podem ser canceladas",
    });
    // Ressincronizou: a lista foi pedida outra vez ao servidor.
    await waitFor(() =>
      expect(servicos.getActiveBackgroundTasks.mock.calls.length).toBeGreaterThan(pedidosAntes),
    );
  });

  it("404 (a tarefa já não existe) também é dito", async () => {
    servicos.cancelBackgroundTask.mockRejectedValueOnce({
      response: { status: 404, data: { detail: "Tarefa não encontrada" } },
    });
    render(<TasksPanel />);
    await userEvent.click(await botaoCancelar());
    await waitFor(() => expect(aviso.error).toHaveBeenCalled());
    expect(aviso.error.mock.calls[0][1].description).toMatch(/já não existe/);
  });

  it("contraprova: cancelar com sucesso retira a tarefa e NÃO mostra erro", async () => {
    servicos.cancelBackgroundTask.mockResolvedValueOnce({ data: { success: true } });
    render(<TasksPanel />);
    await userEvent.click(await botaoCancelar());
    await waitFor(() => expect(screen.queryByText("Gerar proposta")).toBeNull());
    expect(aviso.error).not.toHaveBeenCalled();
  });

  it("sem resposta do servidor não duplica o aviso do interceptor", async () => {
    servicos.cancelBackgroundTask.mockRejectedValueOnce({ message: "Network Error" });
    render(<TasksPanel />);
    await userEvent.click(await botaoCancelar());
    await waitFor(() => expect(servicos.cancelBackgroundTask).toHaveBeenCalled());
    expect(aviso.error).not.toHaveBeenCalled();
  });
});
