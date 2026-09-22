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

// jsdom não implementa estes; vários componentes Radix/Shadcn tocam-lhes.
if (!window.matchMedia) {
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

if (!window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
