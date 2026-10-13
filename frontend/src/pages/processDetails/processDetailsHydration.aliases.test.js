/**
 * A hidratação promove os nomes alternativos UMA vez (apagar um campo, QA Out 2026).
 *
 * Os inputs liam `a || b || ""`: apagar o canónico fazia o alternativo voltar a
 * aparecer no próprio input. Agora o estado só tem o canónico a ler.
 */
import { describe, expect, it } from "vitest";
import { normalizeFormSlices } from "./processDetailsHydration";

describe("normalizeFormSlices — nomes alternativos promovidos UMA vez (apagar um campo)", () => {
  const normalizar = (personal = {}, financial = {}) =>
    normalizeFormSlices({ personal_data: personal, financial_data: financial }, personal, financial, {}, {});

  it("o canónico vazio recebe o alternativo (o ecrã deixa de os misturar no JSX)", () => {
    const out = normalizar(
      { address: "Rua A", nationality: "Portuguesa", marital_status: "casado" },
      { salario_bruto: 3000, other_income: 50, number_of_dependents: 0, empresa: "ACME", tipo_contrato: "efetivo" },
    );
    expect(out.personalData.morada_fiscal).toBe("Rua A");
    expect(out.personalData.nacionalidade).toBe("Portuguesa");
    expect(out.personalData.estado_civil).toBe("casado");
    expect(out.financialData.rendimento_bruto).toBe(3000);
    expect(out.financialData.capital_proprio).toBe(50);
    expect(out.financialData.employer_name).toBe("ACME");
    expect(out.financialData.employment_type).toBe("efetivo");
  });

  it("um dependente a 0 do nome alternativo é promovido (0 é um valor)", () => {
    const out = normalizar({}, { number_of_dependents: 0 });
    expect(out.financialData.nr_dependentes).toBe(0);
  });

  it("o canónico preenchido não é substituído", () => {
    const out = normalizar({ morada_fiscal: "A", address: "B" }, { monthly_income: 1, salario_liquido: 2 });
    expect(out.personalData.morada_fiscal).toBe("A");
    expect(out.financialData.monthly_income).toBe(1);
  });

  it("os alternativos continuam no estado (o limpador sabe que existem e envia-os vazios)", () => {
    const out = normalizar({}, { monthly_income: 1, salario_liquido: 2 });
    expect(out.financialData.salario_liquido).toBe(2);
  });
});
