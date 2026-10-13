/**
 * Os sanitizadores NÃO engolem um vazio explícito dentro das secções (QA, Out 2026).
 *
 * Apagar o NIF (ou a morada…) chega ao servidor como `dados_pessoais.nif: ""`.
 * O sanitizador do cliente descarta vazios de TOPO (protecção contra apagões
 * acidentais), mas as secções aninhadas têm de passar tal e qual — foi a ausência
 * deste teste que deixou o resto dos campos de fora quando se corrigiu o email.
 */
import { describe, expect, it } from "vitest";
import {
  sanitizeClientUpdatePayload,
  sanitizeProcessUpdatePayload,
} from "./processUpdatePayload";

describe("sanitizeClientUpdatePayload — secções aninhadas", () => {
  it("o NIF apagado dentro de dados_pessoais chega ao servidor", () => {
    const out = sanitizeClientUpdatePayload({ dados_pessoais: { nif: "", naturalidade: "Porto" } });
    expect(out.dados_pessoais).toEqual({ nif: "", naturalidade: "Porto" });
  });

  it("o nome vazio de topo continua a ser descartado (o nome não se apaga)", () => {
    expect(sanitizeClientUpdatePayload({ nome: "", dados_pessoais: { nif: "" } })).toEqual({
      dados_pessoais: { nif: "" },
    });
  });

  it("os contactos continuam a pedir o vazio explicitamente", () => {
    expect(sanitizeClientUpdatePayload({ contacto: { email: "" } })).toEqual({});
    expect(
      sanitizeClientUpdatePayload({ contacto: { email: "" } }, { clearContactFields: ["email"] }),
    ).toEqual({ contacto: { email: "" } });
  });
});

describe("sanitizeProcessUpdatePayload — secções aninhadas", () => {
  it("personal_data e financial_data com vazios explícitos passam", () => {
    const out = sanitizeProcessUpdatePayload({
      personal_data: { nif: "", morada_fiscal: "" },
      financial_data: { monthly_income: null, salario_liquido: null },
    });
    expect(out.personal_data).toEqual({ nif: "", morada_fiscal: "" });
    expect(out.financial_data).toEqual({ monthly_income: null, salario_liquido: null });
  });
});
