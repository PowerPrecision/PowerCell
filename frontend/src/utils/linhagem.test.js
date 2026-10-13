import { describe, expect, it } from "vitest";

import {
  caminhosDaLinhagem,
  deveMostrarLinhagem,
  eOFimDoCaminho,
  empresasActuais,
  textoDoCaminho,
} from "./linhagem";

const PARCEIRO = { tipo: "parceiro", nome: "João Angariador", nivel: 0 };
const Y = { tipo: "empresa", papel: "dona", nome: "Empresa Y", nivel: 1 };
const Z = { tipo: "empresa", papel: "convidada", nome: "Empresa Z", nivel: 2, partilhado_por: "Empresa Y" };

const LINHAGEM = {
  origem: PARCEIRO,
  dona: { nome: "Empresa Y" },
  caminhos: [[PARCEIRO, Y, Z]],
  empresa_actual: ["Empresa Z"],
  tem_cadeia: true,
};

describe("caminhosDaLinhagem", () => {
  it("devolve o caminho tal como o servidor o calculou", () => {
    expect(caminhosDaLinhagem(LINHAGEM)).toEqual([[PARCEIRO, Y, Z]]);
  });

  it("descarta nós sem nome (um crachá vazio é pior do que nenhum)", () => {
    const l = { caminhos: [[PARCEIRO, { tipo: "empresa", nome: "  " }, Z]] };
    expect(caminhosDaLinhagem(l)).toEqual([[PARCEIRO, Z]]);
  });

  it("descarta caminhos vazios", () => {
    expect(caminhosDaLinhagem({ caminhos: [[], [{ nome: "" }]] })).toEqual([]);
  });

  it.each([undefined, null, {}, { caminhos: null }, { caminhos: {} }, { caminhos: "x" }, { caminhos: [null, 3, "a"] }])(
    "forma inesperada (%j) → sem caminhos (Array.isArray, nunca `|| []`)",
    (l) => {
      expect(caminhosDaLinhagem(l)).toEqual([]);
    },
  );
});

describe("deveMostrarLinhagem", () => {
  it("mostra com cadeia", () => {
    expect(deveMostrarLinhagem(LINHAGEM)).toBe(true);
  });

  it("mostra só com o parceiro angariador (Parceiro → Y)", () => {
    expect(deveMostrarLinhagem({ origem: PARCEIRO, caminhos: [[PARCEIRO, Y]], tem_cadeia: false })).toBe(true);
  });

  it("um processo da casa, sem parceiro nem partilhas, não repete a etiqueta da empresa", () => {
    expect(deveMostrarLinhagem({ origem: null, caminhos: [[Y]], tem_cadeia: false })).toBe(false);
  });

  it("só o `true` estrito de tem_cadeia conta", () => {
    expect(deveMostrarLinhagem({ caminhos: [[Y, Z]], tem_cadeia: "true" })).toBe(false);
    expect(deveMostrarLinhagem({ caminhos: [[Y, Z]], tem_cadeia: 1 })).toBe(false);
  });

  it("sem caminhos legíveis não há nada para desenhar", () => {
    expect(deveMostrarLinhagem({ tem_cadeia: true, caminhos: [] })).toBe(false);
  });

  it.each([undefined, null, "x", 3, []])("%j não rebenta", (l) => {
    expect(deveMostrarLinhagem(l)).toBe(false);
  });
});

describe("textos", () => {
  it("o texto do caminho liga os nomes com setas", () => {
    expect(textoDoCaminho([PARCEIRO, Y, Z])).toBe("João Angariador → Empresa Y → Empresa Z");
  });

  it("empresasActuais lê as folhas e ignora lixo", () => {
    expect(empresasActuais(LINHAGEM)).toEqual(["Empresa Z"]);
    expect(empresasActuais({ empresa_actual: ["A", "", 3, null, " "] })).toEqual(["A"]);
    expect(empresasActuais({ empresa_actual: "A" })).toEqual([]);
    expect(empresasActuais(undefined)).toEqual([]);
  });

  it("o fim do caminho é o último nó", () => {
    const caminho = [PARCEIRO, Y, Z];
    expect(eOFimDoCaminho(caminho, 2)).toBe(true);
    expect(eOFimDoCaminho(caminho, 1)).toBe(false);
    expect(eOFimDoCaminho(null, 0)).toBe(false);
  });
});
