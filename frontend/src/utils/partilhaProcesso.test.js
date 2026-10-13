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
    expect(res).toEqual([{
      id: "cmp-domus", nome: "Domus", desde: "2026-10-09T10:00:00Z",
      // Sem linhagem (servidor antigo) não se sabe de quem veio nem se se pode retirar.
      partilhadoPor: null, podeRevogar: null,
    }]);
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


describe("parceirosDoProcesso com a cadeia (linhagem do servidor)", () => {
  const processo = {
    partner_companies: [
      { company_id: "cmp-z", company_name: "Empresa Z", added_at: "2026-10-01T10:00:00Z" },
      { company_id: "cmp-w", company_name: "Empresa W", added_at: "2026-10-02T10:00:00Z" },
    ],
    linhagem: {
      partilhas: [
        { company_id: "cmp-z", nome: "Empresa Z", partilhado_por: "Empresa Y", nivel: 2, pode_revogar: false },
        { company_id: "cmp-w", nome: "Empresa W", partilhado_por: "Empresa Z", nivel: 3, pode_revogar: true },
      ],
    },
  };

  it("cada elo traz de quem veio e se o utilizador o pode retirar", () => {
    const [z, w] = parceirosDoProcesso(processo);
    expect(z).toMatchObject({ nome: "Empresa Z", partilhadoPor: "Empresa Y", podeRevogar: false });
    expect(w).toMatchObject({ nome: "Empresa W", partilhadoPor: "Empresa Z", podeRevogar: true });
  });

  it("o botão não se desenha para o elo que o servidor diz que não é meu", () => {
    const [z, w] = parceirosDoProcesso(processo);
    expect(sePodeRevogar(z)).toBe(false);
    expect(sePodeRevogar(w)).toBe(true);
  });

  it("sem a informação do servidor o botão continua a depender só de haver id", () => {
    const [semInfo] = parceirosDoProcesso({ partner_companies: processo.partner_companies });
    expect(sePodeRevogar(semInfo)).toBe(true);
  });

  it("só o booleano estrito do servidor conta; texto vira «não sei»", () => {
    const [p] = parceirosDoProcesso({
      partner_companies: [{ company_id: "cmp-z", company_name: "Z" }],
      linhagem: { partilhas: [{ company_id: "cmp-z", pode_revogar: "false", partilhado_por: "  " }] },
    });
    expect(p.podeRevogar).toBeNull();
    expect(p.partilhadoPor).toBeNull();
    expect(sePodeRevogar(p)).toBe(true);
  });

  it("uma linhagem com a forma errada não rebenta (Array.isArray)", () => {
    expect(() => parceirosDoProcesso({
      partner_companies: [{ company_id: "a", company_name: "A" }],
      linhagem: { partilhas: { 0: {} } },
    })).not.toThrow();
  });
});
