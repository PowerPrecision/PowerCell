import { describe, expect, it } from "vitest";

import { parceirosDoProcesso, podeRevogarPartilha, sePodeRevogar } from "./partilhaProcesso";

describe("podeRevogarPartilha", () => {
  it.each(["admin", "ceo", "diretor", " Diretor "])("%s pode", (papel) => {
    expect(podeRevogarPartilha(papel)).toBe(true);
  });
  it.each(["consultor", "intermediario", "administrativo", "indexacao", "parceiro", "", null, undefined])(
    "%s não pode",
    (papel) => {
      expect(podeRevogarPartilha(papel)).toBe(false);
    },
  );
});

describe("parceirosDoProcesso", () => {
  it("lê a forma REAL do registo", () => {
    const res = parceirosDoProcesso({
      partner_companies: [
        { company_id: "cmp-domus", company_name: "Domus", network_id: "grupo_domus", added_at: "2026-10-09T10:00:00Z", added_by: "u1" },
      ],
    });
    expect(res).toEqual([{ id: "cmp-domus", nome: "Domus", desde: "2026-10-09T10:00:00Z" }]);
  });

  it.each([undefined, null, {}, { partner_companies: null }, { partner_companies: {} }, { partner_companies: [] }])(
    "forma inesperada (%j) → sem parceiros (Array.isArray, nunca `|| []`)",
    (processo) => {
      expect(parceirosDoProcesso(processo)).toEqual([]);
    },
  );

  it("descarta entradas vazias e repetidas; o nome cai para o id", () => {
    const res = parceirosDoProcesso({
      partner_companies: [
        { company_id: "a", company_name: "A" },
        { company_id: "a", company_name: "outra A" },
        {},
        { company_id: "b" },
        { company_name: "Só nome" },
      ],
    });
    expect(res.map((p) => p.nome)).toEqual(["A", "b", "Só nome"]);
  });

  it("sem company_id não há como revogar", () => {
    expect(sePodeRevogar({ id: "x", nome: "X" })).toBe(true);
    expect(sePodeRevogar({ id: "", nome: "Só nome" })).toBe(false);
  });
});

// ====================================================================
// Multi-fornecedor: quem envia um processo para outra rede
// ====================================================================
describe("podePartilharProcesso", () => {
  it("é o MESMO conjunto do backend (PAPEIS_QUE_PARTILHAM)", async () => {
    const fs = await import("node:fs");
    const path = await import("node:path");
    const { PAPEIS_QUE_PARTILHAM } = await import("./partilhaProcesso");
    const fonte = fs.readFileSync(
      path.resolve(process.cwd(), "../backend/services/process_sharing_api.py"),
      "utf-8",
    );
    const bloco = fonte.match(/PAPEIS_QUE_PARTILHAM\s*=\s*\(([^)]*)\)/);
    // Contraprova: um leitor que não leu nada também «passaria» a igualdade vazia.
    expect(bloco).not.toBeNull();
    const doBackend = [...bloco[1].matchAll(/"([^"]+)"/g)].map((m) => m[1]).sort();
    expect(doBackend.length).toBeGreaterThanOrEqual(4);
    expect([...PAPEIS_QUE_PARTILHAM].sort()).toEqual(doBackend);
  });

  it("o consultor e a indexação não partilham", async () => {
    const { podePartilharProcesso } = await import("./partilhaProcesso");
    expect(podePartilharProcesso("administrativo")).toBe(true);
    expect(podePartilharProcesso(" Diretor ")).toBe(true);
    expect(podePartilharProcesso("consultor")).toBe(false);
    expect(podePartilharProcesso("indexacao")).toBe(false);
    expect(podePartilharProcesso(undefined)).toBe(false);
  });
});

describe("efeitoDaPartilha / nomeDoDestino", () => {
  it("descreve o que vai acontecer em cada caso", async () => {
    const { efeitoDaPartilha } = await import("./partilhaProcesso");
    expect(efeitoDaPartilha(null, false)).toBe("");
    expect(efeitoDaPartilha({ tem_index: true }, false)).toMatch(/fila de Index/i);
    expect(efeitoDaPartilha({ tem_index: true }, true)).toMatch(/Via Verde/);
    expect(efeitoDaPartilha({ tem_index: true }, true)).toMatch(/pela própria rede de destino/);
    expect(efeitoDaPartilha({ tem_index: true }, false)).toMatch(/a rede que decide quem o trata/);
    expect(efeitoDaPartilha({ tem_index: false }, true)).toMatch(/não tem equipa de Index/i);
    expect(efeitoDaPartilha({ tem_index: true, ja_partilhado: true }, false)).toMatch(/já está partilhado/i);
  });

  it("o nome do destino são as empresas; sem empresas, o id", async () => {
    const { nomeDoDestino } = await import("./partilhaProcesso");
    expect(nomeDoDestino({ empresas: ["A", "B"], network_id: "x" })).toBe("A / B");
    expect(nomeDoDestino({ empresas: {}, network_id: "x" })).toBe("x");
    expect(nomeDoDestino(null)).toBe("");
  });
});
