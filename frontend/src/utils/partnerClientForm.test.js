import { describe, expect, it } from "vitest";

import { camposAlterados, passoDoSegundoTitular, passosDoTitular, segundoTitularLigado } from "./partnerClientForm";

const PASSOS = [
  { step: 1, label: "Dados do titular", fields: [{ field_key: "name" }, { field_key: "profissao" }, { field_key: "compra_tipo" }] },
  { step: 2, label: "2.º titular", fields: [{ field_key: "titular2_name" }, { field_key: "titular2_nif" }] },
];

describe("segundoTitularLigado", () => {
  it("só o valor outra_pessoa liga", () => {
    expect(segundoTitularLigado({ compra_tipo: "outra_pessoa" })).toBe(true);
    for (const v of ["individual", "", undefined, null, "OUTRA_PESSOA", true]) {
      expect(segundoTitularLigado({ compra_tipo: v })).toBe(false);
    }
    expect(segundoTitularLigado(undefined)).toBe(false);
  });
});

describe("os passos", () => {
  it("o titular não inclui o 2.º titular nem o campo que o liga (é o interruptor)", () => {
    const passos = passosDoTitular(PASSOS);
    expect(passos).toHaveLength(1);
    expect(passos[0].fields.map((f) => f.field_key)).toEqual(["name", "profissao"]);
  });

  it("o 2.º titular é o passo 2", () => {
    expect(passoDoSegundoTitular(PASSOS).fields).toHaveLength(2);
    expect(passoDoSegundoTitular([PASSOS[0]])).toBeNull();
  });

  it.each([undefined, null, "x", {}])("um esquema inválido (%s) não rebenta", (invalido) => {
    expect(passosDoTitular(invalido)).toEqual([]);
    expect(passoDoSegundoTitular(invalido)).toBeNull();
  });
});

describe("camposAlterados", () => {
  const inicial = { name: "Joana", profissao: "Eng.", compra_tipo: "individual" };

  it("só o que mudou", () => {
    expect(camposAlterados(inicial, { ...inicial, profissao: "Médica" }, PASSOS, { ligado: false })).toEqual({ profissao: "Médica" });
  });

  it("nada alterado = nada a enviar", () => {
    expect(camposAlterados(inicial, { ...inicial }, PASSOS, { ligado: false })).toEqual({});
  });

  it("um campo apagado vai como vazio (o servidor apaga-o)", () => {
    expect(camposAlterados(inicial, { ...inicial, profissao: "" }, PASSOS, { ligado: false })).toEqual({ profissao: "" });
    expect(camposAlterados(inicial, { name: "Joana", compra_tipo: "individual" }, PASSOS, { ligado: false })).toEqual({ profissao: "" });
  });

  it("os campos do 2.º titular só vão com o interruptor ligado", () => {
    const actuais = { ...inicial, titular2_name: "Rui" };
    expect(camposAlterados(inicial, actuais, PASSOS, { ligado: false })).toEqual({});
    expect(camposAlterados(inicial, { ...actuais, compra_tipo: "outra_pessoa" }, PASSOS, { ligado: true })).toEqual({
      compra_tipo: "outra_pessoa",
      titular2_name: "Rui",
    });
  });

  it("desligar vai só como a chave que liga/desliga", () => {
    const ligada = { ...inicial, compra_tipo: "outra_pessoa", titular2_name: "Rui" };
    expect(camposAlterados(ligada, { ...ligada, compra_tipo: "individual" }, PASSOS, { ligado: false })).toEqual({ compra_tipo: "individual" });
  });

  it("chaves fora do esquema nunca vão", () => {
    expect(camposAlterados(inicial, { ...inicial, lead_status: "x", network_id: "y" }, PASSOS, { ligado: false })).toEqual({});
  });
});

describe("o formulário é inteligente: dados do 2.º titular ligam-no (QA, Out 2026)", () => {
  it("com o esquema, qualquer campo do 2.º titular preenchido conta como ligado", () => {
    expect(segundoTitularLigado({ compra_tipo: "individual", titular2_name: "Rui" }, PASSOS)).toBe(true);
    expect(segundoTitularLigado({ titular2_nif: "232119867" }, PASSOS)).toBe(true);
  });

  it("sem dados nem valor no campo, não está ligado (e espaços não contam)", () => {
    expect(segundoTitularLigado({ compra_tipo: "individual", titular2_name: "   " }, PASSOS)).toBe(false);
    expect(segundoTitularLigado({ titular2_name: "" }, PASSOS)).toBe(false);
  });

  it("sem o esquema vale só o campo, como sempre", () => {
    expect(segundoTitularLigado({ titular2_name: "Rui" })).toBe(false);
  });

  it("ligado por dados envia compra_tipo = outra_pessoa, mesmo que o campo diga outra coisa", () => {
    const actuais = { ...{ name: "Joana", profissao: "Eng.", compra_tipo: "individual" }, titular2_name: "Rui" };
    const inicial = { name: "Joana", profissao: "Eng.", compra_tipo: "individual" };
    expect(camposAlterados(inicial, actuais, PASSOS, { ligado: true })).toEqual({
      compra_tipo: "outra_pessoa",
      titular2_name: "Rui",
    });
  });

  it("desligado nunca acrescenta compra_tipo", () => {
    const inicial = { name: "Joana", compra_tipo: "individual" };
    expect(camposAlterados(inicial, { ...inicial, titular2_name: "Rui" }, PASSOS, { ligado: false })).toEqual({});
  });
});
