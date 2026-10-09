import { describe, expect, it } from "vitest";

import {
  deveAvisar,
  frase,
  normalizarProcessosActivos,
  processosOcultos,
  rotuloDoTitular,
} from "./processosActivos";

const RESPOSTA = {
  client_id: "c1",
  client_name: "Ana Silva",
  total: 3,
  processos: [
    { id: "p1", process_number: 412, status: "em_analise", status_label: "Em Análise Bancária", titular: "titular1", consultor_names: ["Rui"] },
    { id: "p2", process_number: 380, status: "novo", status_label: "Novo", titular: "titular2", consultor_names: [] },
  ],
};

describe("normalizarProcessosActivos", () => {
  it("lê a forma REAL do servidor", () => {
    const res = normalizarProcessosActivos(RESPOSTA);
    expect(res.client_name).toBe("Ana Silva");
    expect(res.total).toBe(3);
    expect(res.processos.map((p) => p.id)).toEqual(["p1", "p2"]);
    expect(res.processos[0].status_label).toBe("Em Análise Bancária");
  });

  it("o total real pode exceder a lista (o servidor limita-a) e nunca fica abaixo dela", () => {
    expect(normalizarProcessosActivos(RESPOSTA).total).toBe(3);
    expect(normalizarProcessosActivos({ ...RESPOSTA, total: 1 }).total).toBe(2);
  });

  it.each([undefined, null, {}, { processos: null }, { processos: {} }])(
    "forma inesperada (%j) → sem aviso (Array.isArray, nunca `|| []`)",
    (forma) => {
      expect(deveAvisar(normalizarProcessosActivos(forma))).toBe(false);
    },
  );

  it("descarta linhas sem id e cai para o estado quando falta o rótulo", () => {
    const res = normalizarProcessosActivos({
      total: 2,
      processos: [{ process_number: 1 }, { id: "p9", status: "fase_x", titular: "inventado" }],
    });
    expect(res.processos).toHaveLength(1);
    expect(res.processos[0].status_label).toBe("fase_x");
    expect(res.processos[0].titular).toBe("co_titular");
  });
});

describe("a política do aviso", () => {
  it("só avisa quando há mesmo processos activos", () => {
    expect(deveAvisar(normalizarProcessosActivos(RESPOSTA))).toBe(true);
    expect(deveAvisar(normalizarProcessosActivos({ total: 0, processos: [] }))).toBe(false);
    expect(deveAvisar(null)).toBe(false);
  });

  it("singular e plural", () => {
    expect(frase({ total: 1 })).toBe("1 processo activo");
    expect(frase({ total: 3 })).toBe("3 processos activos");
  });

  it("conta os que não cabem na lista", () => {
    expect(processosOcultos(normalizarProcessosActivos(RESPOSTA))).toBe(1);
    expect(processosOcultos({ total: 2, processos: [1, 2] })).toBe(0);
  });

  it("rotula a posição do cliente", () => {
    expect(rotuloDoTitular("titular1")).toBe("1.º titular");
    expect(rotuloDoTitular("titular2")).toBe("2.º titular");
    expect(rotuloDoTitular("co_titular")).toBe("co-titular");
    expect(rotuloDoTitular("???")).toBe("co-titular");
  });
});
