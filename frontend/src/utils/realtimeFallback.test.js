import { describe, expect, it } from "vitest";

import {
  INTERVALO_BASE_MS,
  aplicarRecuoPorRateLimit,
  intervaloEfectivo,
  precisaDeRecuperar,
} from "./realtimeFallback";

describe("intervaloEfectivo", () => {
  it("não sonda enquanto o WebSocket estiver ligado", () => {
    // É este o corte da Fase 3: com a conduta do Redis e a Parede activas,
    // o evento chega a quem tem de chegar, em qualquer worker.
    expect(intervaloEfectivo({ isConnected: true })).toBeNull();
  });

  it("volta a sondar quando o WebSocket cai", () => {
    expect(intervaloEfectivo({ isConnected: false })).toBe(INTERVALO_BASE_MS);
  });

  it("respeita um intervalo já recuado por rate limiting", () => {
    expect(intervaloEfectivo({ isConnected: false, intervaloActual: 120000 }))
      .toBe(120000);
  });

  it("um intervalo inválido cai no base em vez de desligar a sondagem", () => {
    // Falhar para "sem rede de segurança" seria o pior dos dois lados.
    for (const mau of [0, -1, NaN, null, undefined, "30s"]) {
      expect(intervaloEfectivo({ isConnected: false, intervaloActual: mau }))
        .toBe(INTERVALO_BASE_MS);
    }
  });
});

describe("precisaDeRecuperar", () => {
  it("recupera quando a ligação volta depois de ter caído", () => {
    // Os eventos emitidos com o socket em baixo perderam-se: sem esta
    // leitura única, o ecrã fica desactualizado até o utilizador recarregar.
    expect(precisaDeRecuperar({ anterior: false, actual: true })).toBe(true);
  });

  it("não recupera na primeira ligação", () => {
    // A montagem já fez a leitura inicial; recuperar aqui seria pedir duas
    // vezes a mesma coisa em cada abertura de página.
    expect(precisaDeRecuperar({ anterior: null, actual: true })).toBe(false);
  });

  it("não recupera ao perder a ligação nem em estado estável", () => {
    expect(precisaDeRecuperar({ anterior: true, actual: false })).toBe(false);
    expect(precisaDeRecuperar({ anterior: true, actual: true })).toBe(false);
    expect(precisaDeRecuperar({ anterior: false, actual: false })).toBe(false);
  });
});

describe("aplicarRecuoPorRateLimit", () => {
  it("duplica o intervalo a cada 429", () => {
    expect(aplicarRecuoPorRateLimit(30000)).toBe(60000);
    expect(aplicarRecuoPorRateLimit(60000)).toBe(120000);
  });

  it("nunca ultrapassa o tecto de 5 minutos", () => {
    expect(aplicarRecuoPorRateLimit(200000)).toBe(300000);
    expect(aplicarRecuoPorRateLimit(300000)).toBe(300000);
  });

  it("parte do base quando recebe lixo", () => {
    expect(aplicarRecuoPorRateLimit(undefined)).toBe(INTERVALO_BASE_MS * 2);
  });
});
