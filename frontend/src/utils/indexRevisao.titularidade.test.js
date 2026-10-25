/**
 * Sem acções cruzadas entre indexadores (Out 2026): a regra pura que esconde/desliga as acções.
 */
import { describe, expect, it } from "vitest";

import { processoDeOutroIndexador } from "./indexRevisao";

describe("processoDeOutroIndexador", () => {
  const de = (dono) => ({ id: "p1", assigned_indexacao_id: dono });

  it("o Index não age no processo de um colega", () => {
    expect(processoDeOutroIndexador(de("u-rui"), "indexacao", "u-ines")).toBe(true);
    expect(processoDeOutroIndexador(de("u-rui"), "INDEXACAO", "u-ines")).toBe(true);
  });

  it("age no que é seu e no que não é de ninguém", () => {
    expect(processoDeOutroIndexador(de("u-ines"), "indexacao", "u-ines")).toBe(false);
    expect(processoDeOutroIndexador(de(null), "indexacao", "u-ines")).toBe(false);
    expect(processoDeOutroIndexador(de(""), "indexacao", "u-ines")).toBe(false);
    expect(processoDeOutroIndexador({}, "indexacao", "u-ines")).toBe(false);
  });

  it.each(["diretor", "ceo", "admin", "master", "", undefined])("%s não é tocado", (papel) => {
    expect(processoDeOutroIndexador(de("u-rui"), papel, "u-ines")).toBe(false);
  });
});
