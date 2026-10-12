import { describe, expect, it } from "vitest";
import {
  cleanFinancialDataForSubmit,
  cleanPersonalDataForSubmit,
  cleanTitular2DataForSubmit,
} from "./processFormCleaners";

const BASE_PESSOAL = {
  nif: "123456789", morada_fiscal: "Rua A", address: "Rua A", naturalidade: "Porto",
  data_nascimento: "1990-01-01", birth_date: "1990-01-01", estado_civil: "solteiro",
  nome_completo: "Ana", email: "a@b.pt", telefone: "912",
};

describe("cleanPersonalDataForSubmit — apagar um campo", () => {
  it("o campo que tinha valor e foi apagado vai como vazio explícito", () => {
    const out = cleanPersonalDataForSubmit({ ...BASE_PESSOAL, nif: "" }, { base: BASE_PESSOAL });
    expect(out.nif).toBe("");
    expect(out.naturalidade).toBe("Porto");
  });

  it("um campo apagado ao ponto de desaparecer do estado também conta", () => {
    const { naturalidade: _, ...semNaturalidade } = BASE_PESSOAL;
    expect(cleanPersonalDataForSubmit(semNaturalidade, { base: BASE_PESSOAL }).naturalidade).toBe("");
  });

  it("apagar a morada leva o nome alternativo que o servidor tinha", () => {
    const out = cleanPersonalDataForSubmit({ ...BASE_PESSOAL, morada_fiscal: "" }, { base: BASE_PESSOAL });
    expect(out.morada_fiscal).toBe("");
    expect(out.address).toBe("");
  });

  it("apagar a data de nascimento leva o birth_date", () => {
    const out = cleanPersonalDataForSubmit({ ...BASE_PESSOAL, data_nascimento: "" }, { base: BASE_PESSOAL });
    expect(out.data_nascimento).toBe("");
    expect(out.birth_date).toBe("");
  });

  it("o que já nasceu vazio continua omitido", () => {
    const base = { ...BASE_PESSOAL, codigo_postal: "" };
    const out = cleanPersonalDataForSubmit({ ...base }, { base });
    expect(out).not.toHaveProperty("codigo_postal");
  });

  it("sem base descartam-se os vazios, como sempre", () => {
    const out = cleanPersonalDataForSubmit({ ...BASE_PESSOAL, nif: "" });
    expect(out).not.toHaveProperty("nif");
  });

  it("o nome e os contactos nunca vão como vazio por aqui", () => {
    const out = cleanPersonalDataForSubmit(
      { ...BASE_PESSOAL, nome_completo: "", email: "", telefone: "" }, { base: BASE_PESSOAL },
    );
    for (const campo of ["nome_completo", "email", "telefone"]) {
      expect(out).not.toHaveProperty(campo);
    }
  });

  it("um NIF a meio de escrever é descartado, não apagado", () => {
    const out = cleanPersonalDataForSubmit({ ...BASE_PESSOAL, nif: "123" }, { base: BASE_PESSOAL });
    expect(out).not.toHaveProperty("nif");
  });

  it("uma data ilegível é omitida (antes ia null e sobrepunha o valor guardado)", () => {
    const out = cleanPersonalDataForSubmit({ ...BASE_PESSOAL, data_nascimento: "ontem" }, { base: BASE_PESSOAL });
    expect(out).not.toHaveProperty("data_nascimento");
  });

  it("converte a data portuguesa legível", () => {
    expect(cleanPersonalDataForSubmit({ data_nascimento: "03/02/1991" }).data_nascimento).toBe("1991-02-03");
  });

  it("false e 0 são valores: não se apagam", () => {
    const base = { menor_35_anos: true, altura: 0 };
    const out = cleanPersonalDataForSubmit({ menor_35_anos: false, altura: 0 }, { base });
    expect(out.menor_35_anos).toBe(false);
    expect(out.altura).toBe("0"); // texto, como sempre: o campo é uma string no modelo
  });
});

describe("cleanFinancialDataForSubmit — apagar um campo", () => {
  const BASE = { monthly_income: 2000, salario_liquido: 1800, nr_dependentes: 2, capital_proprio: 10 };

  it("o campo apagado vai como null e leva os alternativos que o servidor tinha", () => {
    const out = cleanFinancialDataForSubmit({ ...BASE, monthly_income: null }, { base: BASE });
    expect(out.monthly_income).toBeNull();
    expect(out.salario_liquido).toBeNull();
    expect(out.capital_proprio).toBe(10);
  });

  it("um campo desaparecido do estado também é apagado", () => {
    const { capital_proprio: _, ...resto } = BASE;
    expect(cleanFinancialDataForSubmit(resto, { base: BASE }).capital_proprio).toBeNull();
  });

  it("0 não é apagar: os alternativos ficam", () => {
    const out = cleanFinancialDataForSubmit({ ...BASE, monthly_income: 0 }, { base: BASE });
    expect(out.monthly_income).toBe(0);
    expect(out.salario_liquido).toBe(1800);
  });

  it("só considera campos do modelo financeiro", () => {
    const out = cleanFinancialDataForSubmit({}, { base: { campo_inventado: "x" } });
    expect(out).not.toHaveProperty("campo_inventado");
  });

  it("sem base mantém o comportamento: vazio vira null, ausente fica omitido", () => {
    const out = cleanFinancialDataForSubmit({ monthly_income: "" });
    expect(out).toEqual({ monthly_income: null });
  });
});

describe("cleanTitular2DataForSubmit — substituição da secção", () => {
  it("um campo apagado simplesmente não vai (o servidor substitui a secção)", () => {
    const out = cleanTitular2DataForSubmit({ name: "Rui", naturalidade: "", nif: "987654321" });
    expect(out).toEqual({ name: "Rui", nif: "987654321" });
  });

  it("nunca envia o índice cego", () => {
    expect(cleanTitular2DataForSubmit({ nif_hash: "h" })).toEqual({});
  });

  it("uma data ilegível é omitida", () => {
    expect(cleanTitular2DataForSubmit({ birth_date: "ontem" })).toEqual({});
  });
});
