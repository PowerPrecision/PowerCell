import { describe, expect, it } from "vitest";

import {
  CATEGORIAS,
  agruparPorDia,
  categoriaDe,
  categoriasDoDia,
  construirGrelha,
  contagemDe,
  mesDe,
  rotaDoItem,
  rotuloDoMes,
  somarMeses,
} from "./calendarioDashboard";

describe("construirGrelha", () => {
  it("outubro de 2026 começa a uma quinta e tem 5 semanas", () => {
    const g = construirGrelha("2026-10");
    expect(g).toHaveLength(5);
    expect(g.every((s) => s.length === 7)).toBe(true);
    // A primeira semana começa na segunda 28/09 e o dia 1 é a quinta (índice 3).
    expect(g[0][0]).toEqual({ dia: "2026-09-28", numero: 28, doMes: false });
    expect(g[0][3]).toEqual({ dia: "2026-10-01", numero: 1, doMes: true });
    expect(g[4][6].dia).toBe("2026-11-01");
  });

  it("um mês que começa a uma segunda e acaba a um domingo tem 4 semanas (fevereiro de 2027)", () => {
    const g = construirGrelha("2027-02");
    expect(g).toHaveLength(4);
    expect(g.flat().every((d) => d.doMes)).toBe(true);
  });

  it("um mês que ocupa 6 semanas", () => {
    expect(construirGrelha("2026-03")).toHaveLength(6); // 1 de Março é domingo
    expect(construirGrelha("2027-05")).toHaveLength(6); // 1 de Maio é sábado
  });

  it("cada dia do mês aparece uma só vez", () => {
    const dias = construirGrelha("2026-10").flat().filter((d) => d.doMes).map((d) => d.numero);
    expect(dias).toEqual(Array.from({ length: 31 }, (_, i) => i + 1));
  });

  it("a mudança de hora (março/outubro) não duplica nem salta dias", () => {
    const todos = construirGrelha("2026-10").flat().map((d) => d.dia);
    expect(new Set(todos).size).toBe(todos.length);
  });
});

describe("meses", () => {
  it.each([["2026-10", 1, "2026-11"], ["2026-12", 1, "2027-01"], ["2026-01", -1, "2025-12"], ["2026-10", 14, "2027-12"]])(
    "%s + %i = %s", (mes, n, esperado) => {
      expect(somarMeses(mes, n)).toBe(esperado);
    });
  it("mesDe usa UTC", () => {
    expect(mesDe(new Date("2026-10-31T23:30:00Z"))).toBe("2026-10");
  });
  it("rótulo em português", () => {
    expect(rotuloDoMes("2026-10")).toBe("Outubro de 2026");
  });
});

describe("agrupar e classificar", () => {
  it("agrupa por dia e ignora o que não tem dia", () => {
    const m = agruparPorDia([{ dia: "2026-10-01", id: 1 }, { dia: "2026-10-01", id: 2 }, { id: 3 }, null]);
    expect(Object.keys(m)).toEqual(["2026-10-01"]);
    expect(m["2026-10-01"]).toHaveLength(2);
  });
  it("forma inesperada dá mapa vazio", () => {
    expect(agruparPorDia(undefined)).toEqual({});
    expect(agruparPorDia({})).toEqual({});
  });
  it("categorias do dia pela ordem canónica, sem repetir", () => {
    const r = categoriasDoDia([{ categoria: "prazo" }, { categoria: "escritura" }, { categoria: "prazo" }]);
    expect(r.map((c) => c.chave)).toEqual(["escritura", "prazo"]);
  });
  it("uma categoria desconhecida cai em «prazo»", () => {
    expect(categoriaDe("xpto").chave).toBe("prazo");
  });
  it("cada categoria tem letra única e cor própria", () => {
    expect(new Set(CATEGORIAS.map((c) => c.letra)).size).toBe(CATEGORIAS.length);
    expect(new Set(CATEGORIAS.map((c) => c.cor)).size).toBe(CATEGORIAS.length);
  });
  it("contagemDe nunca devolve NaN", () => {
    expect(contagemDe({ cpcv: 2 }, "cpcv")).toBe(2);
    expect(contagemDe({}, "cpcv")).toBe(0);
    expect(contagemDe(undefined, "cpcv")).toBe(0);
  });
});

describe("rotaDoItem", () => {
  it("prefere o processo, cai no cliente, e sem destino não há rota", () => {
    expect(rotaDoItem({ categoria: "escritura", process_id: "p1", client_id: "c1" })).toBe("/processo/p1");
    expect(rotaDoItem({ categoria: "marcacao", client_id: "c1" })).toBe("/cliente/c1");
    expect(rotaDoItem({ categoria: "prazo" })).toBeNull();
  });
  it("uma ausência nunca leva a um cliente", () => {
    expect(rotaDoItem({ categoria: "ausencia", process_id: "p1" })).toBeNull();
  });
});
