/**
 * Um toast que o utilizador fechou NÃO volta (Out 2026).
 *
 * O `TasksContext` chamava `toast.loading(…, {id})` a cada evento de progresso e a cada poll: um id que o
 * utilizador acabara de fechar no X já não existe no Sonner, pelo que a chamada seguinte CRIAVA outro
 * toast — o aviso «reaparecia». E o de resultado, ao fechar-se, não deixava marca: um recarregamento da
 * página, que volta a listar a tarefa por confirmar, mostrava-o outra vez.
 *
 * O Sonner é falseado ao nível da CHAMADA (`toast.*`); o `onDismiss` que o código lhe passa é o que o
 * Sonner chamaria no X, por isso o teste invoca-o: é exactamente o gesto do utilizador.
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
  default: { get: obter, post: vi.fn(), delete: vi.fn() },
  cancelBackgroundTask: vi.fn(),
}));

import { TasksProvider, useTasks } from "../TasksContext";

const PDF = {
  task_id: "t-pdf", task_type: "PDF_GEN", title: "Geração de PDF", status: "processing",
  progress: 10, progress_message: "A gerar…", priority: "normal", acknowledged_at: null,
};

let refrescar;
function Sonda() {
  const { tasks, fetchActiveTasks } = useTasks();
  refrescar = fetchActiveTasks;
  return <ul>{tasks.map((t) => <li key={t.task_id}>{t.title}</li>)}</ul>;
}

const chamadasDe = (fn, id) => fn.mock.calls.filter(([, o]) => o?.id === id);
const ultimo = (fn, id) => chamadasDe(fn, id).at(-1)?.[1];

beforeEach(() => {
  sessionStorage.clear();
  obter.mockImplementation(async () => ({ data: { tasks: estado.tarefas, active_count: estado.tarefas.length } }));
});
afterEach(() => vi.clearAllMocks());

async function montar(tarefas) {
  estado.tarefas = tarefas;
  const vista = render(<TasksProvider><Sonda /></TasksProvider>);
  await screen.findByText(tarefas[0].title);
  return vista;
}

async function actualizar() {
  await act(async () => { await refrescar(); });
}

describe("o toast «a carregar» que o utilizador fechou", () => {
  it("contraprova: sem o fechar, cada actualização volta a escrever no mesmo toast", async () => {
    await montar([{ ...PDF }]);
    await waitFor(() => expect(chamadasDe(aviso.loading, "bg-task-t-pdf").length).toBeGreaterThanOrEqual(1));
    const antes = chamadasDe(aviso.loading, "bg-task-t-pdf").length;
    await actualizar();
    expect(chamadasDe(aviso.loading, "bg-task-t-pdf").length).toBeGreaterThan(antes);
  });

  it("fechado no X, a actualização seguinte NÃO o recria", async () => {
    await montar([{ ...PDF }]);
    await waitFor(() => expect(chamadasDe(aviso.loading, "bg-task-t-pdf").length).toBeGreaterThanOrEqual(1));

    act(() => { ultimo(aviso.loading, "bg-task-t-pdf").onDismiss(); });   // o X
    const antes = chamadasDe(aviso.loading, "bg-task-t-pdf").length;

    estado.tarefas = [{ ...PDF, progress: 60, progress_message: "A meio" }];
    await actualizar();
    await actualizar();

    expect(chamadasDe(aviso.loading, "bg-task-t-pdf").length).toBe(antes);
  });

  it("nem depois de a página remontar (o registo sobrevive no sessionStorage)", async () => {
    const primeira = await montar([{ ...PDF }]);
    await waitFor(() => expect(chamadasDe(aviso.loading, "bg-task-t-pdf").length).toBeGreaterThanOrEqual(1));
    act(() => { ultimo(aviso.loading, "bg-task-t-pdf").onDismiss(); });
    primeira.unmount();
    aviso.loading.mockClear();

    await montar([{ ...PDF, progress: 80 }]);
    await actualizar();
    expect(chamadasDe(aviso.loading, "bg-task-t-pdf")).toHaveLength(0);
  });

  it("outra tarefa não é afectada: só o id fechado fica calado", async () => {
    const OUTRA = { ...PDF, task_id: "t-outra", title: "Outra tarefa" };
    await montar([{ ...PDF }, OUTRA]);
    await waitFor(() => expect(chamadasDe(aviso.loading, "bg-task-t-outra").length).toBeGreaterThanOrEqual(1));
    act(() => { ultimo(aviso.loading, "bg-task-t-pdf").onDismiss(); });
    aviso.loading.mockClear();

    await actualizar();
    expect(chamadasDe(aviso.loading, "bg-task-t-pdf")).toHaveLength(0);
    expect(chamadasDe(aviso.loading, "bg-task-t-outra").length).toBeGreaterThan(0);
  });

  it("quando a tarefa TERMINA, o resultado mostra-se na mesma (o descarte cobria só o progresso)", async () => {
    await montar([{ ...PDF }]);
    await waitFor(() => expect(chamadasDe(aviso.loading, "bg-task-t-pdf").length).toBeGreaterThanOrEqual(1));
    act(() => { ultimo(aviso.loading, "bg-task-t-pdf").onDismiss(); });

    estado.tarefas = [{ ...PDF, status: "completed", progress: 100 }];
    await actualizar();

    await waitFor(() => expect(chamadasDe(aviso.success, "bg-task-t-pdf")).toHaveLength(1));
  });
});

describe("o que o PRÓPRIO código fecha não conta como escolha do utilizador", () => {
  it("o toast retirado pelo tecto de cinco volta a poder mostrar-se (não fica calado para sempre)", async () => {
    const seis = Array.from({ length: 6 }, (_, i) => ({ ...PDF, task_id: `t-${i + 1}`, title: `Tarefa ${i + 1}` }));
    await montar(seis);
    await waitFor(() => expect(chamadasDe(aviso.loading, "bg-task-t-6").length).toBeGreaterThanOrEqual(1));
    // o tecto retirou o mais antigo; o Sonner avisa o `onDismiss` desse toast como faria num X
    expect(aviso.dismiss).toHaveBeenCalledWith("bg-task-t-1");
    act(() => { chamadasDe(aviso.loading, "bg-task-t-1")[0][1].onDismiss(); });
    aviso.loading.mockClear();

    await actualizar();
    expect(chamadasDe(aviso.loading, "bg-task-t-1").length).toBeGreaterThan(0);
  });
});

describe("o toast de resultado que o utilizador fechou", () => {
  const CONCLUIDA = { ...PDF, status: "completed", progress: 100 };

  it("contraprova: sem o fechar, uma página nova (provider novo) mostra-o outra vez", async () => {
    const primeira = await montar([{ ...CONCLUIDA }]);
    await waitFor(() => expect(chamadasDe(aviso.success, "bg-task-t-pdf")).toHaveLength(1));
    primeira.unmount();
    await montar([{ ...CONCLUIDA }]);
    await waitFor(() => expect(chamadasDe(aviso.success, "bg-task-t-pdf")).toHaveLength(2));
  });

  it("fechado no X, não volta nem com um provider novo (recarregamento da página)", async () => {
    const primeira = await montar([{ ...CONCLUIDA }]);
    await waitFor(() => expect(chamadasDe(aviso.success, "bg-task-t-pdf")).toHaveLength(1));
    act(() => { ultimo(aviso.success, "bg-task-t-pdf").onDismiss(); });
    primeira.unmount();

    await montar([{ ...CONCLUIDA }]);
    await actualizar();
    expect(chamadasDe(aviso.success, "bg-task-t-pdf")).toHaveLength(1);
  });

  it("a falha fechada também não volta", async () => {
    const FALHADA = { ...PDF, status: "failed", error_message: "boom" };
    const primeira = await montar([{ ...FALHADA }]);
    await waitFor(() => expect(chamadasDe(aviso.error, "bg-task-t-pdf")).toHaveLength(1));
    act(() => { ultimo(aviso.error, "bg-task-t-pdf").onDismiss(); });
    primeira.unmount();

    await montar([{ ...FALHADA }]);
    await actualizar();
    expect(chamadasDe(aviso.error, "bg-task-t-pdf")).toHaveLength(1);
  });

  it("fechar o aviso NÃO confirma a tarefa no servidor (uma falha tem de continuar a poder ver-se no painel)", async () => {
    const api = (await import("../../services/api")).default;
    const primeira = await montar([{ ...CONCLUIDA }]);
    await waitFor(() => expect(chamadasDe(aviso.success, "bg-task-t-pdf")).toHaveLength(1));
    act(() => { ultimo(aviso.success, "bg-task-t-pdf").onDismiss(); });
    expect(api.post).not.toHaveBeenCalled();
    primeira.unmount();
  });

  it("outra tarefa concluída continua a mostrar o seu aviso", async () => {
    const primeira = await montar([{ ...CONCLUIDA }]);
    await waitFor(() => expect(chamadasDe(aviso.success, "bg-task-t-pdf")).toHaveLength(1));
    act(() => { ultimo(aviso.success, "bg-task-t-pdf").onDismiss(); });
    primeira.unmount();

    await montar([{ ...CONCLUIDA }, { ...CONCLUIDA, task_id: "t-nova", title: "Outra" }]);
    await waitFor(() => expect(chamadasDe(aviso.success, "bg-task-t-nova")).toHaveLength(1));
  });
});

describe("o armazenamento indisponível não parte nada", () => {
  it("sem sessionStorage o registo vale só para a página e tudo funciona", async () => {
    const original = Object.getOwnPropertyDescriptor(window, "sessionStorage");
    Object.defineProperty(window, "sessionStorage", {
      configurable: true,
      get() { throw new Error("bloqueado"); },
    });
    try {
      await montar([{ ...PDF }]);
      await waitFor(() => expect(chamadasDe(aviso.loading, "bg-task-t-pdf").length).toBeGreaterThanOrEqual(1));
      act(() => { ultimo(aviso.loading, "bg-task-t-pdf").onDismiss(); });
      aviso.loading.mockClear();
      await actualizar();
      expect(chamadasDe(aviso.loading, "bg-task-t-pdf")).toHaveLength(0);
    } finally {
      Object.defineProperty(window, "sessionStorage", original);
    }
  });
});
