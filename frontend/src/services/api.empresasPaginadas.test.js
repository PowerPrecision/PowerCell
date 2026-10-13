/**
 * `getAllCompanies` (Lote 4): a API limita `size` a 100 e o diálogo «Alterar Empresa» pedia 200 → 422.
 * Percorre as páginas até ao `total`, nunca pede mais do que o máximo e não fica preso num ciclo.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import api, { TAMANHO_DA_PAGINA_DE_EMPRESAS, getAllCompanies } from "./api";

const MAXIMO_DA_API = 100;

function empresas(de, ate) {
  return Array.from({ length: ate - de + 1 }, (_, i) => ({ id: `c${de + i}`, name: `E${de + i}` }));
}

describe("getAllCompanies", () => {
  let pedidos;
  beforeEach(() => {
    pedidos = [];
  });

  function servir(total) {
    vi.spyOn(api, "get").mockImplementation(async (_url, { params }) => {
      pedidos.push(params);
      const inicio = (params.page - 1) * params.size + 1;
      const fim = Math.min(total, params.page * params.size);
      return { data: { companies: inicio > total ? [] : empresas(inicio, fim), total } };
    });
  }

  it("o tamanho da página é o máximo que a API aceita (ou menos)", () => {
    expect(TAMANHO_DA_PAGINA_DE_EMPRESAS).toBeLessThanOrEqual(MAXIMO_DA_API);
  });

  it("junta todas as páginas e nunca pede mais do que o máximo", async () => {
    servir(250);
    const todas = await getAllCompanies();
    expect(todas).toHaveLength(250);
    expect(new Set(todas.map((e) => e.id)).size).toBe(250);
    expect(pedidos.map((p) => p.page)).toEqual([1, 2, 3]);
    expect(pedidos.every((p) => p.size <= MAXIMO_DA_API)).toBe(true);
  });

  it("uma página só chega: não pede a seguinte", async () => {
    servir(30);
    expect(await getAllCompanies()).toHaveLength(30);
    expect(pedidos).toHaveLength(1);
  });

  it("sem empresas devolve lista vazia (não fica em ciclo)", async () => {
    servir(0);
    expect(await getAllCompanies()).toEqual([]);
    expect(pedidos).toHaveLength(1);
  });
});
