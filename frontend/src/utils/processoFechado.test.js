import { describe, expect, it } from "vitest";

import { fasesParaReabrir, processoEstaFechado } from "./processoFechado";

const FASES = [
  { name: "novo", label: "Novo", order: 1, is_active: true },
  { name: "cpcv", label: "CPCV", order: 3, is_active: true },
  { name: "concluidos", label: "Concluído", order: 4, is_active: false },
  { name: "renegociacao", label: "Renegociação", order: 5, is_active: false },
  { name: "sem_flag", label: "Sem flag", order: 2 },
];

describe("processoEstaFechado", () => {
  it("uma fase inactiva do motor fecha, mesmo fora da lista legada", () => {
    expect(processoEstaFechado({ status: "renegociacao" }, FASES)).toBe(true);
  });

  it("uma fase activa do motor não fecha", () => {
    expect(processoEstaFechado({ status: "cpcv" }, FASES)).toBe(false);
  });

  it("o motor ganha à lista legada: uma fase legada marcada activa não fecha", () => {
    const fases = [{ name: "concluidos", is_active: true }];
    expect(processoEstaFechado({ status: "concluidos" }, fases)).toBe(false);
  });

  it.each(["concluido", "concluidos", "cancelado", "arquivo", "desistencias"])(
    "sem o motor, %s cai na lista legada e fecha", (estado) => {
      expect(processoEstaFechado({ status: estado }, [])).toBe(true);
    },
  );

  it("sem o motor, uma fase desconhecida não fecha", () => {
    expect(processoEstaFechado({ status: "fase_x" }, [])).toBe(false);
  });

  it("uma fase sem a flag recua para a lista legada", () => {
    expect(processoEstaFechado({ status: "sem_flag" }, FASES)).toBe(false);
  });

  it("sem processo ou sem fase não há o que fechar", () => {
    expect(processoEstaFechado(null, FASES)).toBe(false);
    expect(processoEstaFechado({}, FASES)).toBe(false);
    expect(processoEstaFechado({ status: 42 }, FASES)).toBe(false);
  });

  it("fases com a forma errada não rebentam (Array.isArray, nunca || [])", () => {
    expect(processoEstaFechado({ status: "concluidos" }, { 0: "x" })).toBe(true);
    expect(processoEstaFechado({ status: "novo" }, undefined)).toBe(false);
  });

  it("não depende do cargo: a função nem o recebe", () => {
    expect(processoEstaFechado.length).toBeLessThanOrEqual(2);
  });
});

describe("fasesParaReabrir", () => {
  it("só as activas, por ordem, com o rótulo", () => {
    expect(fasesParaReabrir(FASES)).toEqual([
      { name: "novo", label: "Novo" },
      { name: "sem_flag", label: "Sem flag" },
      { name: "cpcv", label: "CPCV" },
    ]);
  });

  it("nunca oferece uma fase terminal", () => {
    const nomes = fasesParaReabrir(FASES).map((f) => f.name);
    expect(nomes).not.toContain("concluidos");
    expect(nomes).not.toContain("renegociacao");
  });

  it("uma fase sem flag mas na lista legada não é oferecida", () => {
    expect(fasesParaReabrir([{ name: "cancelado" }, { name: "novo" }]).map((f) => f.name))
      .toEqual(["novo"]);
  });

  it("lista inválida dá lista vazia", () => {
    expect(fasesParaReabrir(null)).toEqual([]);
    expect(fasesParaReabrir({})).toEqual([]);
  });
});
