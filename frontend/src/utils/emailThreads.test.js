/**
 * Testes do agrupamento em conversas e das acções de resposta.
 * Correr com: node --test frontend/src/utils/emailThreads.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  buildReplyAllRecipients,
  buildReplyThreadHeaders,
  groupEmailsIntoThreads,
  normalizeMessageId,
  normalizeSubject,
  parseReferences,
  threadKey,
} from "./emailThreads.js";

describe("normalizeMessageId", () => {
  it("põe o id na forma canónica", () => {
    assert.equal(normalizeMessageId("abc@x.pt"), "<abc@x.pt>");
    assert.equal(normalizeMessageId("<abc@x.pt>"), "<abc@x.pt>");
    assert.equal(normalizeMessageId("  <abc@x.pt> "), "<abc@x.pt>");
  });

  it("rejeita vazios", () => {
    [null, undefined, "", "   ", "<>"].forEach((v) => {
      assert.equal(normalizeMessageId(v), null, String(v));
    });
  });
});

describe("normalizeSubject", () => {
  it("remove prefixos repetidos e localizados", () => {
    assert.equal(normalizeSubject("Re: Crédito"), "Crédito");
    assert.equal(normalizeSubject("Fwd: Re: Enc: Proposta"), "Proposta");
    assert.equal(normalizeSubject("RES: Proposta"), "Proposta");
    assert.equal(normalizeSubject("Re[2]: Proposta"), "Proposta");
  });

  it("normaliza espaços", () => {
    assert.equal(normalizeSubject("  Crédito   Habitação "), "Crédito Habitação");
  });
});

describe("parseReferences", () => {
  it("aceita string de cabeçalho e lista", () => {
    assert.deepEqual(parseReferences("<a@x.pt> <b@x.pt>"), ["<a@x.pt>", "<b@x.pt>"]);
    assert.deepEqual(parseReferences(["a@x.pt"]), ["<a@x.pt>"]);
  });

  it("preserva ordem e remove duplicados", () => {
    assert.deepEqual(parseReferences("<a@x.pt> <b@x.pt> <a@x.pt>"), [
      "<a@x.pt>",
      "<b@x.pt>",
    ]);
  });
});

describe("threadKey", () => {
  it("prefere a raiz de references", () => {
    assert.equal(
      threadKey({
        references: "<raiz@x.pt> <meio@x.pt>",
        in_reply_to: "<meio@x.pt>",
        message_id: "<folha@x.pt>",
      }),
      "<raiz@x.pt>"
    );
  });

  it("cai para in_reply_to, depois message_id, depois assunto", () => {
    assert.equal(threadKey({ in_reply_to: "<pai@x.pt>" }), "<pai@x.pt>");
    assert.equal(threadKey({ message_id: "<eu@x.pt>" }), "<eu@x.pt>");
    assert.equal(threadKey({ subject: "Re: Crédito" }), "subject:crédito");
  });

  it("dá a mesma chave ao original e à resposta sem cabeçalhos", () => {
    assert.equal(threadKey({ subject: "Crédito" }), threadKey({ subject: "RE: Crédito" }));
  });
});

describe("groupEmailsIntoThreads", () => {
  const conversa = [
    { id: "3", message_id: "<c@x.pt>", references: "<a@x.pt> <b@x.pt>", subject: "Re: Crédito", sent_at: "2026-09-21T12:00:00Z", is_read: false },
    { id: "1", message_id: "<a@x.pt>", subject: "Crédito", sent_at: "2026-09-21T10:00:00Z", is_read: true },
    { id: "2", message_id: "<b@x.pt>", references: "<a@x.pt>", subject: "Re: Crédito", sent_at: "2026-09-21T11:00:00Z", is_read: false },
  ];

  it("junta 3 mensagens numa só conversa", () => {
    const threads = groupEmailsIntoThreads(conversa);
    assert.equal(threads.length, 1, "5 linhas na caixa passam a 1");
    assert.equal(threads[0].count, 3);
    assert.equal(threads[0].key, "<a@x.pt>");
  });

  it("mostra a mensagem mais recente como cabeça da conversa", () => {
    const [thread] = groupEmailsIntoThreads(conversa);
    assert.equal(thread.latest.id, "3");
    assert.deepEqual(thread.emails.map((e) => e.id), ["3", "2", "1"]);
  });

  it("conta os não-lidos da conversa", () => {
    assert.equal(groupEmailsIntoThreads(conversa)[0].unreadCount, 2);
  });

  it("mantém conversas distintas separadas", () => {
    const threads = groupEmailsIntoThreads([
      { id: "1", message_id: "<a@x.pt>", subject: "Crédito" },
      { id: "2", message_id: "<z@x.pt>", subject: "Seguro" },
    ]);
    assert.equal(threads.length, 2);
  });

  it("não funde emails sem pistas nenhumas", () => {
    // Juntá-los numa thread "sem assunto" seria pior do que não agrupar.
    const threads = groupEmailsIntoThreads([{ id: "1" }, { id: "2" }]);
    assert.equal(threads.length, 2);
  });

  it("assinala anexos na conversa", () => {
    const threads = groupEmailsIntoThreads([
      { id: "1", message_id: "<a@x.pt>", attachments: [{ filename: "irs.pdf" }] },
    ]);
    assert.equal(threads[0].hasAttachments, true);
  });

  it("tolera entradas vazias ou inválidas", () => {
    assert.deepEqual(groupEmailsIntoThreads([]), []);
    assert.deepEqual(groupEmailsIntoThreads(null), []);
    assert.equal(groupEmailsIntoThreads([null, { id: "1" }]).length, 1);
  });

  it("não muta a lista original", () => {
    const original = [...conversa];
    groupEmailsIntoThreads(conversa);
    assert.deepEqual(conversa, original);
  });
});

describe("buildReplyAllRecipients", () => {
  const recebido = {
    direction: "received",
    from_email: "ana@cliente.pt",
    to_emails: ["eu@empresa.pt", "colega@empresa.pt"],
    cc_emails: ["chefe@empresa.pt"],
  };

  it("põe o remetente em Para e os restantes em Cc", () => {
    const { to, cc } = buildReplyAllRecipients(recebido, "eu@empresa.pt");
    assert.deepEqual(to, ["ana@cliente.pt"]);
    assert.deepEqual(cc, ["colega@empresa.pt", "chefe@empresa.pt"]);
  });

  it("remove o próprio utilizador — não se responde a si mesmo", () => {
    const { to, cc } = buildReplyAllRecipients(recebido, "eu@empresa.pt");
    assert.ok(![...to, ...cc].some((e) => e === "eu@empresa.pt"));
  });

  it("ignora maiúsculas ao remover o próprio", () => {
    const { cc } = buildReplyAllRecipients(recebido, "EU@Empresa.PT");
    assert.ok(!cc.includes("eu@empresa.pt"));
  });

  it("não duplica um endereço presente em To e Cc", () => {
    const { to, cc } = buildReplyAllRecipients(
      { ...recebido, cc_emails: ["ana@cliente.pt", "chefe@empresa.pt"] },
      "eu@empresa.pt"
    );
    assert.deepEqual(to, ["ana@cliente.pt"]);
    assert.deepEqual(cc, ["colega@empresa.pt", "chefe@empresa.pt"]);
  });

  it("ao responder a um email NOSSO mantém os destinatários originais", () => {
    const { to } = buildReplyAllRecipients(
      { direction: "sent", from_email: "eu@empresa.pt", to_emails: ["ana@cliente.pt"] },
      "eu@empresa.pt"
    );
    assert.deepEqual(to, ["ana@cliente.pt"]);
  });

  it("aceita destinatários em string separada por vírgulas", () => {
    const { cc } = buildReplyAllRecipients(
      { direction: "received", from_email: "ana@cliente.pt", to_emails: "a@x.pt, b@x.pt" },
      "eu@empresa.pt"
    );
    assert.deepEqual(cc, ["a@x.pt", "b@x.pt"]);
  });

  it("tolera entradas inválidas", () => {
    assert.deepEqual(buildReplyAllRecipients(null, "eu@x.pt"), { to: [], cc: [] });
  });
});

describe("buildReplyThreadHeaders", () => {
  it("aponta In-Reply-To ao pai e estende a cadeia", () => {
    const headers = buildReplyThreadHeaders({
      message_id: "<pai@x.pt>",
      references: "<avo@x.pt>",
    });
    assert.equal(headers.in_reply_to, "<pai@x.pt>");
    assert.deepEqual(headers.references, ["<avo@x.pt>", "<pai@x.pt>"]);
  });

  it("arranca uma cadeia quando o pai é a raiz", () => {
    const headers = buildReplyThreadHeaders({ message_id: "<pai@x.pt>" });
    assert.deepEqual(headers.references, ["<pai@x.pt>"]);
  });

  it("devolve vazio quando o pai não tem Message-ID", () => {
    // Sem id do pai não há thread possível — melhor não inventar.
    const headers = buildReplyThreadHeaders({ subject: "Sem id" });
    assert.equal(headers.in_reply_to, null);
    assert.deepEqual(headers.references, []);
  });
});
