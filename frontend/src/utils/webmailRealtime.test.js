/**
 * Testes da inserção em tempo real na lista do Webmail.
 * Correr com: node --test frontend/src/utils/webmailRealtime.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  eventToEmailRow,
  insertEmailIntoList,
  shouldInsertEmail,
} from "./webmailRealtime.js";

const EVENTO = {
  email_id: "e-novo",
  from_email: "ana@cliente.pt",
  subject: "IRS 2025",
  account: "geral@empresa.pt",
  direction: "received",
  folder: "inbox",
  is_read: false,
  sent_at: "2026-09-21T10:00:00Z",
};

const LISTA = {
  emails: [{ id: "e-antigo", subject: "Anterior", is_read: true }],
  total: 1,
  page: 1,
  unread_count: 0,
};

describe("eventToEmailRow", () => {
  it("converte o evento numa linha utilizável", () => {
    const row = eventToEmailRow(EVENTO);
    assert.equal(row.id, "e-novo");
    assert.equal(row.from_email, "ana@cliente.pt");
    assert.equal(row.subject, "IRS 2025");
    assert.equal(row.is_read, false);
    assert.equal(row.is_realtime, true, "a UI pode assinalar a linha que chegou ao vivo");
  });

  it("assume não-lido quando o evento não o diz", () => {
    const row = eventToEmailRow({ email_id: "x" });
    assert.equal(row.is_read, false);
  });

  it("usa created_at quando não há sent_at", () => {
    const row = eventToEmailRow({ email_id: "x", created_at: "2026-01-01T00:00:00Z" });
    assert.equal(row.sent_at, "2026-01-01T00:00:00Z");
  });

  it("rejeita eventos sem identificador", () => {
    assert.equal(eventToEmailRow({ subject: "sem id" }), null);
    assert.equal(eventToEmailRow(null), null);
    assert.equal(eventToEmailRow("texto"), null);
  });
});

describe("shouldInsertEmail", () => {
  it("aceita um email da caixa de entrada com a entrada aberta", () => {
    assert.equal(shouldInsertEmail(EVENTO, { folder: "inbox", page: 1 }), true);
  });

  it("recusa um email recebido quando se está em Enviados", () => {
    assert.equal(shouldInsertEmail(EVENTO, { folder: "sent", page: 1 }), false);
  });

  it("recusa fora da primeira página", () => {
    assert.equal(shouldInsertEmail(EVENTO, { folder: "inbox", page: 2 }), false);
  });

  it("recusa com pesquisa activa (a relevância é decisão do servidor)", () => {
    assert.equal(
      shouldInsertEmail(EVENTO, { folder: "inbox", page: 1, search: "contrato" }),
      false
    );
  });

  it("recusa email de outra caixa", () => {
    assert.equal(
      shouldInsertEmail(EVENTO, { folder: "inbox", page: 1, mailbox: "outra@empresa.pt" }),
      false
    );
  });

  it("aceita quando a caixa aberta é a do email", () => {
    assert.equal(
      shouldInsertEmail(EVENTO, { folder: "inbox", page: 1, mailbox: "geral@empresa.pt" }),
      true
    );
  });

  it("deduz a pasta pela direção quando o evento não a traz", () => {
    const enviado = { email_id: "s1", direction: "sent" };
    assert.equal(shouldInsertEmail(enviado, { folder: "sent", page: 1 }), true);
    assert.equal(shouldInsertEmail(enviado, { folder: "inbox", page: 1 }), false);
  });

  it("tolera entradas inválidas", () => {
    assert.equal(shouldInsertEmail(null, { folder: "inbox" }), false);
    assert.equal(shouldInsertEmail({ subject: "sem id" }, { folder: "inbox" }), false);
  });
});

describe("insertEmailIntoList", () => {
  it("insere no TOPO e incrementa totais", () => {
    const next = insertEmailIntoList(LISTA, EVENTO);
    assert.equal(next.emails.length, 2);
    assert.equal(next.emails[0].id, "e-novo", "o email novo fica em primeiro");
    assert.equal(next.total, 2);
    assert.equal(next.unread_count, 1);
  });

  it("NÃO duplica um email que já esteja na lista", () => {
    const comOEmail = { ...LISTA, emails: [{ id: "e-novo" }, ...LISTA.emails] };
    const next = insertEmailIntoList(comOEmail, EVENTO);
    assert.equal(next, comOEmail, "devolve a mesma referência — sem re-render");
    assert.equal(next.emails.length, 2);
  });

  it("não conta para não-lidos um email já lido", () => {
    const next = insertEmailIntoList(LISTA, { ...EVENTO, is_read: true });
    assert.equal(next.unread_count, 0);
    assert.equal(next.total, 2);
  });

  it("não muta a lista original", () => {
    const antes = JSON.parse(JSON.stringify(LISTA));
    insertEmailIntoList(LISTA, EVENTO);
    assert.deepEqual(LISTA, antes);
  });

  it("tolera cache vazia ou malformada", () => {
    assert.equal(insertEmailIntoList(undefined, EVENTO), undefined);
    assert.equal(insertEmailIntoList({}, EVENTO).emails, undefined);
  });

  it("ignora um evento sem id", () => {
    assert.equal(insertEmailIntoList(LISTA, { subject: "sem id" }), LISTA);
  });
});
