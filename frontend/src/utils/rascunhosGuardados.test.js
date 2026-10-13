import { beforeEach, describe, expect, it } from "vitest";

import {
  CHAVE_LEGADA,
  carregarRascunhos,
  chaveDosRascunhos,
  guardarRascunhos,
} from "./rascunhosGuardados";

beforeEach(() => localStorage.clear());

describe("rascunhosGuardados — âmbito por utilizador e empresa (Lote 4)", () => {
  it("a chave distingue utilizador E empresa", () => {
    const a = chaveDosRascunhos("u1", "cmp-power");
    expect(chaveDosRascunhos("u1", "cmp-domus")).not.toBe(a);
    expect(chaveDosRascunhos("u2", "cmp-power")).not.toBe(a);
    expect(a).not.toBe(CHAVE_LEGADA);
  });

  it("trocar de empresa NÃO mostra os rascunhos da outra", () => {
    const power = chaveDosRascunhos("u1", "cmp-power");
    const domus = chaveDosRascunhos("u1", "cmp-domus");
    guardarRascunhos(power, [{ id: 1, title: "da Power" }]);

    expect(carregarRascunhos(domus)).toEqual([]);
    expect(carregarRascunhos(power)).toEqual([{ id: 1, title: "da Power" }]);
  });

  it("os rascunhos antigos (chave sem âmbito) passam UMA vez para quem abrir primeiro", () => {
    localStorage.setItem(CHAVE_LEGADA, JSON.stringify([{ id: 9, title: "antigo" }]));
    const primeiro = chaveDosRascunhos("u1", "cmp-power");
    const segundo = chaveDosRascunhos("u2", "cmp-domus");

    expect(carregarRascunhos(primeiro)).toEqual([{ id: 9, title: "antigo" }]);
    expect(localStorage.getItem(CHAVE_LEGADA)).toBeNull();
    // O segundo já não os herda: não se espalham por todos os que abrirem a página.
    expect(carregarRascunhos(segundo)).toEqual([]);
  });

  it("dados corrompidos não rebentam: lista vazia", () => {
    const chave = chaveDosRascunhos("u1", "c");
    localStorage.setItem(chave, "{não é json");
    expect(carregarRascunhos(chave)).toEqual([]);
  });

  it("sem utilizador/empresa ainda há uma chave estável (e diferente da legada)", () => {
    expect(chaveDosRascunhos(null, undefined)).toBe(chaveDosRascunhos(undefined, null));
    expect(chaveDosRascunhos(null, null)).not.toBe(CHAVE_LEGADA);
  });
});
