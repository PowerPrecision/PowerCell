/**
 * Testes da lógica pura de reactividade a eventos de tarefa.
 * Correr com: node --test frontend/src/utils/taskEvents.test.js
 *
 * O hook (`hooks/useTaskEvents.js`) precisa de React + WebSocket; aqui
 * exercita-se o motor de merge que ele usa.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  applyTaskEvent,
  countActiveTasks,
  isFromSource,
  TASK_EVENT_TYPES,
  TASK_SOURCE,
  taskEventToPatch,
} from "./taskEvents.js";

describe("TASK_EVENT_TYPES", () => {
  it("cobre os quatro eventos do contrato com o backend", () => {
    assert.deepEqual(TASK_EVENT_TYPES, [
      "task_started",
      "task_progress",
      "task_completed",
      "task_failed",
    ]);
  });
});

describe("taskEventToPatch", () => {
  it("traduz os nomes curtos do evento para os da API", () => {
    const patch = taskEventToPatch({
      task_id: "t1",
      status: "completed",
      progress: 100,
      message: "Pronto",
      error: "nenhum",
      result: { document_id: "d1" },
    });
    assert.equal(patch.task_id, "t1");
    assert.equal(patch.progress_message, "Pronto");
    assert.equal(patch.error_message, "nenhum");
    assert.deepEqual(patch.result_data, { document_id: "d1" });
  });

  it("omite campos ausentes para o merge preservar o que já se sabe", () => {
    const patch = taskEventToPatch({ task_id: "t1", progress: 40 });
    assert.deepEqual(patch, { task_id: "t1", progress: 40 });
    assert.ok(!("title" in patch));
    assert.ok(!("status" in patch));
  });

  it("mantém progresso 0 (é informação, não ausência)", () => {
    assert.equal(taskEventToPatch({ task_id: "t1", progress: 0 }).progress, 0);
  });

  it("tolera payloads inválidos", () => {
    assert.deepEqual(taskEventToPatch(null), {});
    assert.deepEqual(taskEventToPatch(undefined), {});
    assert.deepEqual(taskEventToPatch("string"), {});
  });
});

describe("applyTaskEvent", () => {
  const existente = [
    { task_id: "t1", title: "Proposta", status: "processing", progress: 20 },
    { task_id: "t2", title: "Importação", status: "pending", progress: 0 },
  ];

  it("funde o evento na tarefa correspondente", () => {
    const next = applyTaskEvent(existente, {
      task_id: "t1",
      status: "completed",
      progress: 100,
    });
    assert.equal(next[0].status, "completed");
    assert.equal(next[0].progress, 100);
    assert.equal(next[0].title, "Proposta", "campos omitidos preservam-se");
  });

  it("não altera as outras tarefas", () => {
    const next = applyTaskEvent(existente, { task_id: "t1", progress: 60 });
    assert.deepEqual(next[1], existente[1]);
  });

  it("não muta a lista original", () => {
    const antes = JSON.parse(JSON.stringify(existente));
    applyTaskEvent(existente, { task_id: "t1", progress: 99 });
    assert.deepEqual(existente, antes);
  });

  it("insere à cabeça uma tarefa desconhecida", () => {
    const next = applyTaskEvent(existente, {
      task_id: "t3",
      status: "pending",
      title: "Nova",
    });
    assert.equal(next.length, 3);
    assert.equal(next[0].task_id, "t3");
  });

  it("devolve a MESMA referência quando não há task_id", () => {
    const next = applyTaskEvent(existente, { status: "completed" });
    assert.equal(next, existente, "evita re-render desnecessário");
  });

  it("tolera lista ausente ou inválida", () => {
    assert.deepEqual(applyTaskEvent(null, { task_id: "t1" }), [
      { task_id: "t1" },
    ]);
    assert.deepEqual(applyTaskEvent(undefined, { task_id: "t1" }), [
      { task_id: "t1" },
    ]);
  });

  it("tolera entradas nulas dentro da lista", () => {
    const next = applyTaskEvent([null, { task_id: "t1" }], {
      task_id: "t1",
      progress: 10,
    });
    assert.equal(next[1].progress, 10);
  });
});

describe("countActiveTasks", () => {
  it("conta pending, processing e running", () => {
    const tasks = [
      { status: "pending" },
      { status: "processing" },
      { status: "running" },
      { status: "completed" },
      { status: "failed" },
    ];
    assert.equal(countActiveTasks(tasks), 3);
  });

  it("devolve 0 para listas vazias ou inválidas", () => {
    assert.equal(countActiveTasks([]), 0);
    assert.equal(countActiveTasks(null), 0);
    assert.equal(countActiveTasks(undefined), 0);
  });

  it("ignora entradas sem estado", () => {
    assert.equal(countActiveTasks([{}, null, { status: "processing" }]), 1);
  });
});

describe("isFromSource", () => {
  it("distingue task_log de background_job", () => {
    const evento = { source: TASK_SOURCE.TASK_LOG };
    assert.equal(isFromSource(evento, TASK_SOURCE.TASK_LOG), true);
    assert.equal(isFromSource(evento, TASK_SOURCE.BACKGROUND_JOB), false);
  });

  it("aceita eventos sem origem (retrocompatibilidade)", () => {
    assert.equal(isFromSource({}, TASK_SOURCE.TASK_LOG), true);
    assert.equal(isFromSource({}, TASK_SOURCE.BACKGROUND_JOB), true);
    assert.equal(isFromSource(null, TASK_SOURCE.TASK_LOG), true);
  });
});
