/**
 * Testes do merge do delta de processo (WebSocket → estado local).
 * Correr com: node --test frontend/src/utils/processDelta.test.js
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  applyProcessDelta,
  buildProcessPatch,
  PROCESS_DELTA_FIELDS,
} from "./processDelta.js";

const PID = "proc-1";

describe("PROCESS_DELTA_FIELDS", () => {
  it("cobre os campos de atribuição que o cartão lê", () => {
    // Regressão do bug do cartão em branco: se o backend deixar de enviar
    // (ou renomear) um destes, o cartão volta a ficar vazio.
    ["assigned_consultor_ids", "consultor_names",
     "assigned_mediador_ids", "mediador_names"].forEach((campo) => {
      assert.ok(
        PROCESS_DELTA_FIELDS.includes(campo),
        `${campo} tem de estar no contrato do delta`
      );
    });
  });
});

describe("buildProcessPatch", () => {
  it("extrai a atribuição vinda do delta", () => {
    const patch = buildProcessPatch(
      {
        process_id: PID,
        consultor_names: ["Carla"],
        assigned_consultor_ids: ["u1"],
        mediador_names: ["Mário"],
        assigned_mediador_ids: ["u2"],
      },
      PID
    );
    assert.deepEqual(patch.consultor_names, ["Carla"]);
    assert.deepEqual(patch.assigned_consultor_ids, ["u1"]);
    assert.deepEqual(patch.mediador_names, ["Mário"]);
    assert.deepEqual(patch.assigned_mediador_ids, ["u2"]);
  });

  it("ignora deltas de OUTRO processo", () => {
    const patch = buildProcessPatch(
      { process_id: "outro", consultor_names: ["Carla"] },
      PID
    );
    assert.deepEqual(patch, {});
  });

  it("ignora campos fora do contrato", () => {
    const patch = buildProcessPatch(
      { process_id: PID, financial_data: { rendimento: 9999 }, status: "analise" },
      PID
    );
    assert.deepEqual(patch, { status: "analise" });
    assert.ok(!("financial_data" in patch), "delta não pode sobrepor o formulário");
  });

  it("omite campos ausentes ou nulos", () => {
    const patch = buildProcessPatch(
      { process_id: PID, consultor_names: null, status: "analise" },
      PID
    );
    assert.deepEqual(patch, { status: "analise" });
  });

  it("tolera entradas inválidas", () => {
    assert.deepEqual(buildProcessPatch(null, PID), {});
    assert.deepEqual(buildProcessPatch(undefined, PID), {});
    assert.deepEqual(buildProcessPatch("string", PID), {});
    assert.deepEqual(buildProcessPatch({ process_id: PID }, null), {});
  });
});

describe("applyProcessDelta", () => {
  const processo = { id: PID, client_name: "Ana", status: "pre_registo" };

  it("funde a atribuição preservando o resto", () => {
    const next = applyProcessDelta(
      processo,
      { process_id: PID, consultor_names: ["Carla"], status: "analise" },
      PID
    );
    assert.deepEqual(next.consultor_names, ["Carla"]);
    assert.equal(next.status, "analise");
    assert.equal(next.client_name, "Ana", "campos não tocados preservam-se");
  });

  it("não muta o objecto original", () => {
    const antes = { ...processo };
    applyProcessDelta(processo, { process_id: PID, status: "analise" }, PID);
    assert.deepEqual(processo, antes);
  });

  it("devolve a MESMA referência quando não há nada a aplicar", () => {
    const next = applyProcessDelta(
      processo,
      { process_id: "outro", status: "analise" },
      PID
    );
    assert.equal(next, processo, "evita re-render desnecessário");
  });

  it("tolera processo ainda não carregado", () => {
    assert.equal(applyProcessDelta(null, { process_id: PID }, PID), null);
  });
});
