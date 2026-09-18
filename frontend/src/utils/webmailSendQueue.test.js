/**
 * Testes unitários (node --test) — PACOTE 9: helpers do Undo Send.
 * Correr: node --test src/utils/webmailSendQueue.test.js
 */
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  parseSendResponse,
  buildComposerSnapshot,
  draftToComposerFields,
} from "./webmailSendQueue.js";

test("parseSendResponse extrai queue/send_id/janela", () => {
  const r = parseSendResponse({
    success: true,
    queued: true,
    send_id: "abc-123",
    undo_window_seconds: 10,
  });
  assert.equal(r.queued, true);
  assert.equal(r.sendId, "abc-123");
  assert.equal(r.undoWindowMs, 10000);
});

test("parseSendResponse ignora respostas antigas/inválidas", () => {
  assert.equal(parseSendResponse(null).queued, false);
  assert.equal(parseSendResponse(undefined).sendId, null);
  assert.equal(parseSendResponse({ success: true }).queued, false);
  assert.equal(parseSendResponse({ queued: true, send_id: "" }).sendId, null);
  // janela inválida/negativa → 0 (sem undo)
  assert.equal(parseSendResponse({ queued: true, send_id: "x", undo_window_seconds: -5 }).undoWindowMs, 0);
  assert.equal(parseSendResponse({ queued: true, send_id: "x", undo_window_seconds: "abc" }).undoWindowMs, 0);
});

test("buildComposerSnapshot devolve cópia profunda do estado", () => {
  const state = {
    composerData: { to_emails: "a@b.pt", subject: "Olá" },
    uploadAttachments: [{ id: "1", file_name: "f.pdf" }],
  };
  const snap = buildComposerSnapshot(state);
  assert.deepEqual(snap.composerData, state.composerData);
  assert.equal(snap.uploadAttachments.length, 1);
  // mutar o original não afecta o snapshot
  state.composerData.subject = "MUDADO";
  state.uploadAttachments[0].file_name = "MUDADO.pdf";
  assert.equal(snap.composerData.subject, "Olá");
  assert.equal(snap.uploadAttachments[0].file_name, "f.pdf");
});

test("draftToComposerFields converte draft do backend para o composer", () => {
  const fields = draftToComposerFields({
    to_emails: ["a@b.pt", "c@d.pt"],
    cc_emails: ["e@f.pt"],
    subject: "Assunto",
    body: "Corpo",
    process_id: "proc-1",
  });
  assert.equal(fields.to_emails, "a@b.pt, c@d.pt");
  assert.equal(fields.cc_emails, "e@f.pt");
  assert.equal(fields.subject, "Assunto");
  assert.equal(fields.body, "Corpo");
  assert.equal(fields.process_id, "proc-1");
});

test("draftToComposerFields tolera null/strings/draft vazio", () => {
  const empty = draftToComposerFields(null);
  assert.equal(empty.to_emails, "");
  assert.equal(empty.process_id, null);

  const strings = draftToComposerFields({
    to_emails: "a@b.pt",
    cc_emails: null,
    subject: 123,
    body: null,
  });
  assert.equal(strings.to_emails, "a@b.pt");
  assert.equal(strings.cc_emails, "");
  assert.equal(strings.subject, "");
});
