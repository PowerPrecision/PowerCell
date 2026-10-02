/**
 * O ecrã branco no Voltar do browser (Lote 3, ponto 3).
 *
 * TRÊS DEFEITOS NA MESMA FRONTEIRA
 * O `LazyChunkErrorBoundary` embrulha TODAS as rotas do `App.js`.
 *
 * 1. **A lista de causas era larga demais.** Incluía
 *    `includes("Unexpected token")`, e `JSON.parse("{mau")` levanta
 *    `SyntaxError: Unexpected token 'm', ...` — qualquer falha de
 *    `JSON.parse` em qualquer página era classificada como erro de chunk e
 *    desencadeava um recarregamento. O defeito real nunca chegava ao Sentry.
 *
 * 2. **O ECRÃ BRANCO.** Para tudo o que não fosse chunk, devolvia
 *    `{ hasError: false }`. Um boundary que não muda de estado **não trata
 *    o erro**: o React volta a renderizar os mesmos filhos, eles levantam
 *    outra vez e, sem fronteira a assumir a falha, o React desmonta a
 *    árvore inteira. Como as rotas têm fronteira própria, o que chega aqui
 *    é o que vive FORA delas — contextos, layout, router — e é exactamente
 *    isso que o Voltar do browser volta a montar de uma vez.
 *
 * 3. **O cache-busting acumulava e matava o histórico.**
 *    `window.location.search` já inclui o `?`, logo a segunda passagem dava
 *    `/x?_t=1&_t=2` e a terceira `/x?_t=1&_t=2&_t=3`. E usava
 *    `location.replace`, que apaga a entrada do histórico — ou seja, a
 *    correcção do ecrã branco estragava o Voltar por si mesma.
 */
import { describe, expect, it } from "vitest";

import {
  CODIGOS_DE_CHUNK,
  NOMES_DE_CHUNK,
  SINAIS_DE_CHUNK,
  SINAIS_REJEITADOS,
  eErroDeChunk,
  urlDeRecarregamento,
} from "./chunkErrors";

describe("Um erro de chunk é reconhecido", () => {
  it("pelo nome", () => {
    const e = new Error("qualquer coisa");
    e.name = "ChunkLoadError";
    expect(eErroDeChunk(e)).toBe(true);
  });

  it("pelo código", () => {
    const e = new Error("x");
    e.code = "MODULE_NOT_FOUND";
    expect(eErroDeChunk(e)).toBe(true);
  });

  it("pela mensagem do Vite", () => {
    expect(
      eErroDeChunk(new Error("Failed to fetch dynamically imported module: /assets/x.js")),
    ).toBe(true);
  });

  it("pela mensagem do webpack", () => {
    expect(eErroDeChunk(new Error("Loading chunk 42 failed."))).toBe(true);
  });

  it("pelo MIME type, mas só com a frase COMPLETA", () => {
    expect(
      eErroDeChunk(
        new Error(
          "Expected a JavaScript module script but the server responded with a MIME type of text/html",
        ),
      ),
    ).toBe(true);
  });

  it("sem distinguir maiúsculas", () => {
    expect(eErroDeChunk(new Error("LOADING CHUNK 7 FAILED"))).toBe(true);
  });
});

describe("Um erro da APLICAÇÃO não é um erro de chunk", () => {
  it("o caso que estragava tudo: a mensagem literal «Unexpected token»", () => {
    // Afirmada como LITERAL, e não extraída de um `JSON.parse` a correr: o
    // texto do V8 muda com a versão do Node ("{mau" dá hoje «Expected
    // property name or '}'»), e um teste preso à mensagem de uma versão
    // falha num runtime diferente por um motivo que não é o do teste.
    expect(
      eErroDeChunk(new SyntaxError(`Unexpected token 'i', "isto" is not valid JSON`)),
    ).toBe(false);
  });

  it("e um JSON.parse REAL deste runtime também não é chunk", () => {
    // O par do teste acima: este prova que, qualquer que seja a mensagem
    // que esta versão do V8 produza, não é classificada como chunk.
    const mensagens = [];
    for (const entrada of ["{mau", "isto nao e json", '{"a":}', "undefined"]) {
      try {
        JSON.parse(entrada);
      } catch (e) {
        mensagens.push(e.message);
        expect(eErroDeChunk(e)).toBe(false);
      }
    }
    expect(mensagens).toHaveLength(4);
  });

  it("um TypeError de uma propriedade em falta", () => {
    expect(
      eErroDeChunk(new TypeError("Cannot read properties of undefined (reading 'title')")),
    ).toBe(false);
  });

  it("o «companies is not iterable» do incidente das chaves de cache", () => {
    expect(eErroDeChunk(new TypeError("companies is not iterable"))).toBe(false);
  });

  it("«Script error» — opaco, de outra origem, e não de um chunk", () => {
    expect(eErroDeChunk(new Error("Script error."))).toBe(false);
  });

  it("uma mensagem de API que menciona text/html", () => {
    expect(
      eErroDeChunk(new Error("Unexpected response: text/html instead of application/json")),
    ).toBe(false);
  });

  it("nada, undefined, ou um erro sem mensagem", () => {
    expect(eErroDeChunk(null)).toBe(false);
    expect(eErroDeChunk(undefined)).toBe(false);
    expect(eErroDeChunk({})).toBe(false);
    expect(eErroDeChunk(new Error(""))).toBe(false);
  });
});

describe("As sub-cadeias largas NÃO voltam", () => {
  it("nenhum sinal rejeitado está na lista activa", () => {
    // Guarda contra a regressão: cada uma destas classificava erros comuns
    // da aplicação como erros de chunk.
    for (const rejeitada of Object.keys(SINAIS_REJEITADOS)) {
      expect(SINAIS_DE_CHUNK).not.toContain(rejeitada);
    }
  });

  it("cada rejeitada tem o MOTIVO escrito", () => {
    // Sem o motivo, a próxima pessoa volta a acrescentá-la.
    for (const motivo of Object.values(SINAIS_REJEITADOS)) {
      expect(typeof motivo).toBe("string");
      expect(motivo.length).toBeGreaterThan(10);
    }
  });

  it("CONTRAPROVA: a lista activa não ficou vazia", () => {
    // Sem isto, "não reconhece nada" passava os testes de rejeição e os
    // erros de chunk deixavam de ser tratados.
    expect(SINAIS_DE_CHUNK.length).toBeGreaterThanOrEqual(4);
    expect(NOMES_DE_CHUNK).toContain("ChunkLoadError");
    expect(CODIGOS_DE_CHUNK).toContain("MODULE_NOT_FOUND");
  });
});

describe("O recarregamento não acumula nem mata o histórico", () => {
  it("acrescenta _t a um URL sem query", () => {
    expect(urlDeRecarregamento({ pathname: "/processo/7", search: "" }, { agora: 111 })).toBe(
      "/processo/7?_t=111",
    );
  });

  it("preserva os parâmetros que já existiam", () => {
    expect(
      urlDeRecarregamento({ pathname: "/lista", search: "?tab=docs" }, { agora: 111 }),
    ).toBe("/lista?tab=docs&_t=111");
  });

  it("NÃO acumula: um _t já presente significa que já recarregámos", () => {
    // A versão antiga produzia `/x?_t=1&_t=2&_t=3`, com o comentário a
    // dizer que era "para evitar ciclo infinito".
    expect(urlDeRecarregamento({ pathname: "/x", search: "?_t=1" })).toBeNull();
  });

  it("nem com outros parâmetros à mistura", () => {
    expect(urlDeRecarregamento({ pathname: "/x", search: "?tab=a&_t=1" })).toBeNull();
  });

  it("um location em falta não rebenta", () => {
    expect(urlDeRecarregamento(null, { agora: 9 })).toBe("/?_t=9");
  });
});
