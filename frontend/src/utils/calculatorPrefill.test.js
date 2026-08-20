/**
 * Unit tests for calculator prefill + webmail mailbox helpers (Pacote DR).
 * Run with: node --test frontend/src/utils/calculatorPrefill.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  extractCalculatorPrefill,
  getProcessIdFromPath,
} from "./calculatorPrefill.js";
import {
  applyMailboxSelection,
  buildMailboxOptions,
  resolveMailboxSelection,
} from "./webmailMailbox.js";

describe("getProcessIdFromPath", () => {
  it("reads /processo/:id", () => {
    assert.equal(getProcessIdFromPath("/processo/abc-123"), "abc-123");
  });

  it("reads /process/:id", () => {
    assert.equal(getProcessIdFromPath("/process/xyz"), "xyz");
  });

  it("returns null outside a process page", () => {
    assert.equal(getProcessIdFromPath("/webmail"), null);
    assert.equal(getProcessIdFromPath("/processos"), null);
    assert.equal(getProcessIdFromPath(""), null);
  });
});

describe("extractCalculatorPrefill", () => {
  it("returns empty context without a process", () => {
    const empty = extractCalculatorPrefill(null);
    assert.equal(empty.hasContext, false);
    assert.deepEqual(empty.mortgage, {});
  });

  it("maps credit_data to mortgage fields", () => {
    const prefill = extractCalculatorPrefill({
      credit_data: {
        requested_amount: 180000,
        loan_term_years: 35,
        interest_rate: 3.2,
        monthly_payment: 720,
        spread: 1.1,
      },
      financial_data: {
        monthly_income: 2400,
        rendimento_bruto: 3100,
        capital_proprio: 20000,
      },
      real_estate_data: { valor_imovel: 220000 },
      personal_data: { idade: 38 },
    });

    assert.equal(prefill.hasContext, true);
    assert.equal(prefill.mortgage.capital, 180000);
    assert.equal(prefill.mortgage.prazoAnos, 35);
    assert.equal(prefill.mortgage.taxaJuro, 3.2);
    assert.equal(prefill.dsti.rendimento_mensal, 2400);
    assert.equal(prefill.dsti.prestacao_nova, 720);
    assert.equal(prefill.risk.valor_imovel, 220000);
    assert.equal(prefill.risk.spread, 1.1);
    assert.equal(prefill.risk.prazo_anos, 35);
  });

  it("ignores zero/invalid numeric values", () => {
    const prefill = extractCalculatorPrefill({
      credit_data: { requested_amount: 0, loan_term_years: "x" },
    });
    assert.equal(prefill.mortgage.capital, undefined);
    assert.equal(prefill.mortgage.prazoAnos, undefined);
  });
});

describe("webmail mailbox selector", () => {
  it("labels personal and general boxes clearly", () => {
    const options = buildMailboxOptions({
      personalAccounts: [
        { email_address: "joao@empresa.pt", label: "João" },
        { email_address: "geral@empresa.pt", is_caixa_geral: true },
      ],
      showGeneral: true,
      unreadByBox: { personal: 3, general: 8 },
    });
    assert.equal(options[0].label, "Caixa Pessoal (João)");
    assert.equal(options[1].label, "Caixa Geral (geral@empresa.pt)");
    assert.equal(options.length, 2);
    assert.ok(!options.some((o) => o.value === "general"));
  });

  it("does not inject a ghost Caixa Geral without email", () => {
    const options = buildMailboxOptions({
      personalAccounts: [{ email_address: "joao@empresa.pt" }],
      showGeneral: true,
    });
    assert.ok(!options.some((o) => (o.label || "").includes("Caixa Geral")));
  });

  it("locks indexacao to the shared mailbox", () => {
    const options = buildMailboxOptions({ isIndexacao: true });
    assert.equal(options.length, 1);
    assert.equal(options[0].value, "shared_indexacao");
  });

  it("round-trips selection values", () => {
    assert.deepEqual(applyMailboxSelection("general"), { activeBox: "general" });
    assert.deepEqual(applyMailboxSelection("personal:joao@x.pt"), {
      activeBox: "personal",
      selectedMailbox: "joao@x.pt",
    });
    assert.equal(
      resolveMailboxSelection({ activeBox: "personal", selectedMailbox: "a@b.pt" }),
      "personal:a@b.pt",
    );
    assert.equal(
      resolveMailboxSelection({ activeBox: "general" }),
      "general",
    );
  });
});
