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
