/**
 * PACOTE 8 — seletor unificado de caixas do Webmail.
 * Run: node --test src/utils/webmailMailbox.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  applyMailboxSelection,
  buildMailboxOptions,
  resolveMailboxSelection,
} from "./webmailMailbox.js";

describe("buildMailboxOptions", () => {
  it("inclui o sufixo da empresa nas contas multi-empresa (scope=all)", () => {
    const options = buildMailboxOptions({
      personalAccounts: [
        { email_address: "geral@power.pt", company_name: "Power" },
        { email_address: "geral@precision.pt", company_name: "Precision" },
      ],
    });
    assert.equal(options.length, 2);
    assert.match(options[0].label, /Caixa Pessoal \(geral@power\.pt · Power\)/);
    assert.match(options[1].label, /Caixa Pessoal \(geral@precision\.pt · Precision\)/);
  });

  it("PACOTE 8 — mostra a Caixa de Indexação quando hasSharedIndexacao (sem trocar de perfil)", () => {
    const options = buildMailboxOptions({
      personalAccounts: [{ email_address: "a@x.pt" }],
      hasSharedIndexacao: true,
    });
    assert.equal(options.length, 2);
    assert.equal(options[1].value, "shared_indexacao");
    assert.match(options[1].label, /Indexação/);
  });

  it("sem hasSharedIndexacao mantém apenas as contas pessoais", () => {
    const options = buildMailboxOptions({
      personalAccounts: [{ email_address: "a@x.pt" }],
    });
    assert.equal(options.length, 1);
    assert.equal(options[0].value, "personal:a@x.pt");
  });

  it("marca contas is_caixa_geral como Caixa Geral com email + empresa", () => {
    const options = buildMailboxOptions({
      personalAccounts: [
        { email_address: "geral@x.pt", is_caixa_geral: true, company_name: "X" },
      ],
    });
    assert.equal(options.length, 1);
    assert.match(options[0].label, /^Caixa Geral \(geral@x\.pt · X\)$/);
  });

  it("sem contas configuradas cai na Caixa Pessoal neutra", () => {
    const options = buildMailboxOptions({ personalAccounts: [] });
    assert.equal(options.length, 1);
    assert.equal(options[0].value, "personal:");
  });

  it("remove duplicados por endereço (mesma caixa em empresas diferentes)", () => {
    const options = buildMailboxOptions({
      personalAccounts: [
        { email_address: "a@x.pt", company_name: "A" },
        { email_address: "a@x.pt", company_name: "B" },
      ],
    });
    assert.equal(options.length, 1);
  });
});

describe("applyMailboxSelection / resolveMailboxSelection", () => {
  it("selecciona a caixa partilhada de indexação pelo Select", () => {
    const next = applyMailboxSelection("shared_indexacao");
    assert.equal(next.activeBox, "shared_indexacao");
    assert.equal(
      resolveMailboxSelection({ activeBox: "shared_indexacao" }),
      "shared_indexacao",
    );
  });

  it("selecciona caixa geral", () => {
    const next = applyMailboxSelection("general");
    assert.equal(next.activeBox, "general");
  });

  it("selecciona caixa pessoal por email", () => {
    const next = applyMailboxSelection("personal:geral@x.pt");
    assert.equal(next.activeBox, "personal");
    assert.equal(next.selectedMailbox, "geral@x.pt");
    assert.equal(
      resolveMailboxSelection({ activeBox: "personal", selectedMailbox: "geral@x.pt" }),
      "personal:geral@x.pt",
    );
  });
});
