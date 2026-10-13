/**
 * O toast «Envio directo falhou — retry agendado» não fica eternamente (QA, Out 2026).
 *
 * A tarefa do email de acesso ao Portal fica em «processing» enquanto o reenvio não é processado.
 * O toast que a representa é persistente; quando o pedido do utilizador falha (400/500) ele tem de
 * ser SUBSTITUÍDO por um de erro — e o polling seguinte (que ainda vê a tarefa «processing») não
 * o pode voltar a transformar em «a carregar».
 */
import { render, screen, waitFor, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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
const obter = vi.hoisted(() => vi.fn());
vi.mock("../../services/api", () => ({
  default: { get: obter, delete: vi.fn() },
  cancelBackgroundTask: vi.fn(),
}));

import { TasksProvider, useTasks } from "../TasksContext";
import {
  TITULO_DA_FALHA,
  _reporRegistoDeToastsDeEmail,
  mostrarFalhaDoEnvioDeEmail,
} from "../../utils/falhaNoEnvioDeEmail";

const EMAIL = {
  task_id: "task_email", task_type: "EMAIL_SEND", kind: "portal_access_email",
  title: "Email de acesso ao Portal", status: "processing", progress: 0,
  progress_message: "Envio directo falhou — retry agendado na fila.", priority: "normal",
};

let refrescar;
function Sonda() {
  const { tasks, fetchActiveTasks } = useTasks();
  refrescar = fetchActiveTasks;
  return <ul>{tasks.map((t) => <li key={t.task_id}>{t.title}</li>)}</ul>;
}

beforeEach(() => {
  _reporRegistoDeToastsDeEmail();
  estado.tarefas = [{ ...EMAIL }];
  obter.mockImplementation(async () => ({
    data: { tasks: estado.tarefas, active_count: estado.tarefas.length },
  }));
});
afterEach(() => vi.clearAllMocks());

async function montar() {
  render(<TasksProvider><Sonda /></TasksProvider>);
  await screen.findByText("Email de acesso ao Portal");
  await waitFor(() => expect(aviso.loading).toHaveBeenCalled());
}

const erroDoServidor = { response: { status: 500, data: { detail: "Falha interna ao enviar" } } };

describe("toast de email «a tentar»", () => {
  it("aparece como «a carregar» enquanto a tarefa está em curso", async () => {
    await montar();

    expect(aviso.loading).toHaveBeenCalledWith(
      "Email de acesso ao Portal",
      expect.objectContaining({
        id: "bg-task-task_email",
        description: "Envio directo falhou — retry agendado na fila.",
      }),
    );
  });

  it("quando o envio falha, é SUBSTITUÍDO por um toast de erro com o mesmo id", async () => {
    await montar();

    act(() => { mostrarFalhaDoEnvioDeEmail(erroDoServidor); });

    expect(aviso.error).toHaveBeenCalledTimes(1);
    expect(aviso.error).toHaveBeenCalledWith(TITULO_DA_FALHA, expect.objectContaining({
      id: "bg-task-task_email", description: "Falha interna ao enviar",
    }));
  });

  it("o polling seguinte (tarefa ainda «processing») NÃO o volta a pôr «a carregar»", async () => {
    await montar();
    act(() => { mostrarFalhaDoEnvioDeEmail(erroDoServidor); });
    aviso.loading.mockClear();

    await act(async () => { await refrescar(); });

    expect(aviso.loading).not.toHaveBeenCalled();
  });

  it("quando a tarefa termina como FALHADA, o toast de erro final substitui o mesmo id", async () => {
    await montar();
    act(() => { mostrarFalhaDoEnvioDeEmail(erroDoServidor); });
    aviso.error.mockClear();

    estado.tarefas = [{
      ...EMAIL, status: "failed", error_message: "O reenvio agendado não foi processado a tempo.",
    }];
    await act(async () => { await refrescar(); });

    expect(aviso.error).toHaveBeenCalledWith("Email de acesso ao Portal falhou", expect.objectContaining({
      id: "bg-task-task_email",
      description: "O reenvio agendado não foi processado a tempo.",
    }));
  });

  it("uma tarefa que NÃO é de email não é tocada pela falha do envio", async () => {
    estado.tarefas = [{ ...EMAIL, task_id: "task_pdf", kind: null, title: "Gerar proposta" }];
    render(<TasksProvider><Sonda /></TasksProvider>);
    await screen.findByText("Gerar proposta");
    await waitFor(() => expect(aviso.loading).toHaveBeenCalled());

    act(() => { mostrarFalhaDoEnvioDeEmail(erroDoServidor); });

    // O único erro é o genérico, com id próprio — o toast do PDF segue «a carregar».
    expect(aviso.error).toHaveBeenCalledWith(TITULO_DA_FALHA, expect.objectContaining({
      id: "falha-envio-email",
    }));
    expect(aviso.error).not.toHaveBeenCalledWith(TITULO_DA_FALHA, expect.objectContaining({
      id: "bg-task-task_pdf",
    }));
  });
});
