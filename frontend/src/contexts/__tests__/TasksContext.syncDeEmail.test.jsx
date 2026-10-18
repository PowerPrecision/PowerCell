/**
 * O toast «Sincronização de Email» não fica para sempre (Lote 4, Out 2026).
 *
 * Os toasts das tarefas em background são persistentes (`duration: Infinity`) e só o utilizador os
 * fecha. A sincronização de email, porém, é ROTINA — corre ao entrar, ao trocar de perfil, de 10 em
 * 10 minutos — e o seu toast ficava a acumular. Hoje:
 *   * o «a carregar» tem um limite (o Sonner nunca expira um toast de loading sozinho);
 *   * o sucesso desaparece sozinho;
 *   * as FALHAS ficam (com fecho), e as outras tarefas mantêm o comportamento persistente.
 */
import { act, render, screen, waitFor } from "@testing-library/react";
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

const SYNC = {
  task_id: "t-sync", task_type: "EMAIL_SYNC", title: "Sincronização de Email",
  status: "processing", progress: 0, progress_message: "A sincronizar…", priority: "normal",
};
const ENVIO = {
  task_id: "t-envio", task_type: "EMAIL_SEND", title: "Envio de Email",
  status: "processing", progress: 0, progress_message: "A enviar…", priority: "normal",
};
const OUTRA = {
  task_id: "t-pdf", task_type: "PDF_GEN", title: "Geração de PDF",
  status: "processing", progress: 0, progress_message: "A gerar…", priority: "normal",
};

let refrescar;
function Sonda() {
  const { tasks, fetchActiveTasks } = useTasks();
  refrescar = fetchActiveTasks;
  return <ul>{tasks.map((t) => <li key={t.task_id}>{t.title}</li>)}</ul>;
}

beforeEach(() => {
  obter.mockImplementation(async () => ({
    data: { tasks: estado.tarefas, active_count: estado.tarefas.length },
  }));
});
afterEach(() => {
  vi.clearAllMocks();
  vi.useRealTimers();
});

async function montar(tarefas) {
  estado.tarefas = tarefas;
  render(<TasksProvider><Sonda /></TasksProvider>);
  await screen.findByText(tarefas[0].title);
  await waitFor(() => expect(aviso.loading).toHaveBeenCalled());
}

async function terminar(tarefa, status) {
  estado.tarefas = [{ ...tarefa, status, acknowledged_at: null }];
  await act(async () => { await refrescar(); });
}

describe("toast da sincronização de email", () => {
  it("o sucesso desaparece sozinho (duração finita)", async () => {
    await montar([{ ...SYNC }]);
    await terminar(SYNC, "completed");

    await waitFor(() => expect(aviso.success).toHaveBeenCalled());
    const [, opcoes] = aviso.success.mock.calls.at(-1);
    expect(Number.isFinite(opcoes.duration)).toBe(true);
    expect(opcoes.duration).toBeLessThanOrEqual(10_000);
  });

  it("a falha NÃO desaparece sozinha: fica, com botão de fechar", async () => {
    await montar([{ ...SYNC }]);
    await terminar({ ...SYNC, error_message: "IMAP recusou" }, "failed");

    await waitFor(() => expect(aviso.error).toHaveBeenCalled());
    const [, opcoes] = aviso.error.mock.calls.at(-1);
    expect(opcoes.duration).toBe(Infinity);
    expect(opcoes.closeButton).toBe(true);
  });

  it("o «a carregar» é retirado ao fim do limite, mesmo que ninguém o termine", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await montar([{ ...SYNC }]);
    expect(aviso.dismiss).not.toHaveBeenCalledWith("bg-task-t-sync");

    await act(async () => { vi.advanceTimersByTime(95_000); });

    expect(aviso.dismiss).toHaveBeenCalledWith("bg-task-t-sync");
  });

  it("concluir antes do limite cancela o temporizador (nada é retirado depois)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await montar([{ ...SYNC }]);
    await terminar(SYNC, "completed");
    aviso.dismiss.mockClear();

    await act(async () => { vi.advanceTimersByTime(120_000); });

    expect(aviso.dismiss).not.toHaveBeenCalledWith("bg-task-t-sync");
  });
});

describe("toast do envio de email (QA-6)", () => {
  it("o sucesso de um envio desaparece sozinho", async () => {
    await montar([{ ...ENVIO }]);
    await terminar(ENVIO, "completed");
    await waitFor(() => expect(aviso.success).toHaveBeenCalled());
    const [, opcoes] = aviso.success.mock.calls.at(-1);
    expect(Number.isFinite(opcoes.duration)).toBe(true);
  });

  it("a falha de um envio FICA, com botão de fechar", async () => {
    await montar([{ ...ENVIO }]);
    await terminar({ ...ENVIO, error_message: "535" }, "failed");
    await waitFor(() => expect(aviso.error).toHaveBeenCalled());
    expect(aviso.error.mock.calls.at(-1)[1].duration).toBe(Infinity);
  });
});

describe("contraprova: as outras tarefas mantêm-se persistentes", () => {
  it("o sucesso de uma tarefa que não é sincronização de email fica até ser fechado", async () => {
    await montar([{ ...OUTRA }]);
    await terminar(OUTRA, "completed");

    await waitFor(() => expect(aviso.success).toHaveBeenCalled());
    expect(aviso.success.mock.calls.at(-1)[1].duration).toBe(Infinity);
  });

  it("e o seu «a carregar» não leva temporizador", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await montar([{ ...OUTRA }]);
    await act(async () => { vi.advanceTimersByTime(300_000); });
    expect(aviso.dismiss).not.toHaveBeenCalledWith("bg-task-t-pdf");
  });
});
