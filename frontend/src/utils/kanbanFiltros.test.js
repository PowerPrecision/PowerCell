/**
 * Os filtros do Kanban (Lote 4, ponto 1).
 *
 * O TESTE CENTRAL é `cada filtro muda os parâmetros E a chave`: é a
 * afirmação que apanha o defeito que estava cá — as etiquetas iam no
 * fetcher e não iam na chave nem nas opções que o hook reconstruía, pelo
 * que mudar o filtro não enviava nada e não invalidava nada. Escrito
 * por campo e não só para as etiquetas, porque o defeito é da FORMA e o
 * próximo filtro cai no mesmo sítio.
 */
import { describe, expect, it } from "vitest";

import {
  CAMPOS_DE_FILTRO,
  chaveDeFiltros,
  normalizarFiltros,
  parametrosDoKanban,
} from "./kanbanFiltros";

const BASE = normalizarFiltros({});

/** Um valor diferente do de omissão, por campo. */
const VARIACOES = {
  consultor: "user-123",
  mediador: "user-456",
  indexacao: "user-789",
  parceiro: "user-abc",
  completedDays: 0,
  labels: ["urgente", "sub35"],
  labelsLogic: "AND",
  sub35: true,
};

describe("normalizarFiltros", () => {
  it("tem um valor para cada filtro conhecido", () => {
    for (const campo of CAMPOS_DE_FILTRO) {
      expect(BASE[campo]).toBeDefined();
    }
  });

  it("não transforma «sem limite» (0 dias) em 30", () => {
    // `completedDays || 30` fazia isto, e a diferença entre "todos os
    // concluídos" e "os dos últimos 30 dias" não dá erro nenhum.
    expect(normalizarFiltros({ completedDays: 0 }).completedDays).toBe(0);
    expect(normalizarFiltros({}).completedDays).toBe(30);
  });

  it("apara e descarta etiquetas vazias", () => {
    expect(normalizarFiltros({ labels: [" a ", "", null, "b"] }).labels).toEqual(["a", "b"]);
  });

  it("só aceita AND como lógica alternativa", () => {
    expect(normalizarFiltros({ labelsLogic: "AND" }).labelsLogic).toBe("AND");
    expect(normalizarFiltros({ labelsLogic: "xpto" }).labelsLogic).toBe("OR");
  });

  it("o sub35 é booleano estrito", () => {
    expect(normalizarFiltros({ sub35: true }).sub35).toBe(true);
    expect(normalizarFiltros({ sub35: "true" }).sub35).toBe(false);
    expect(normalizarFiltros({}).sub35).toBe(false);
  });
});

describe("parametrosDoKanban", () => {
  it("não envia filtros desligados", () => {
    const p = parametrosDoKanban(BASE);
    expect(p.get("consultor_id")).toBeNull();
    expect(p.getAll("labels")).toEqual([]);
    expect(p.get("sub35")).toBeNull();
    // O que vai sempre:
    expect(p.get("view_mode")).toBe("all");
    expect(p.get("show_all")).toBe("true");
  });

  it("envia as etiquetas uma a uma (o backend lê List[str])", () => {
    const p = parametrosDoKanban(normalizarFiltros({ labels: ["a", "b"] }));
    expect(p.getAll("labels")).toEqual(["a", "b"]);
  });

  it("só envia labels_logic=AND com mais de uma etiqueta", () => {
    const uma = parametrosDoKanban(normalizarFiltros({ labels: ["a"], labelsLogic: "AND" }));
    expect(uma.get("labels_logic")).toBeNull();
    const duas = parametrosDoKanban(normalizarFiltros({ labels: ["a", "b"], labelsLogic: "AND" }));
    expect(duas.get("labels_logic")).toBe("AND");
  });

  it("envia sub35 só quando está ligado", () => {
    expect(parametrosDoKanban(normalizarFiltros({ sub35: true })).get("sub35")).toBe("true");
    expect(parametrosDoKanban(normalizarFiltros({ sub35: false })).get("sub35")).toBeNull();
  });

  it("«none» é um filtro válido (sem ninguém atribuído)", () => {
    const p = parametrosDoKanban(normalizarFiltros({ consultorFilter: "none" }));
    expect(p.get("consultor_id")).toBe("none");
  });

  it("aguenta um objecto vazio", () => {
    expect(parametrosDoKanban().get("view_mode")).toBe("all");
    expect(parametrosDoKanban(null).get("show_all")).toBe("true");
  });
});

describe("a chave de cache e os parâmetros não podem divergir", () => {
  it.each(Object.keys(VARIACOES))(
    "mudar «%s» muda os parâmetros E a chave",
    (campo) => {
      // A lógica E/OU só tem efeito com MAIS DE UMA etiqueta — é a
      // regra do filtro, não um esquecimento: com uma etiqueta só, "E"
      // e "OU" dão a mesma lista. Daí a base deste caso já ter duas.
      const BASE = normalizarFiltros(
        campo === "labelsLogic" ? { labels: ["a", "b"] } : {},
      );
      const alterado = { ...BASE, [campo]: VARIACOES[campo] };

      const antes = parametrosDoKanban(BASE).toString();
      const depois = parametrosDoKanban(alterado).toString();
      expect(depois).not.toBe(antes);

      // E a chave. Era esta metade que faltava: o filtro de etiquetas
      // não entrava na chave, logo o React Query servia a cache antiga
      // e não havia nem pedido para o servidor ignorar.
      const chaveAntes = JSON.stringify(chaveDeFiltros(BASE));
      const chaveDepois = JSON.stringify(chaveDeFiltros(alterado));
      expect(chaveDepois).not.toBe(chaveAntes);
    },
  );

  it("CONTRAPROVA: filtros iguais dão a MESMA chave", () => {
    // Sem isto, uma chave com um valor aleatório passava o teste acima
    // e destruía a cache a cada render.
    expect(JSON.stringify(chaveDeFiltros(BASE))).toBe(
      JSON.stringify(chaveDeFiltros({ ...BASE })),
    );
  });

  it("a chave sobrevive a uma volta completa (normalizar → chave)", () => {
    const filtros = normalizarFiltros({
      consultorFilter: "u1",
      labels: ["x"],
      sub35: true,
      completedDays: 0,
    });
    expect(chaveDeFiltros(filtros)).toEqual(filtros);
  });

  it("a lista de campos cobre tudo o que varia", () => {
    // Contraprova do inventário: se alguém acrescentar um filtro e não o
    // puser em CAMPOS_DE_FILTRO, as VARIAÇÕES deste ficheiro deixam de
    // o cobrir — e é aí que o próximo filtro se perde.
    expect(new Set(Object.keys(VARIACOES))).toEqual(
      new Set(CAMPOS_DE_FILTRO.filter((c) => c !== "viewMode")),
    );
  });
});
