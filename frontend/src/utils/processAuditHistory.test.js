/**
 * PACOTE DS — helpers de histórico de auditoria + seleção IA no Dashboard.
 * Run with: node --test frontend/src/utils/processAuditHistory.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  classifyAuditEvent,
  describeAuditEvent,
  findProcessBySelectValue,
  mergeAuditEvents,
  resolveProcessId,
} from "./processAuditHistory.js";

describe("classifyAuditEvent / describeAuditEvent", () => {
  it("prefers backend event_type and description", () => {
    const entry = {
      event_type: "status_change",
      description: "Fase alterada de A para B",
      action: "Alterou estado",
    };
    assert.equal(classifyAuditEvent(entry), "status_change");
    assert.equal(describeAuditEvent(entry), "Fase alterada de A para B");
  });

  it("builds a phase sentence from old/new status", () => {
    const entry = {
      action: "Moveu processo",
      field: "status",
      old_value: "clientes_espera",
      new_value: "fase_documental",
    };
    assert.equal(classifyAuditEvent(entry), "status_change");
    assert.equal(
      describeAuditEvent(entry),
      "Fase alterada de clientes_espera para fase_documental",
    );
  });

  it("classifies document, email and comment events", () => {
    assert.equal(classifyAuditEvent({ action: "Carregou documento IRS.pdf" }), "document");
    assert.equal(classifyAuditEvent({ action: "Enviou email" }), "email");
    assert.equal(classifyAuditEvent({ comment: "Nota rápida", user_name: "Ana" }), "comment");
  });
});

describe("mergeAuditEvents", () => {
  it("merges history and activities newest first without duplicating ids", () => {
    const merged = mergeAuditEvents(
      [{ id: "h1", action: "Alterou estado", created_at: "2026-08-02T10:00:00Z" }],
      [
        { id: "h1", comment: "dup", created_at: "2026-08-02T10:00:00Z" },
        { id: "a1", comment: "Olá", created_at: "2026-08-03T10:00:00Z" },
      ],
    );
    assert.equal(merged.length, 2);
    assert.equal(merged[0].id, "a1");
    assert.equal(merged[1].id, "h1");
  });
});

describe("findProcessBySelectValue", () => {
  const processes = [
    { id: "proc-1", client_id: "cli-1", client_name: "Ana" },
    { id: "proc-2", client_id: "cli-2", client_name: "Bruno" },
  ];

  it("captures the process id from the select value", () => {
    const found = findProcessBySelectValue(processes, "proc-2");
    assert.equal(resolveProcessId(found), "proc-2");
    assert.equal(found.client_name, "Bruno");
  });

  it("also matches client_id when the select stores that", () => {
    const found = findProcessBySelectValue(processes, "cli-1");
    assert.equal(resolveProcessId(found), "proc-1");
  });

  it("returns null for empty or unknown values", () => {
    assert.equal(findProcessBySelectValue(processes, ""), null);
    assert.equal(findProcessBySelectValue(processes, "missing"), null);
    assert.equal(findProcessBySelectValue(null, "proc-1"), null);
  });
});
