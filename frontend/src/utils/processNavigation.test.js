/**
 * Ponto 17 — o estado e a cache da Navegação Contígua.
 *
 * O que estes testes protegem, por ordem de gravidade:
 *
 *  1. Uma seta NUNCA pode apontar para o sítio errado. É pior do que não
 *     haver seta: não dá erro, não deixa rasto, e o utilizador só
 *     percebe depois de editar a ficha errada. Daí haver tantos testes
 *     sobre o caso "este processo não pertence a esta listagem".
 *  2. As camadas 1 e 2 têm de custar ZERO pedidos. Se `precisaDeSeguinte`
 *     ficasse sempre verdadeiro, o endpoint da camada 3 seria chamado em
 *     cada abertura de processo — exactamente o over-fetching que este
 *     desenho existe para evitar.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  CHAVE_CONTEXTO,
  VERSAO_CONTEXTO,
  construirContextoDeNavegacao,
  vizinhosNoContexto,
  comVizinhosDoServidor,
  guardarContexto,
  lerContexto,
  paramsDeVizinhos,
} from "./processNavigation";

function contextoDeExemplo(over = {}) {
  return construirContextoDeNavegacao({
    ids: ["a", "b", "c"],
    page: 1,
    size: 3,
    total: 3,
    origem: "/processos",
    params: { view_mode: "all" },
    ...over,
  });
}

describe("construirContextoDeNavegacao", () => {
  it("guarda os ids pela ordem recebida", () => {
    expect(contextoDeExemplo().ids).toEqual(["a", "b", "c"]);
  });

  it("descarta ids vazios sem deslocar a lista", () => {
    const ctx = construirContextoDeNavegacao({
      ids: ["a", null, "b", "", undefined, "c"], page: 1, size: 3, total: 3,
    });
    expect(ctx.ids).toEqual(["a", "b", "c"]);
  });

  it("devolve null quando não há ids nenhuns", () => {
    // Uma listagem vazia não tem vizinhança para oferecer.
    expect(construirContextoDeNavegacao({ ids: [] })).toBeNull();
    expect(construirContextoDeNavegacao({})).toBeNull();
    expect(construirContextoDeNavegacao()).toBeNull();
  });

  it("recupera de paginação em falta ou absurda", () => {
    const ctx = construirContextoDeNavegacao({ ids: ["a"], page: 0, size: -5 });
    expect(ctx.page).toBe(1);
    expect(ctx.size).toBe(1);
    expect(ctx.total).toBe(1);
  });

  it("copia os params em vez de os referenciar", () => {
    // O objecto vem do estado da listagem; guardá-lo por referência
    // faria o contexto mudar sozinho quando os filtros mudassem.
    const params = { status: "cpcv" };
    const ctx = construirContextoDeNavegacao({ ids: ["a"], params });
    params.status = "outra";
    expect(ctx.params.status).toBe("cpcv");
  });
});

describe("vizinhosNoContexto — dentro da página (zero pedidos)", () => {
  it("dá os dois lados a meio da lista", () => {
    const v = vizinhosNoContexto(contextoDeExemplo(), "b");
    expect(v.disponivel).toBe(true);
    expect(v.anteriorId).toBe("a");
    expect(v.seguinteId).toBe("c");
    expect(v.posicao).toBe(2);
    expect(v.total).toBe(3);
  });

  it("não pede nada ao servidor no primeiro item da PRIMEIRA página", () => {
    const v = vizinhosNoContexto(contextoDeExemplo(), "a");
    expect(v.anteriorId).toBeNull();
    expect(v.precisaDeAnterior).toBe(false);
  });

  it("não pede nada ao servidor no último item do ÚLTIMO processo", () => {
    const v = vizinhosNoContexto(contextoDeExemplo(), "c");
    expect(v.seguinteId).toBeNull();
    expect(v.precisaDeSeguinte).toBe(false);
  });

  it("calcula a posição global, não a posição na página", () => {
    // "Processo 23 de 87" — e não "2 de 3".
    // (7 páginas cheias de 3 = 21, mais o índice 1 da página aberta.)
    const ctx = contextoDeExemplo({ page: 8, size: 3, total: 87 });
    expect(vizinhosNoContexto(ctx, "b").posicao).toBe(23);
  });
});

describe("vizinhosNoContexto — a fronteira da página (camada 3)", () => {
  it("marca o anterior como pedido ao servidor no topo de uma página do meio", () => {
    const ctx = contextoDeExemplo({ page: 2, size: 3, total: 9 });
    const v = vizinhosNoContexto(ctx, "a");
    expect(v.anteriorId).toBeNull();
    expect(v.precisaDeAnterior).toBe(true);
    expect(v.precisaDeSeguinte).toBe(false);
  });

  it("marca o seguinte como pedido ao servidor no fim de uma página do meio", () => {
    const ctx = contextoDeExemplo({ page: 2, size: 3, total: 9 });
    const v = vizinhosNoContexto(ctx, "c");
    expect(v.seguinteId).toBeNull();
    expect(v.precisaDeSeguinte).toBe(true);
    expect(v.precisaDeAnterior).toBe(false);
  });

  it("não pede o seguinte quando já se está no último processo do total", () => {
    // Fim da página 3 de 3: não há mais nada. Um pedido aqui seria
    // desperdício puro, e é o caso em que é mais fácil enganar-se.
    const ctx = contextoDeExemplo({ page: 3, size: 3, total: 9 });
    expect(vizinhosNoContexto(ctx, "c").precisaDeSeguinte).toBe(false);
  });

  it("no meio da página nunca pede nada", () => {
    const ctx = contextoDeExemplo({ page: 2, size: 3, total: 9 });
    const v = vizinhosNoContexto(ctx, "b");
    expect(v.precisaDeAnterior).toBe(false);
    expect(v.precisaDeSeguinte).toBe(false);
  });
});

describe("vizinhosNoContexto — quando NÃO há vizinhança a oferecer", () => {
  it("recusa um processo que não está na listagem guardada", () => {
    // Chegou por pesquisa global, link ou notificação. As setas
    // desaparecem em vez de apontarem para os vizinhos de outro.
    const v = vizinhosNoContexto(contextoDeExemplo(), "z");
    expect(v.disponivel).toBe(false);
    expect(v.anteriorId).toBeNull();
    expect(v.seguinteId).toBeNull();
    expect(v.precisaDeSeguinte).toBe(false);
  });

  it("recusa contexto nulo", () => {
    expect(vizinhosNoContexto(null, "a").disponivel).toBe(false);
    expect(vizinhosNoContexto(undefined, "a").disponivel).toBe(false);
  });

  it("recusa um contexto de uma versão que não conhece", () => {
    const antigo = { ...contextoDeExemplo(), versao: VERSAO_CONTEXTO + 1 };
    expect(vizinhosNoContexto(antigo, "b").disponivel).toBe(false);
  });

  it("recusa um contexto sem ids", () => {
    expect(vizinhosNoContexto({ versao: VERSAO_CONTEXTO }, "a").disponivel)
      .toBe(false);
  });
});

describe("comVizinhosDoServidor", () => {
  const base = contextoDeExemplo({ page: 2, size: 3, total: 9 });

  it("preenche o lado em falta com a resposta do servidor", () => {
    const v = vizinhosNoContexto(base, "c");
    const completo = comVizinhosDoServidor(v, {
      previous_id: "b", next_id: "d", position: 6, total: 9,
    });
    expect(completo.seguinteId).toBe("d");
    expect(completo.precisaDeSeguinte).toBe(false);
  });

  it("não deixa o servidor sobrepor-se ao que a página já sabe", () => {
    // O contexto local é o que o utilizador ESTÁ a ver. Se a listagem
    // mudou entretanto no servidor, mandar a seta para outro lado a
    // meio da página seria desorientar sem aviso.
    const v = vizinhosNoContexto(base, "b");
    const completo = comVizinhosDoServidor(v, {
      previous_id: "outro", next_id: "outro", position: 99,
    });
    expect(completo.anteriorId).toBe("a");
    expect(completo.seguinteId).toBe("c");
    expect(completo.posicao).toBe(5);
  });

  it("sem resposta devolve o que já tinha", () => {
    const v = vizinhosNoContexto(base, "b");
    expect(comVizinhosDoServidor(v, null)).toBe(v);
  });
});

describe("guardarContexto / lerContexto", () => {
  let store;
  beforeEach(() => {
    const dados = new Map();
    store = {
      getItem: (k) => (dados.has(k) ? dados.get(k) : null),
      setItem: (k, v) => dados.set(k, v),
      removeItem: (k) => dados.delete(k),
      _dados: dados,
    };
  });

  it("dá a volta completa", () => {
    guardarContexto(contextoDeExemplo(), store);
    expect(lerContexto(store).ids).toEqual(["a", "b", "c"]);
  });

  it("usa uma chave própria e não polui o resto da sessão", () => {
    guardarContexto(contextoDeExemplo(), store);
    expect([...store._dados.keys()]).toEqual([CHAVE_CONTEXTO]);
  });

  it("devolve null com a sessão vazia", () => {
    expect(lerContexto(store)).toBeNull();
  });

  it("devolve null perante JSON corrompido", () => {
    store.setItem(CHAVE_CONTEXTO, "{isto não é json");
    expect(lerContexto(store)).toBeNull();
  });

  it("devolve null perante um contexto de outra versão", () => {
    store.setItem(CHAVE_CONTEXTO, JSON.stringify({ versao: 99, ids: ["a"] }));
    expect(lerContexto(store)).toBeNull();
  });

  it("não rebenta quando o storage recusa escrever", () => {
    // Janela privada / quota cheia. As setas são uma conveniência: a
    // página de Detalhes tem de abrir na mesma.
    const recusa = {
      getItem: () => { throw new Error("bloqueado"); },
      setItem: () => { throw new Error("quota"); },
    };
    expect(guardarContexto(contextoDeExemplo(), recusa)).toBe(false);
    expect(lerContexto(recusa)).toBeNull();
  });

  it("não rebenta sem storage nenhum", () => {
    const semJanela = vi.spyOn(globalThis, "window", "get")
      .mockReturnValue(undefined);
    try {
      expect(guardarContexto(contextoDeExemplo())).toBe(false);
      expect(lerContexto()).toBeNull();
    } finally {
      semJanela.mockRestore();
    }
  });
});

describe("paramsDeVizinhos", () => {
  it("repete a chave para cada etiqueta", () => {
    // O backend lê `labels` como List[str]. Uma chave só com "a,b"
    // procuraria uma etiqueta chamada "a,b" e a vizinhança sairia
    // calculada sobre outro filtro — sem erro nenhum.
    const sp = paramsDeVizinhos({ labels: ["VIP", "Urgente"], labels_logic: "AND" });
    expect(sp.getAll("labels")).toEqual(["VIP", "Urgente"]);
    expect(sp.get("labels_logic")).toBe("AND");
  });

  it("descarta valores vazios, nulos e indefinidos", () => {
    const sp = paramsDeVizinhos({ status: "", search: null, tipo: undefined, a: "1" });
    expect([...sp.keys()]).toEqual(["a"]);
  });

  it("descarta entradas vazias dentro de um array", () => {
    const sp = paramsDeVizinhos({ labels: ["VIP", "", null] });
    expect(sp.getAll("labels")).toEqual(["VIP"]);
  });

  it("serializa booleanos como o backend os espera", () => {
    const sp = paramsDeVizinhos({ show_all: true, is_indexed: false });
    expect(sp.get("show_all")).toBe("true");
    // `false` é uma resposta, não uma ausência: `is_indexed=false` é o
    // filtro "por indexar". Deixá-lo cair mostraria também os indexados.
    expect(sp.get("is_indexed")).toBe("false");
  });

  it("aguenta params nulos", () => {
    expect([...paramsDeVizinhos(null).keys()]).toEqual([]);
    expect([...paramsDeVizinhos().keys()]).toEqual([]);
  });
});
