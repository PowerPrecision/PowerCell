/**
 * PACOTE DS — helpers de histórico de auditoria + seleção IA no Dashboard.
 * Run with: node --test frontend/src/utils/processAuditHistory.test.js
 */
import { after, before, describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  classifyAuditEvent,
  dataDoEvento,
  describeAuditEvent,
  findProcessBySelectValue,
  instanteDoEvento,
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

describe("instanteDoEvento", () => {
  // O sandbox e o CI correm em UTC, onde «hora local» e UTC coincidem e uma
  // leitura errada de uma data sem fuso passaria despercebida (mutação que
  // sobreviveu). Um fuso com desvio torna-a observável.
  const tzAntes = process.env.TZ;
  before(() => {
    process.env.TZ = "America/Sao_Paulo";
  });
  after(() => {
    if (tzAntes === undefined) delete process.env.TZ;
    else process.env.TZ = tzAntes;
  });

  it("lê as formas de data que o sistema mistura, como o mesmo instante", () => {
    const alvo = Date.parse("2026-10-01T10:00:00Z");
    for (const v of [
      "2026-10-01T10:00:00Z",
      "2026-10-01T10:00:00+00:00",
      "2026-10-01T11:00:00+01:00",
      "2026-10-01T10:00:00",
      "2026-10-01 10:00:00",
      new Date("2026-10-01T10:00:00Z"),
      alvo,
      alvo / 1000,
    ]) {
      assert.equal(instanteDoEvento(v), alvo, String(v));
    }
  });

  it("uma data sem fuso é UTC (como o servidor as grava), não a hora local", () => {
    assert.equal(
      instanteDoEvento("2026-10-01T10:00:00"),
      instanteDoEvento("2026-10-01T10:00:00Z"),
    );
  });

  it("o que não se lê vale -Infinity", () => {
    for (const v of [undefined, null, "", "   ", "ontem", {}, [], NaN, new Date("x")]) {
      assert.equal(instanteDoEvento(v), -Infinity, String(v));
    }
  });
});

describe("mergeAuditEvents — a ordem cronológica inversa", () => {
  const ids = (lista) => lista.map((e) => e.id);

  it("mais recente primeiro, com formatos de data MISTURADOS", () => {
    // Em texto, «…+00:00» < «…Z» no mesmo segundo e «+01:00» ficava fora de
    // sítio: aqui a ordem certa é h3 (10:00:02Z) > h2 (10:00:01.500Z) > h1.
    const merged = mergeAuditEvents(
      [
        { id: "h1", action: "a", created_at: "2026-10-01T10:00:01+00:00" },
        { id: "h3", action: "c", created_at: "2026-10-01T11:00:02+01:00" },
      ],
      [{ id: "a2", comment: "b", created_at: "2026-10-01T10:00:01.500Z" }],
    );
    assert.deepEqual(ids(merged), ["h3", "a2", "h1"]);
  });

  it("o mesmo segundo em formatos diferentes não troca a ordem real", () => {
    const merged = mergeAuditEvents(
      [
        { id: "antes", action: "a", created_at: "2026-10-01T10:00:00.100000+00:00" },
        { id: "depois", action: "b", created_at: "2026-10-01T10:00:00.900Z" },
      ],
      [],
    );
    assert.deepEqual(ids(merged), ["depois", "antes"]);
  });

  it("um fuso diferente ordena pelo instante e não pelo texto", () => {
    const merged = mergeAuditEvents(
      [
        // 09:30Z — escrito com «10:30» mas é MAIS ANTIGO que 10:00Z.
        { id: "antigo", action: "a", created_at: "2026-10-01T10:30:00+01:00" },
        { id: "novo", action: "b", created_at: "2026-10-01T10:00:00Z" },
      ],
      [],
    );
    assert.deepEqual(ids(merged), ["novo", "antigo"]);
  });

  it("eventos sem data legível vão para o FIM, nunca para o topo", () => {
    const merged = mergeAuditEvents(
      [
        { id: "sem", action: "a", created_at: "" },
        { id: "datado", action: "b", created_at: "2020-01-01T00:00:00Z" },
        { id: "lixo", action: "c", created_at: "ontem" },
      ],
      [],
    );
    assert.deepEqual(ids(merged), ["datado", "sem", "lixo"]);
  });

  it("empates mantêm a ordem de chegada (estável)", () => {
    const merged = mergeAuditEvents(
      [
        { id: "x", action: "a", created_at: "2026-10-01T10:00:00Z" },
        { id: "y", action: "b", created_at: "2026-10-01T10:00:00+00:00" },
      ],
      [],
    );
    assert.deepEqual(ids(merged), ["x", "y"]);
  });

  it("entradas inválidas na lista não rebentam", () => {
    const merged = mergeAuditEvents([null, undefined, "x", { id: "ok", action: "a", created_at: "2026-10-01T10:00:00Z" }], [null]);
    assert.deepEqual(ids(merged), ["ok"]);
  });

  it("um objecto (e não lista) nunca rebenta", () => {
    assert.deepEqual(mergeAuditEvents({}, {}), []);
  });

  it("a data mostrada é a MESMA com que se ordena", () => {
    assert.equal(
      dataDoEvento({ created_at: "2026-10-01T10:00:00Z", timestamp: "1999-01-01T00:00:00Z" }),
      "2026-10-01T10:00:00Z",
    );
    assert.equal(dataDoEvento({ timestamp: "2026-10-01T10:00:00Z" }), "2026-10-01T10:00:00Z");
    assert.equal(dataDoEvento(null), "");
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
