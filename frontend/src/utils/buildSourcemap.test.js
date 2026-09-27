/**
 * D-11 — os sourcemaps de produção eram servidos publicamente.
 *
 * O `'hidden'` do Vite não impede o download: só apaga a referência no JS.
 * Confirmado contra produção em 2026-09-27 (`GET
 * /assets/<chunk>.js.map` → 200 com o código completo).
 */
import { describe, expect, it } from "vitest";

import { resolverSourcemapDoBuild, avisoDoSourcemap } from "./buildSourcemap";

describe("resolverSourcemapDoBuild", () => {
  it("produção COM token: gera escondidos, para o plugin enviar e apagar", () => {
    expect(
      resolverSourcemapDoBuild({ isProduction: true, temTokenDoSentry: true }),
    ).toBe("hidden");
  });

  it("produção SEM token: NÃO gera — é o caso que expunha o código", () => {
    // Era este o estado real do deploy: sem token, o plugin não corria, nada
    // era enviado, nada era apagado, e os .map ficavam servidos.
    expect(
      resolverSourcemapDoBuild({ isProduction: true, temTokenDoSentry: false }),
    ).toBe(false);
  });

  it("fora de produção gera sempre, com token ou sem ele", () => {
    expect(
      resolverSourcemapDoBuild({ isProduction: false, temTokenDoSentry: false }),
    ).toBe(true);
    expect(
      resolverSourcemapDoBuild({ isProduction: false, temTokenDoSentry: true }),
    ).toBe(true);
  });
});

describe("avisoDoSourcemap", () => {
  it("avisa quando um build de produção sai sem mapas", () => {
    const aviso = avisoDoSourcemap({ isProduction: true, temTokenDoSentry: false });
    expect(aviso).toContain("SENTRY_AUTH_TOKEN");
  });

  it("cala-se quando há token, e fora de produção", () => {
    expect(avisoDoSourcemap({ isProduction: true, temTokenDoSentry: true })).toBeNull();
    expect(avisoDoSourcemap({ isProduction: false, temTokenDoSentry: false })).toBeNull();
  });
});
