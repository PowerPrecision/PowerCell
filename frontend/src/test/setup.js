/**
 * Setup global dos testes (Vitest + jsdom).
 * Carregado por `setupFiles` no vitest.config.js.
 */
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Desmontar a árvore React entre testes — sem isto, os `getBy*` do teste
// seguinte encontram nós do anterior e as falhas aparecem no sítio errado.
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// Alguns ficheiros correm em ambiente `node` (`// @vitest-environment node`)
// para exercitar transporte HTTP a sério — aí não há `window`, e tocar-lhe
// aqui rebentava a RECOLHA desse ficheiro inteiro, com uma mensagem sobre
// `matchMedia` que não aponta para o problema real.
const temDOM = typeof window !== "undefined";

// jsdom não implementa estes; vários componentes Radix/Shadcn tocam-lhes.
if (temDOM && !window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

if (temDOM && !window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

if (temDOM && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// A API de Pointer Capture não existe no jsdom e o `Select` do Radix
// chama-a ao abrir a lista: sem isto, `hasPointerCapture is not a
// function` faz o clique morrer em silêncio e o teste falha a dizer que
// não encontrou a opção — uma pista que aponta para o sítio errado.
if (temDOM && !Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
  Element.prototype.setPointerCapture = () => {};
  Element.prototype.releasePointerCapture = () => {};
}

// O jsdom tenta DESCODIFICAR as imagens de um `<img src=…>` e, para isso, faz
// `require("canvas")` (`jsdom/lib/jsdom/utils.js`). Este projecto aponta o
// `canvas` para um pacote VAZIO no `package.json`
// (`"canvas": "npm:empty-npm-package@1.0.0"`, para não compilar o módulo
// nativo) — e é aí que está a armadilha: o `require` **tem sucesso**, pelo que
// o jsdom conclui que tem descodificador (`if (!Canvas) return;` não dispara) e
// depois rebenta em `new Canvas.Image()`, que não existe.
//
// O sintoma é `TypeError: Canvas.Image is not a constructor` num stack só de
// `react-dom`, que não menciona imagens nem canvas e manda procurar no sítio
// errado. Qualquer teste que MONTE uma página com um logótipo bate nisto.
//
// Um stub em `window.Image` não serve: o jsdom usa a sua referência interna.
// O que resolve é dar ao módulo vazio a única coisa que o jsdom lhe pede — e
// como o `require` devolve sempre o MESMO objecto de exports, acrescentar-lhe
// a classe aqui é visto pelo jsdom, que a capturou por referência.
if (temDOM) {
  try {
    const { createRequire } = await import("node:module");
    const requireCJS = createRequire(import.meta.url);
    const canvas = requireCJS("canvas");

    if (canvas && typeof canvas.Image !== "function") {
      // Só o que o jsdom toca: constrói, atribui `src` e pode chamar
      // `onerror`. Descodificar bytes não interessa a nenhum teste — o que se
      // afirma é o `alt`, o `src` ou a presença do elemento.
      canvas.Image = class {
        constructor() {
          this.width = 0;
          this.height = 0;
          this.onload = null;
          this.onerror = null;
          this._src = "";
        }

        get src() {
          return this._src;
        }

        set src(valor) {
          this._src = valor;
        }
      };
    }
  } catch {
    // Sem o pacote `canvas` resolvível, o jsdom faz `Canvas = null` e volta
    // atrás sozinho — que é o caminho bom. Nada a fazer.
  }
}
