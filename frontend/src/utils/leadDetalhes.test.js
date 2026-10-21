import { describe, expect, it } from "vitest";

import { ficheirosDaLead, linhasDaSeccao, podeAbrirDetalhes, rotuloDoCampo, seccoesDaLead } from "./leadDetalhes";

describe("seccoesDaLead", () => {
  it("só desenha as secções com linhas, pela ordem de leitura da equipa", () => {
    const s = seccoesDaLead({
      dados_pessoais: { nif: "1" },
      titular2_data: {},
      dados_financeiros: { rendimento_mensal: 0 },
      dados_imobiliarios: null,
    });
    expect(s.map((x) => x.chave)).toEqual(["dados_pessoais", "dados_financeiros"]);
  });

  it("zero é um valor (não uma linha em branco)", () => {
    expect(linhasDaSeccao({ rendimento_mensal: 0 })[0].valor).toBe("0");
  });

  it("nos dados pessoais não repete nome, email nem telefone (já estão nos contactos)", () => {
    const campos = linhasDaSeccao({ nome: "A", email: "a@x.pt", telefone: "9", nif: "2" }, { semRepetidos: true });
    expect(campos.map((l) => l.campo)).toEqual(["nif"]);
  });

  it.each([undefined, null, "texto", [], 5])("uma secção que não é um objecto não rebenta (%j)", (v) => {
    expect(linhasDaSeccao(v)).toEqual([]);
    expect(seccoesDaLead({ dados_pessoais: v })).toEqual([]);
  });

  it("um campo desconhecido tem rótulo legível, nunca a chave crua", () => {
    expect(rotuloDoCampo("anos_de_casa")).toBe("Anos de casa");
    expect(rotuloDoCampo("profissao")).toBe("Profissão");
  });
});

describe("ficheirosDaLead", () => {
  it("o comprovativo vai primeiro e a ordem do resto mantém-se", () => {
    const f = ficheirosDaLead({ ficheiros: [{ filename: "a" }, { filename: "p", comprovativo: true }, { filename: "b" }] });
    expect(f.map((x) => x.filename)).toEqual(["p", "a", "b"]);
  });

  it.each([undefined, null, {}, { ficheiros: "x" }])("sem lista = vazio (%j)", (d) => {
    expect(ficheirosDaLead(d)).toEqual([]);
  });
});

describe("podeAbrirDetalhes", () => {
  it("exige um id em texto", () => {
    expect(podeAbrirDetalhes({ id: "c1" })).toBe(true);
    expect(podeAbrirDetalhes({ id: "" })).toBe(false);
    expect(podeAbrirDetalhes({ id: 7 })).toBe(false);
    expect(podeAbrirDetalhes(null)).toBe(false);
  });
});
