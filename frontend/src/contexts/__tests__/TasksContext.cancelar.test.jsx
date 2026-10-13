/**
 * `cancelTask` do TasksContext (botão ✕ do painel de tarefas do cabeçalho).
 *
 * Antes: qualquer falha dava o MESMO aviso genérico («Não foi possível cancelar a
 * tarefa») por cima do toast do interceptor, sem motivo, e a tarefa ficava na lista.
 */
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// ESTÁVEL: um `user` novo a cada render recriava o `fetchActiveTasks` (depende de
// `user`) e fazia o contexto pedir a lista em cada render — o que escondia, nos
// testes, se a ressincronização era ou não feita pelo `cancelTask`.
const sessao = vi.hoisted(() => ({ valor: { user: { id: "u-1", role: "diretor" }, token: "t" } }));
vi.mock("../AuthContext", () => ({ useAuth: () => sessao.valor }));
vi.mock("../../hooks/useTaskEvents", async () => {
  const real = await vi.importActual("../../hooks/useTaskEvents");
  return { ...real, useTaskEvents: () => ({ isConnected: false }) };
});

const aviso = vi.hoisted(() => ({
  error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn(), loading: vi.fn(), dismiss: vi.fn(),
}));
vi.mock("sonner", () => ({ toast: aviso }));

const estado = vi.hoisted(() => ({ tarefas: [] }));
const cancelar = vi.hoisted(() => vi.fn());
const obter = vi.hoisted(() => vi.fn());

vi.mock("../../services/api", () => ({
  default: { get: obter, delete: vi.fn() },
  cancelBackgroundTask: cancelar,
}));

import { TasksProvider, useTasks } from "../TasksContext";

const TAREFA = {
  task_id: "task_1", task_type: "PDF_GEN", title: "Gerar proposta", status: "running",
  progress: 10, priority: "normal",
};

function Sonda() {
  const { tasks, cancelTask } = useTasks();
  return (
    <div>
      <ul>{tasks.map((t) => <li key={t.task_id}>{t.title}</li>)}</ul>
      <button onClick={() => cancelTask("task_1")}>cancelar</button>
    </div>
  );
}

beforeEach(() => {
  estado.tarefas = [{ ...TAREFA }];
  obter.mockImplementation(async () => ({
    data: { tasks: estado.tarefas, active_count: estado.tarefas.length },
  }));
});
afterEach(() => vi.clearAllMocks());

const montar = async () => {
  render(<TasksProvider><Sonda /></TasksProvider>);
  await screen.findByText("Gerar proposta");
};

describe("TasksContext.cancelTask — recusa do servidor", () => {
  it("400: toast com o MOTIVO (um só) e ressincroniza a lista", async () => {
    cancelar.mockRejectedValueOnce({
      response: { status: 400, data: { detail: "Apenas tarefas pendentes podem ser canceladas" } },
    });
    await montar();
    const pedidosAntes = obter.mock.calls.length;
    // O servidor entretanto já a deu por terminada.
    estado.tarefas = [];

    await userEvent.click(screen.getByRole("button", { name: "cancelar" }));

    await waitFor(() => expect(aviso.error).toHaveBeenCalledTimes(1));
    expect(aviso.error).toHaveBeenCalledWith("Não foi possível cancelar a tarefa", {
      description: "Apenas tarefas pendentes podem ser canceladas",
    });
    await waitFor(() => expect(obter.mock.calls.length).toBeGreaterThan(pedidosAntes));
    await waitFor(() => expect(screen.queryByText("Gerar proposta")).toBeNull());
  });

  it("403: diz que falta permissão e a tarefa continua na lista", async () => {
    cancelar.mockRejectedValueOnce({ response: { status: 403, data: {} } });
    await montar();

    await userEvent.click(screen.getByRole("button", { name: "cancelar" }));

    await waitFor(() => expect(aviso.error).toHaveBeenCalled());
    expect(aviso.error.mock.calls[0][1].description).toMatch(/permissão/);
    expect(screen.getByText("Gerar proposta")).toBeInTheDocument();
  });

  it("contraprova: sucesso retira a tarefa, avisa «cancelada» e não mostra erro", async () => {
    cancelar.mockImplementationOnce(async () => {
      estado.tarefas = [];   // o servidor deixa de a listar
      return { data: { success: true } };
    });
    await montar();
    await userEvent.click(screen.getByRole("button", { name: "cancelar" }));
    await waitFor(() => expect(screen.queryByText("Gerar proposta")).toBeNull());
    expect(aviso.info).toHaveBeenCalledWith("Tarefa cancelada");
    expect(aviso.error).not.toHaveBeenCalled();
  });
});
