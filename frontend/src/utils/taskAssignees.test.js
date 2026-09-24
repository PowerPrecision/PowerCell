/**
 * Selecção de responsáveis de uma tarefa — ponto 10 (Lote 5, Secção B).
 *
 * O agrupamento "equipa do processo primeiro, o resto atrás de um
 * separador" já existia dentro do `TasksPanel`, mas só para a CRIAÇÃO
 * de tarefas. A reatribuição precisa exactamente do mesmo — e
 * duplicá-lo daria dois sítios a divergir.
 *
 * A REGRA QUE VEM DO LOTE 4 (ponto 13): quando a equipa do processo não
 * se confirma, isso é DITO. Antes caía-se para todo o staff com um
 * `console.warn` — o utilizador via uma lista enorme e não sabia porquê.
 */
import { describe, expect, it } from "vitest";

import { agruparResponsaveis } from "./taskAssignees";

const UTILIZADORES = [
  { id: "u1", name: "Ana", role: "consultor" },
  { id: "u2", name: "Bruno", role: "intermediario" },
  { id: "u3", name: "Carla", role: "admin" },
];

describe("agruparResponsaveis — dentro de um processo", () => {
  it("separa a equipa do processo do resto", () => {
    const r = agruparResponsaveis({
      users: UTILIZADORES,
      equipaDoProcesso: ["u1", "u2"],
      dentroDeProcesso: true,
    });
    expect(r.daEquipa.map((u) => u.id)).toEqual(["u1", "u2"]);
    expect(r.foraDaEquipa.map((u) => u.id)).toEqual(["u3"]);
    expect(r.temGrupos).toBe(true);
  });

  it("compara ids como texto", () => {
    // Um id numérico vindo do backend contra uma string no estado é a
    // causa nº1 de listas vazias neste projecto.
    const r = agruparResponsaveis({
      users: [{ id: 1, name: "Ana" }],
      equipaDoProcesso: ["1"],
      dentroDeProcesso: true,
    });
    expect(r.daEquipa).toHaveLength(1);
  });

  it("sem ninguém fora da equipa não há grupos a mostrar", () => {
    const r = agruparResponsaveis({
      users: [UTILIZADORES[0]],
      equipaDoProcesso: ["u1"],
      dentroDeProcesso: true,
    });
    expect(r.temGrupos).toBe(false);
  });

  it("equipa por confirmar mostra todos E di-lo", () => {
    // Lote 4, ponto 13: cair para todo o staff em silêncio deixava o
    // utilizador com uma lista enorme sem saber porquê.
    const r = agruparResponsaveis({
      users: UTILIZADORES,
      equipaDoProcesso: [],
      dentroDeProcesso: true,
    });
    expect(r.daEquipa).toHaveLength(3);
    expect(r.equipaPorConfirmar).toBe(true);
  });
});

describe("agruparResponsaveis — fora de um processo", () => {
  it("mostra todos sem separar", () => {
    const r = agruparResponsaveis({
      users: UTILIZADORES,
      equipaDoProcesso: [],
      dentroDeProcesso: false,
    });
    expect(r.daEquipa).toHaveLength(3);
    expect(r.foraDaEquipa).toEqual([]);
    expect(r.temGrupos).toBe(false);
  });

  it("não reclama de uma equipa que não se aplica", () => {
    // Contraprova: sem processo não há equipa para confirmar, e um aviso
    // aqui seria ruído permanente na lista geral de tarefas.
    const r = agruparResponsaveis({
      users: UTILIZADORES,
      equipaDoProcesso: [],
      dentroDeProcesso: false,
    });
    expect(r.equipaPorConfirmar).toBe(false);
  });
});

describe("agruparResponsaveis — robustez", () => {
  it("sem argumentos devolve listas vazias", () => {
    const r = agruparResponsaveis();
    expect(r.daEquipa).toEqual([]);
    expect(r.foraDaEquipa).toEqual([]);
    expect(r.temGrupos).toBe(false);
  });

  it("entradas inválidas na lista de utilizadores são descartadas", () => {
    const r = agruparResponsaveis({
      users: [null, { name: "sem id" }, UTILIZADORES[0]],
      equipaDoProcesso: [],
      dentroDeProcesso: false,
    });
    expect(r.daEquipa.map((u) => u.id)).toEqual(["u1"]);
  });
});
