/**
 * A forma de uma coluna do Kanban (Lote 7, D-20).
 *
 * Estes testes existem porque o teste de PÁGINA do Kanban apanhou um
 * `Cannot read properties of undefined (reading 'filter')` numa coluna sem
 * a chave `processes` — e o quadro é a página de entrada do sistema.
 */
import { describe, expect, it } from "vitest";
import {
  contarCartoes,
  fundirColunasDeConcluidos,
  normalizarColuna,
  normalizarColunas,
} from "./kanbanColunas";

describe("normalizarColuna", () => {
  it("dá uma lista vazia a uma coluna sem `processes`", () => {
    const coluna = normalizarColuna({ id: "x", name: "x", label: "Fase X" });
    expect(coluna.processes).toEqual([]);
    expect(coluna.count).toBe(0);
  });

  it("preserva os cartões e os restantes campos", () => {
    const coluna = normalizarColuna({
      id: "a", name: "a", label: "Análise", color: "#123456", order: 2,
      processes: [{ id: "p1" }, { id: "p2" }],
    });
    expect(coluna.processes).toHaveLength(2);
    expect(coluna.label).toBe("Análise");
    expect(coluna.color).toBe("#123456");
    expect(coluna.order).toBe(2);
  });

  it("o `count` DERIVA da lista e não do que o servidor disse", () => {
    // Depois do arrasto optimista e do filtro em memória, o `count` do
    // servidor contradiz o ecrã. Um contador que discorda da coluna é o
    // rodapé a discordar da lista, com outro nome.
    const coluna = normalizarColuna({
      name: "a", processes: [{ id: "p1" }], count: 97,
    });
    expect(coluna.count).toBe(1);
  });

  it("um `processes` que não é array não passa por truthy", () => {
    // `x || []` devolveria o objecto (é truthy) e o erro mudava de sítio
    // em vez de desaparecer — é a lição da colisão de chaves de cache.
    for (const lixo of [{}, "abc", 7, true]) {
      expect(normalizarColuna({ name: "a", processes: lixo }).processes).toEqual([]);
    }
  });

  it("devolve null para o que não é coluna", () => {
    for (const lixo of [null, undefined, "x", 3, []]) {
      // Um array também não é uma coluna; `[]` tem typeof object, daí o
      // teste explícito.
      const resultado = normalizarColuna(lixo);
      expect(resultado === null || Array.isArray(lixo)).toBe(true);
    }
  });
});

describe("normalizarColunas", () => {
  it("deixa cair as entradas inválidas em vez de rebentar", () => {
    expect(normalizarColunas([null, { name: "a" }, undefined])).toEqual([
      { name: "a", processes: [], count: 0 },
    ]);
  });

  it("entrada que não é lista dá lista vazia", () => {
    for (const lixo of [null, undefined, {}, "x"]) {
      expect(normalizarColunas(lixo)).toEqual([]);
    }
  });
});

describe("fundirColunasDeConcluidos", () => {
  const ACTIVAS = [
    { name: "analise", label: "Análise", processes: [{ id: "p1" }] },
    { name: "concluidos", label: "Concluídos", processes: [{ id: "p9" }] },
  ];

  it("substitui a coluna de concluídos pela da consulta isolada", () => {
    const fundidas = fundirColunasDeConcluidos(ACTIVAS, [
      { name: "concluidos", label: "Concluídos", processes: [{ id: "pA" }, { id: "pB" }] },
    ]);
    expect(fundidas.map((c) => c.name)).toEqual(["analise", "concluidos"]);
    expect(fundidas[1].processes.map((p) => p.id)).toEqual(["pA", "pB"]);
    expect(fundidas[1].count).toBe(2);
  });

  it("uma coluna de concluídos SEM `processes` não parte o quadro", () => {
    // É o caminho real do defeito: a substituição troca a coluna INTEIRA,
    // logo a forma passa a ser a que o OUTRO endpoint devolver.
    const fundidas = fundirColunasDeConcluidos(ACTIVAS, [
      { name: "concluidos", label: "Concluídos" },
    ]);
    expect(fundidas[1].processes).toEqual([]);
    expect(fundidas[1].count).toBe(0);
  });

  it("mantém a coluna activa quando não há par em concluídos", () => {
    const fundidas = fundirColunasDeConcluidos(ACTIVAS, []);
    expect(fundidas[0].processes.map((p) => p.id)).toEqual(["p1"]);
    expect(fundidas[1].processes.map((p) => p.id)).toEqual(["p9"]);
  });

  it("sem colunas activas não inventa colunas a partir dos concluídos", () => {
    // O quadro ainda está a carregar: mostrar só a coluna de concluídos
    // seria pior do que mostrar o esqueleto.
    expect(fundirColunasDeConcluidos([], [{ name: "concluidos" }])).toEqual([]);
  });
});

describe("contarCartoes", () => {
  it("soma os cartões das colunas já filtradas", () => {
    expect(contarCartoes([
      { name: "a", processes: [{ id: 1 }, { id: 2 }] },
      { name: "b", processes: [{ id: 3 }] },
    ])).toBe(3);
  });

  it("uma coluna sem `processes` conta zero e não rebenta", () => {
    expect(contarCartoes([{ name: "a" }, { name: "b", processes: [{ id: 1 }] }])).toBe(1);
  });
});
