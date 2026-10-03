import { describe, it, expect } from "vitest";

import {
  casaPesquisa,
  eOrfa,
  nomeFoiResolvido,
  nomeVisivel,
  ordenarPastas,
  temColisao,
} from "./pastaS3";

const UUID = "11111111-1111-4111-8111-111111111111";
const POR_ID = {
  path: `Documentação Clientes/${UUID}`,
  name: UUID,
  display_name: "Carolina Agostinho da Silva",
  nomes_dos_clientes: ["Carolina Agostinho da Silva"],
  orfa: false,
};
const LEGADA = {
  path: "Documentação Clientes/Joao_Silva",
  name: "Joao_Silva",
  display_name: "Joao_Silva",
  nomes_dos_clientes: ["João Silva"],
  orfa: false,
};
const COLIDIDA = {
  path: "Documentação Clientes/Carolina_Silva",
  name: "Carolina_Silva",
  display_name: "Carolina_Silva",
  nomes_dos_clientes: ["Carolina Silva", "Carolina Agostinho da Silva"],
  orfa: false,
};
const ORFA = {
  path: `Documentação Clientes/${UUID}`,
  name: UUID,
  display_name: UUID,
  nomes_dos_clientes: [],
  orfa: true,
};

describe("nomeVisivel", () => {
  it("mostra o nome do cliente em vez do uuid", () => {
    expect(nomeVisivel(POR_ID)).toBe("Carolina Agostinho da Silva");
  });

  it("uma pasta legada mantém o próprio nome", () => {
    expect(nomeVisivel(LEGADA)).toBe("Joao_Silva");
  });

  it("sem resolução fica o nome da pasta — não se inventa", () => {
    expect(nomeVisivel(ORFA)).toBe(UUID);
  });

  it("nunca devolve vazio", () => {
    expect(nomeVisivel({})).toBe("—");
    expect(nomeVisivel(null)).toBe("—");
  });

  it("um display_name em branco não apaga o nome", () => {
    expect(nomeVisivel({ name: "X_Y", display_name: "   " })).toBe("X_Y");
  });
});

describe("o path é que manda nas operações", () => {
  it("o nome visível não substitui o path nem o name", () => {
    // Guarda de contrato: este módulo NUNCA reescreve o que se usa para
    // entrar, renomear ou apagar.
    expect(POR_ID.path).toBe(`Documentação Clientes/${UUID}`);
    expect(POR_ID.name).toBe(UUID);
  });
});

describe("diagnóstico da pasta", () => {
  it("duas fichas na mesma pasta é colisão", () => {
    expect(temColisao(COLIDIDA)).toBe(true);
    expect(temColisao(POR_ID)).toBe(false);
    expect(temColisao(ORFA)).toBe(false);
  });

  it("a órfã diz-se órfã", () => {
    expect(eOrfa(ORFA)).toBe(true);
    expect(eOrfa(POR_ID)).toBe(false);
  });

  it("distingue um nome resolvido de um nome do bucket", () => {
    expect(nomeFoiResolvido(POR_ID)).toBe(true);
    expect(nomeFoiResolvido(LEGADA)).toBe(false);
    expect(nomeFoiResolvido(ORFA)).toBe(false);
  });
});

describe("pesquisa", () => {
  it("encontra pelo nome do cliente", () => {
    expect(casaPesquisa(POR_ID, "carolina")).toBe(true);
  });

  it("encontra pelo uuid colado de um log", () => {
    // Filtrar só pelo visível fazia o uuid deixar de ser pesquisável no dia
    // em que o nome passou a aparecer.
    expect(casaPesquisa(POR_ID, "11111111")).toBe(true);
  });

  it("encontra pelo segundo nome de uma pasta colidida", () => {
    expect(casaPesquisa(COLIDIDA, "Agostinho")).toBe(true);
  });

  it("termo vazio não filtra nada", () => {
    expect(casaPesquisa(ORFA, "")).toBe(true);
    expect(casaPesquisa(ORFA, "   ")).toBe(true);
  });

  it("não encontra o que não está", () => {
    expect(casaPesquisa(LEGADA, "zzz")).toBe(false);
  });
});

describe("ordenação", () => {
  it("ordena pelo nome VISÍVEL, não pelo uuid", () => {
    const nomes = ordenarPastas([POR_ID, LEGADA]).map(nomeVisivel);
    expect(nomes).toEqual(["Carolina Agostinho da Silva", "Joao_Silva"]);
  });

  it("não muta a lista recebida", () => {
    const entrada = [LEGADA, POR_ID];
    ordenarPastas(entrada);
    expect(entrada[0]).toBe(LEGADA);
  });

  it("lida com lista vazia ou ausente", () => {
    expect(ordenarPastas([])).toEqual([]);
    expect(ordenarPastas(null)).toEqual([]);
  });
});
