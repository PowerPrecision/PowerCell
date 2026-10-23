import { describe, expect, it } from "vitest";

import {
  ESTADOS_DA_ABA,
  ORDENACAO_POR_OMISSAO,
  campoDaColuna,
  filtrosDaFila,
  normalizarFila,
  opcoesDeOrdenacao,
  ordenacaoValida,
  parametrosDaFila,
  proximaOrdenacao,
  sentidoDaColuna,
  totalDeFiltrosLigados,
} from "./indexRevisao";
import { queryKeys } from "../lib/queryClient";

describe("opções e validação da ordem", () => {
  it("a Fila tem a entrada; as Revisões têm o «indexado em» e nunca a entrada", () => {
    const fila = opcoesDeOrdenacao("pending").map((o) => o.valor);
    const revisoes = opcoesDeOrdenacao("reviews").map((o) => o.valor);
    expect(fila).toContain("created_asc");
    expect(fila.some((v) => v.startsWith("indexed"))).toBe(false);
    expect(revisoes).toContain("indexed_desc");
    expect(revisoes.some((v) => v.startsWith("created"))).toBe(false);
  });

  it("cada campo tem os dois sentidos, e todos os valores são «<campo>_<asc|desc>»", () => {
    for (const aba of ["pending", "reviews"]) {
      const valores = opcoesDeOrdenacao(aba).map((o) => o.valor);
      expect(new Set(valores).size).toBe(valores.length);
      for (const v of valores) expect(v).toMatch(/^[a-z]+_(asc|desc)$/);
      expect(valores.length % 2).toBe(0);
    }
  });

  it("uma ordem que a aba não aceita cai na por omissão (nunca vai ao servidor para dar 422)", () => {
    expect(ordenacaoValida("pending", "indexed_asc")).toBe(ORDENACAO_POR_OMISSAO.pending);
    expect(ordenacaoValida("reviews", "created_asc")).toBe(ORDENACAO_POR_OMISSAO.reviews);
    expect(ordenacaoValida("pending", "hacker")).toBe("created_asc");
    expect(ordenacaoValida("pending", undefined)).toBe("created_asc");
    expect(ordenacaoValida("pending", "client_desc")).toBe("client_desc");
  });
});

describe("cabeçalhos clicáveis", () => {
  it("a coluna da data muda de campo com a aba", () => {
    expect(campoDaColuna("pending", "data")).toBe("created");
    expect(campoDaColuna("reviews", "data")).toBe("indexed");
    expect(campoDaColuna("pending", "documentos")).toBeNull();
  });

  it("noutra coluna começa pelo sentido natural; na mesma, inverte", () => {
    expect(proximaOrdenacao("pending", "created_asc", "processo")).toBe("client_asc");
    expect(proximaOrdenacao("pending", "client_asc", "processo")).toBe("client_desc");
    expect(proximaOrdenacao("pending", "client_desc", "processo")).toBe("client_asc");
    expect(proximaOrdenacao("pending", "client_asc", "alertas")).toBe("alerts_desc");
    expect(proximaOrdenacao("pending", "alerts_desc", "alertas")).toBe("alerts_asc");
    expect(proximaOrdenacao("reviews", "indexed_desc", "data")).toBe("indexed_asc");
  });

  it("uma coluna que não ordena deixa a ordem como está", () => {
    expect(proximaOrdenacao("pending", "client_asc", "documentos")).toBe("client_asc");
  });

  it("aria-sort reflecte a ordem em vigor", () => {
    expect(sentidoDaColuna("pending", "client_asc", "processo")).toBe("ascending");
    expect(sentidoDaColuna("pending", "client_desc", "processo")).toBe("descending");
    expect(sentidoDaColuna("pending", "client_desc", "empresa")).toBe("none");
    expect(sentidoDaColuna("pending", "created_asc", "data")).toBe("ascending");
    expect(sentidoDaColuna("reviews", "indexed_desc", "data")).toBe("descending");
  });
});

describe("filtros", () => {
  it("só mantém o que a aba aceita", () => {
    expect(filtrosDaFila("pending", { estado: "in_review", empresa: " c1 ", origem: "shared" }))
      .toEqual({ estado: "in_review", empresa: "c1", origem: "shared" });
    expect(filtrosDaFila("reviews", { estado: "pending" }).estado).toBe("");
    expect(filtrosDaFila("pending", { estado: "indexed" }).estado).toBe("");
    expect(filtrosDaFila("pending", { origem: "todas" }).origem).toBe("");
    expect(ESTADOS_DA_ABA.reviews).toEqual(["indexed"]);
  });

  it("uma empresa gigante (URL escrito à mão) é cortada", () => {
    expect(filtrosDaFila("pending", { empresa: "x".repeat(500) }).empresa).toHaveLength(64);
  });

  it("conta os filtros ligados (a ordem não conta)", () => {
    expect(totalDeFiltrosLigados({ estado: "", empresa: "", origem: "" })).toBe(0);
    expect(totalDeFiltrosLigados({ estado: "pending", empresa: "c", origem: "" })).toBe(2);
    expect(totalDeFiltrosLigados(undefined)).toBe(0);
  });
});

describe("parametrosDaFila — o pedido só leva o que se afasta da omissão", () => {
  const vazio = { estado: "", empresa: "", origem: "" };

  it("por omissão não leva sort_by nem filtros", () => {
    expect(parametrosDaFila({ tab: "pending", page: 1, q: "", ordem: "created_asc", filtros: vazio }))
      .toEqual({ tab: "pending", page: 1, q: undefined });
    expect(parametrosDaFila({ tab: "reviews", page: 2, q: "", ordem: "indexed_desc", filtros: vazio }).sort_by).toBeUndefined();
  });

  it("leva cada um com o nome do servidor", () => {
    expect(parametrosDaFila({
      tab: "pending", page: 3, q: "ana", ordem: "client_desc",
      filtros: { estado: "in_review", empresa: "c-power", origem: "own" },
    })).toEqual({
      tab: "pending", page: 3, q: "ana", sort_by: "client_desc",
      index_status: "in_review", company_id: "c-power", origin: "own",
    });
  });
});

describe("a chave de cache", () => {
  const f = { estado: "", empresa: "", origem: "" };
  const base = queryKeys.index.queue("pending", 1, "", "created_asc", f);

  it("muda com CADA parâmetro (senão mudar o filtro não provocava um pedido)", () => {
    const variantes = [
      queryKeys.index.queue("reviews", 1, "", "created_asc", f),
      queryKeys.index.queue("pending", 2, "", "created_asc", f),
      queryKeys.index.queue("pending", 1, "x", "created_asc", f),
      queryKeys.index.queue("pending", 1, "", "client_asc", f),
      queryKeys.index.queue("pending", 1, "", "created_asc", { ...f, estado: "pending" }),
      queryKeys.index.queue("pending", 1, "", "created_asc", { ...f, empresa: "c" }),
      queryKeys.index.queue("pending", 1, "", "created_asc", { ...f, origem: "own" }),
    ];
    for (const v of variantes) expect(v).not.toEqual(base);
    expect(new Set(variantes.map((v) => JSON.stringify(v))).size).toBe(variantes.length);
  });

  it("filtros iguais dão a mesma chave e continua sob o prefixo que a invalidação alcança", () => {
    expect(queryKeys.index.queue("pending", 1, "", "created_asc", { ...f })).toEqual(base);
    expect(base.slice(0, queryKeys.index.queueAll().length)).toEqual(queryKeys.index.queueAll());
  });
});

describe("normalizarFila", () => {
  it("lê as empresas com a forma garantida", () => {
    const f = normalizarFila({
      items: [], total: 0,
      facets: { companies: [{ id: "c1", name: "Power", count: 4 }, { id: "", name: "x" }, null, { id: "c2", count: "3" }] },
    });
    expect(f.empresas).toEqual([{ id: "c1", nome: "Power", total: 4 }, { id: "c2", nome: "c2", total: 3 }]);
  });
  it("sem facets (servidor antigo) são zero empresas, nunca um erro", () => {
    expect(normalizarFila({ items: [] }).empresas).toEqual([]);
    expect(normalizarFila({ items: [], facets: { companies: { 0: "x" } } }).empresas).toEqual([]);
  });
});
