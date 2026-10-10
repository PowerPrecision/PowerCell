import { describe, expect, it } from "vitest";

import {
  candidatosValidos,
  montarPedido,
  podeGerirOrigemFinanceira,
  resumoDaOrigem,
} from "./origemFinanceira";

describe("podeGerirOrigemFinanceira", () => {
  it.each(["admin", "ceo", "diretor", "CEO", " Diretor "])("%s gere", (papel) => {
    expect(podeGerirOrigemFinanceira(papel)).toBe(true);
  });

  it.each(["consultor", "intermediario", "administrativo", "indexacao", "parceiro", "", null, undefined])(
    "%s não gere",
    (papel) => {
      expect(podeGerirOrigemFinanceira(papel)).toBe(false);
    },
  );
});

describe("montarPedido", () => {
  it("orgânica não leva angariador, mesmo que ficasse um escolhido", () => {
    expect(montarPedido("organica", "u-dora")).toEqual({ ok: true, corpo: { tipo: "organica" } });
  });

  it("angariação leva o id aparado", () => {
    expect(montarPedido("angariacao", " u-dora ")).toEqual({
      ok: true,
      corpo: { tipo: "angariacao", angariador_id: "u-dora" },
    });
  });

  it.each(["", "  ", null, undefined])("angariação sem angariador (%s) diz o que falta", (id) => {
    const r = montarPedido("angariacao", id);
    expect(r.ok).toBe(false);
    expect(r.erro).toMatch(/utilizador que angariou/i);
  });

  it.each(["", "outra", null])("sem origem escolhida (%s) diz o que falta", (tipo) => {
    expect(montarPedido(tipo, "x").ok).toBe(false);
  });
});

describe("candidatosValidos", () => {
  it("devolve a lista normalizada", () => {
    expect(candidatosValidos({ candidatos: [{ id: "a", nome: "Ana", papel: "diretor" }] })).toEqual([
      { id: "a", nome: "Ana", papel: "diretor" },
    ]);
  });

  it.each([undefined, null, {}, { candidatos: {} }, { candidatos: "x" }, { candidatos: null }])(
    "forma inesperada %j dá lista vazia (Array.isArray, nunca || [])",
    (resposta) => {
      expect(candidatosValidos(resposta)).toEqual([]);
    },
  );

  it("descarta entradas sem id e usa o id quando falta o nome", () => {
    expect(candidatosValidos({ candidatos: [null, {}, { id: "" }, { id: "z" }] })).toEqual([
      { id: "z", nome: "z", papel: null },
    ]);
  });
});

describe("resumoDaOrigem", () => {
  it("sem origem definida", () => {
    expect(resumoDaOrigem(null)).toBe("Ainda não definida");
    expect(resumoDaOrigem({ definida: false })).toBe("Ainda não definida");
  });

  it("orgânica", () => {
    expect(resumoDaOrigem({ definida: true, tipo: "organica" })).toBe("Veio diretamente à empresa");
  });

  it("angariação diz quem", () => {
    expect(
      resumoDaOrigem({ definida: true, tipo: "angariacao", angariador: { id: "u", nome: "Dora" } }),
    ).toBe("Angariado por Dora");
  });

  it("angariação sem nome cai no rótulo, nunca em «Angariado por undefined»", () => {
    expect(resumoDaOrigem({ definida: true, tipo: "angariacao", angariador: null })).toBe(
      "Foi angariado por um utilizador específico",
    );
  });
});
