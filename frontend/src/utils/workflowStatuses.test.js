/**
 * Testes unitários (node --test) — PACOTE 11 (Eixo 1): dropdown de estado
 * 100% dinâmica (sem fallback estático hardcoded de fases).
 * Correr: node --test src/utils/workflowStatuses.test.js
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import { formatStatusLabel, buildStatusOptions } from "./workflowStatuses.js";

test("formatStatusLabel humaniza nomes técnicos", () => {
  assert.equal(formatStatusLabel("clientes_espera"), "Clientes Espera");
  assert.equal(formatStatusLabel("pre_registo"), "Pre Registo");
  assert.equal(formatStatusLabel(null), "—");
  assert.equal(formatStatusLabel(""), "—");
});

test("buildStatusOptions usa APENAS a lista dinâmica (sem inventar fases)", () => {
  const dynamic = [
    { id: "1", name: "fase_a", label: "Fase A", color: "blue", order: 1 },
    { id: "2", name: "fase_b", label: "Fase B", color: "green", order: 2 },
  ];
  const options = buildStatusOptions(dynamic, "fase_a");
  assert.equal(options.length, 2);
  assert.deepEqual(options.map((o) => o.name), ["fase_a", "fase_b"]);
});

test("lista dinâmica vazia NÃO devolve fases hardcoded (Pacote 11)", () => {
  // Antes do Pacote 11, uma API vazia injectava ~40 fases cravadas em
  // código (KNOWN_PROCESS_STATUSES). Agora devolve [] — as fases vêm
  // apenas da colecção workflow_statuses via API.
  const options = buildStatusOptions([], null);
  assert.equal(options.length, 0);
  const nullOptions = buildStatusOptions(undefined, undefined);
  assert.equal(nullOptions.length, 0);
});

test("currentStatus ausente da lista dinâmica é injectado como fallback único", () => {
  const dynamic = [{ id: "1", name: "fase_a", label: "Fase A", order: 1 }];
  const options = buildStatusOptions(dynamic, "fase_removida_pelo_admin");
  assert.equal(options.length, 2);
  const fallback = options.find((o) => o.name === "fase_removida_pelo_admin");
  assert.ok(fallback);
  assert.equal(fallback._isFallback, true);
  assert.equal(fallback.label, "Fase Removida Pelo Admin");
  // Fallback ordenado no fim
  assert.equal(options[options.length - 1].name, "fase_removida_pelo_admin");
});

test("currentStatus duplicado na dinâmica não gera opções repetidas", () => {
  const dynamic = [
    { id: "1", name: "fase_a", label: "Fase A", order: 1 },
    { id: "2", name: "fase_b", label: "Fase B", order: 2 },
  ];
  const options = buildStatusOptions(dynamic, "fase_b");
  assert.equal(options.length, 2);
});

test("ordenação por order asc com order ausente no fim", () => {
  const dynamic = [
    { id: "1", name: "sem_order" },
    { id: "2", name: "primeira", order: 1 },
    { id: "3", name: "segunda", order: 2 },
  ];
  const options = buildStatusOptions(dynamic, null);
  assert.deepEqual(options.map((o) => o.name), ["primeira", "segunda", "sem_order"]);
});
