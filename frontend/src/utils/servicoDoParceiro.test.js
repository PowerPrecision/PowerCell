/**
 * «Serviço pago pelo parceiro» — as regras do cartão.
 *
 * As listas de papéis espelham as do servidor; uma cópia à mão diverge sem dar
 * erro e a divergência tem forma concreta (o botão aparece e o servidor
 * responde 403). Por isso este teste LÊ o Python.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import servicoPago from "@/test/fixtures/parceiro/servico_pago.json";
import servicoPorPagar from "@/test/fixtures/parceiro/servico_por_pagar.json";
import {
  LIMITE_DE_OBSERVACOES,
  PAPEIS_QUE_ALTERAM,
  PAPEIS_QUE_VEEM,
  corpoDaCaixa,
  corpoDasObservacoes,
  normalizarServico,
  observacoesMudaram,
  podeAlterarServicoDoParceiro,
  podeVerServicoDoParceiro,
  processoTemParceiro,
} from "./servicoDoParceiro";

const PY = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "backend", "services", "servico_do_parceiro.py"), "utf8");
const tuplo = (nome) => {
  const m = PY.match(new RegExp(`^${nome} = \\(([^)]*)\\)`, "m"));
  expect(m, `${nome} não encontrado no Python`).not.toBeNull();
  return [...m[1].matchAll(/"(\w+)"/g)].map((x) => x[1]);
};

describe("os papéis dizem o mesmo no Python e no JS", () => {
  it("quem vê", () => {
    const doPython = tuplo("PAPEIS_QUE_VEEM");
    expect(doPython.length).toBeGreaterThan(3); // contraprova: o leitor leu mesmo
    expect([...PAPEIS_QUE_VEEM].sort()).toEqual([...doPython].sort());
  });

  it("quem altera", () => {
    const doPython = tuplo("PAPEIS_QUE_ALTERAM");
    expect(doPython.length).toBeGreaterThan(3);
    expect([...PAPEIS_QUE_ALTERAM].sort()).toEqual([...doPython].sort());
  });
});

describe("quem vê e quem altera", () => {
  it("indexação, parceiro e desconhecidos não vêem", () => {
    for (const p of ["indexacao", "parceiro", "", undefined, null, "inventado"]) {
      expect(podeVerServicoDoParceiro(p)).toBe(false);
      expect(podeAlterarServicoDoParceiro(p)).toBe(false);
    }
  });

  it("consultor e intermediário vêem mas não alteram", () => {
    for (const p of ["consultor", "intermediario"]) {
      expect(podeVerServicoDoParceiro(p)).toBe(true);
      expect(podeAlterarServicoDoParceiro(p)).toBe(false);
    }
  });

  it("gestão e administrativo alteram (e o Master também)", () => {
    for (const p of ["master", "admin", "ceo", "diretor", "administrativo"]) {
      expect(podeAlterarServicoDoParceiro(p)).toBe(true);
    }
  });

  it("não distingue maiúsculas nem espaços", () => {
    expect(podeVerServicoDoParceiro(" Admin ")).toBe(true);
  });

  it("quem pode alterar também pode ver (nunca o contrário do que o servidor aceita)", () => {
    for (const p of PAPEIS_QUE_ALTERAM) expect(PAPEIS_QUE_VEEM).toContain(p);
  });
});

describe("processoTemParceiro", () => {
  it("só com parceiro atribuído (texto não vazio)", () => {
    expect(processoTemParceiro({ assigned_parceiro_id: "pt-1" })).toBe(true);
    for (const p of [{}, null, undefined, { assigned_parceiro_id: "" }, { assigned_parceiro_id: "  " }, { assigned_parceiro_id: null }]) {
      expect(processoTemParceiro(p)).toBe(false);
    }
  });
});

describe("normalizarServico (forma REAL do servidor)", () => {
  it("serviço pago", () => {
    const s = normalizarServico(servicoPago);
    expect(s).toMatchObject({
      aplicavel: true, pago: true, observacoes: "Transferência de 14/10\nRef. 8841",
      actualizadoPor: "Ana", podeAlterar: true, parceiro: { id: "pt-1", nome: "Rui" },
    });
    expect(s.pagoEm).toBe("2026-10-11T09:30:00+00:00");
  });

  it("serviço por pagar", () => {
    expect(normalizarServico(servicoPorPagar)).toMatchObject({ pago: false, pagoEm: null, observacoes: "" });
  });

  it("lixo dá a forma garantida, nunca rebenta e nunca concede", () => {
    for (const lixo of [null, undefined, "x", 3, [], { pago: "true", pode_alterar: "sim", aplicavel: 1 }]) {
      expect(normalizarServico(lixo)).toMatchObject({ aplicavel: false, pago: false, podeAlterar: false, observacoes: "" });
    }
  });
});

describe("corpos do PUT", () => {
  it("a caixa envia só `pago`, sempre booleano", () => {
    expect(corpoDaCaixa(true)).toEqual({ pago: true });
    expect(corpoDaCaixa("x")).toEqual({ pago: true });
    expect(corpoDaCaixa(undefined)).toEqual({ pago: false });
  });

  it("as observações enviam só `observacoes`, com tecto", () => {
    expect(corpoDasObservacoes("ok")).toEqual({ observacoes: "ok" });
    expect(corpoDasObservacoes("x".repeat(LIMITE_DE_OBSERVACOES + 50)).observacoes).toHaveLength(LIMITE_DE_OBSERVACOES);
    expect(corpoDasObservacoes(null)).toEqual({ observacoes: "" });
  });

  it("espaços nas pontas não contam como mudança", () => {
    expect(observacoesMudaram("  a ", "a")).toBe(false);
    expect(observacoesMudaram("a", "b")).toBe(true);
    expect(observacoesMudaram(null, "")).toBe(false);
  });
});
