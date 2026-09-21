/**
 * Testes do feedback de UX do Motor de Simulação Financeira.
 * Correr com: node --test frontend/src/utils/financialEngineFeedback.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  FINANCIAL_ENGINE_MESSAGE,
  FINANCIAL_ENGINE_TOAST_ID,
  buildFinancialEngineToast,
  notifyFinancialEngine,
  readFinancialEngineResult,
} from "./financialEngineFeedback.js";

describe("readFinancialEngineResult", () => {
  it("lê o bloco financial_engine de uma resposta disparada", () => {
    const result = readFinancialEngineResult({
      success: true,
      financial_engine: { triggered: true, task_id: "task_abc", documents: 3 },
    });
    assert.deepEqual(result, {
      triggered: true,
      taskId: "task_abc",
      documents: 3,
    });
  });

  it("trata respostas antigas sem o bloco (retrocompatibilidade)", () => {
    assert.deepEqual(readFinancialEngineResult({ success: true }), {
      triggered: false,
      taskId: null,
      documents: 0,
    });
    assert.deepEqual(readFinancialEngineResult(null), {
      triggered: false,
      taskId: null,
      documents: 0,
    });
    assert.deepEqual(readFinancialEngineResult(undefined), {
      triggered: false,
      taskId: null,
      documents: 0,
    });
  });

  it("normaliza contagens inválidas para zero", () => {
    const result = readFinancialEngineResult({
      financial_engine: { triggered: true, documents: "muitos" },
    });
    assert.equal(result.documents, 0);
  });

  it("não considera disparado quando triggered é falso", () => {
    const result = readFinancialEngineResult({
      financial_engine: {
        triggered: false,
        reason: "sem_documentos_financeiros",
      },
    });
    assert.equal(result.triggered, false);
  });
});

describe("buildFinancialEngineToast", () => {
  it("constrói o toast informativo com a contagem de documentos", () => {
    const toast = buildFinancialEngineToast({
      financial_engine: { triggered: true, task_id: "task_1", documents: 3 },
    });
    assert.equal(toast.id, FINANCIAL_ENGINE_TOAST_ID);
    assert.equal(toast.message, FINANCIAL_ENGINE_MESSAGE);
    assert.match(toast.description, /3 documentos financeiros/);
    assert.match(toast.description, /Documentos/);
  });

  it("usa o singular com um único documento", () => {
    const toast = buildFinancialEngineToast({
      financial_engine: { triggered: true, documents: 1 },
    });
    assert.match(toast.description, /1 documento financeiro\./);
  });

  it("degrada para texto genérico sem contagem", () => {
    const toast = buildFinancialEngineToast({
      financial_engine: { triggered: true },
    });
    assert.match(toast.description, /documentos financeiros indexados/);
  });

  it("devolve null quando o motor não arrancou", () => {
    assert.equal(
      buildFinancialEngineToast({
        financial_engine: { triggered: false, reason: "processo_nao_credito" },
      }),
      null
    );
    assert.equal(buildFinancialEngineToast({ success: true }), null);
    assert.equal(buildFinancialEngineToast(null), null);
  });
});

describe("notifyFinancialEngine", () => {
  it("chama o notificador com mensagem, id e descrição", () => {
    const calls = [];
    const shown = notifyFinancialEngine(
      { financial_engine: { triggered: true, documents: 2 } },
      (message, options) => calls.push({ message, options })
    );
    assert.equal(shown, true);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].message, FINANCIAL_ENGINE_MESSAGE);
    assert.equal(calls[0].options.id, FINANCIAL_ENGINE_TOAST_ID);
    assert.ok(calls[0].options.description.length > 0);
  });

  it("não notifica quando o motor não arrancou", () => {
    const calls = [];
    const shown = notifyFinancialEngine({ success: true }, () =>
      calls.push(1)
    );
    assert.equal(shown, false);
    assert.equal(calls.length, 0);
  });

  it("não rebenta sem notificador", () => {
    assert.equal(
      notifyFinancialEngine(
        { financial_engine: { triggered: true } },
        undefined
      ),
      false
    );
  });
});
