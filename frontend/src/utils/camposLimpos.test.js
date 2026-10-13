import { describe, expect, it } from "vitest";
import {
  ALIASES_FINANCEIROS,
  ALIASES_PESSOAIS,
  FORA_DA_LIMPEZA_PESSOAL,
  alteracoesDeTexto,
  camposLimpos,
  estaVazio,
  limparAliasesDosCampos,
  numeroOuNulo,
  preencherCanonicosComAliases,
  valorDoCampo,
} from "./camposLimpos";

describe("estaVazio — o 0 e o false são valores", () => {
  it.each([[undefined], [null], [""], ["   "], ["\n\t"]])("%j está vazio", (v) => {
    expect(estaVazio(v)).toBe(true);
  });
  it.each([[0], [false], ["0"], ["a"], [" a "], [[]], [{}]])("%j NÃO está vazio", (v) => {
    expect(estaVazio(v)).toBe(false);
  });
});

describe("camposLimpos — só o que tinha valor e foi apagado", () => {
  const base = { nif: "123456789", morada_fiscal: "Rua A", naturalidade: "", sexo: "M", altura: 0 };

  it("devolve os campos que tinham valor e agora estão vazios (ou desapareceram)", () => {
    const atual = { nif: "", morada_fiscal: "Rua A", sexo: undefined, altura: 0 };
    expect(camposLimpos(base, atual)).toEqual(["nif", "sexo"]);
  });

  it("um campo que já nasceu vazio não é um pedido", () => {
    expect(camposLimpos({ naturalidade: "" }, { naturalidade: "" })).toEqual([]);
    expect(camposLimpos({ naturalidade: null }, {})).toEqual([]);
  });

  it("um campo que nunca existiu na base não conta (o formulário nunca o mostrou)", () => {
    expect(camposLimpos({ nif: "1" }, { nif: "1", codigo_postal: "" })).toEqual([]);
  });

  it("0 e false na base são valores: apagá-los é uma limpeza, mantê-los não", () => {
    expect(camposLimpos(base, { ...base })).toEqual([]);
    expect(camposLimpos({ altura: 0 }, { altura: null })).toEqual(["altura"]);
  });

  it("nunca devolve índices cegos", () => {
    expect(camposLimpos({ nif_hash: "h" }, { nif_hash: "" })).toEqual([]);
  });

  it("respeita `ignorar`", () => {
    expect(camposLimpos({ nif: "1" }, { nif: "" }, { ignorar: ["nif"] })).toEqual([]);
    expect(FORA_DA_LIMPEZA_PESSOAL).toEqual(expect.arrayContaining(["nome", "nome_completo", "email", "telefone"]));
  });

  it("sem base (ou base que não é objecto) não há nada a limpar", () => {
    expect(camposLimpos(null, { nif: "" })).toEqual([]);
    expect(camposLimpos("x", { nif: "" })).toEqual([]);
    expect(camposLimpos(base, null)).toEqual(Object.keys(base).filter((k) => !estaVazio(base[k])));
  });
});

describe("preencherCanonicosComAliases", () => {
  it("promove o primeiro alternativo com valor, pela ordem da tabela", () => {
    const out = preencherCanonicosComAliases(
      { salario_liquido: 1800, rendimento_mensal: 1900 }, ALIASES_FINANCEIROS,
    );
    expect(out.monthly_income).toBe(1900);
  });

  it("o canónico preenchido não é tocado — nem o 0", () => {
    expect(preencherCanonicosComAliases({ monthly_income: 0, salario_liquido: 5 }, ALIASES_FINANCEIROS).monthly_income).toBe(0);
    expect(preencherCanonicosComAliases({ morada_fiscal: "A", address: "B" }, ALIASES_PESSOAIS).morada_fiscal).toBe("A");
  });

  it("não cria chaves sem alternativo e não altera o argumento", () => {
    const entrada = { capital_proprio: 7 };
    const out = preencherCanonicosComAliases(entrada, ALIASES_FINANCEIROS);
    expect(out).toEqual({ capital_proprio: 7 });
    expect(out).not.toBe(entrada);
    expect(preencherCanonicosComAliases(null, ALIASES_PESSOAIS)).toEqual({});
  });
});

describe("limparAliasesDosCampos", () => {
  it("só limpa os alternativos que o servidor tinha", () => {
    const payload = {};
    limparAliasesDosCampos(payload, ["morada_fiscal"], ALIASES_PESSOAIS, "", { morada: "x", address: "" });
    expect(payload).toEqual({ morada: "" });
  });

  it("usa o valor vazio pedido (null no financeiro)", () => {
    const payload = {};
    limparAliasesDosCampos(payload, ["monthly_income"], ALIASES_FINANCEIROS, null, { salario_liquido: 1 });
    expect(payload).toEqual({ salario_liquido: null });
  });

  it("campos sem alternativos não geram nada", () => {
    const payload = {};
    limparAliasesDosCampos(payload, ["naturalidade"], ALIASES_PESSOAIS, "", { naturalidade: "x" });
    expect(payload).toEqual({});
  });
});

describe("numeroOuNulo / valorDoCampo — o 0 é um valor", () => {
  it('"" → null, "0" → 0, "12.5" → 12.5', () => {
    expect(numeroOuNulo("")).toBeNull();
    expect(numeroOuNulo("   ")).toBeNull();
    expect(numeroOuNulo(undefined)).toBeNull();
    expect(numeroOuNulo("0")).toBe(0);
    expect(numeroOuNulo("12.5")).toBe(12.5);
  });
  it("inteiro trunca e continua a aceitar o 0", () => {
    expect(numeroOuNulo("7.9", { inteiro: true })).toBe(7);
    expect(numeroOuNulo("0", { inteiro: true })).toBe(0);
  });
  it("texto ilegível é null (não NaN)", () => {
    expect(numeroOuNulo("abc")).toBeNull();
  });
  it("valorDoCampo mostra o 0 e esconde só o vazio", () => {
    expect(valorDoCampo(0)).toBe(0);
    expect(valorDoCampo("")).toBe("");
    expect(valorDoCampo(null)).toBe("");
    expect(valorDoCampo(undefined)).toBe("");
    expect(valorDoCampo(5)).toBe(5);
  });
});

describe("alteracoesDeTexto — só o que mudou, e apagar é vazio explícito", () => {
  const original = { email: "a@b.pt", telefone: "912", nif: "" };

  it("apagado vai como \"\" e fica em `limpos`", () => {
    const out = alteracoesDeTexto(original, { ...original, email: "" }, ["email", "telefone"]);
    expect(out).toEqual({ definidos: { email: "" }, limpos: ["email"] });
  });

  it("espaços contam como apagado", () => {
    expect(alteracoesDeTexto(original, { ...original, telefone: "   " }, ["telefone"]).definidos)
      .toEqual({ telefone: "" });
  });

  it("valor novo vai aparado; igual ao original não vai", () => {
    expect(alteracoesDeTexto(original, { ...original, email: " c@d.pt " }, ["email"]).definidos)
      .toEqual({ email: "c@d.pt" });
    expect(alteracoesDeTexto(original, original, ["email", "telefone"])).toEqual({ definidos: {}, limpos: [] });
  });

  it("vazio → vazio não é uma alteração (nunca manda apagar o que já não existia)", () => {
    expect(alteracoesDeTexto(original, { ...original, nif: "" }, ["nif"])).toEqual({ definidos: {}, limpos: [] });
    expect(alteracoesDeTexto(original, { ...original, nif: null }, ["nif"])).toEqual({ definidos: {}, limpos: [] });
  });

  it("preencher um campo vazio é uma alteração normal", () => {
    expect(alteracoesDeTexto(original, { ...original, nif: "123" }, ["nif"]))
      .toEqual({ definidos: { nif: "123" }, limpos: [] });
  });
});
