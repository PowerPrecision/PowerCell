import { describe, expect, it } from "vitest";

import {
  convidaAJuntarMais,
  ficheirosEnviados,
  pedidosParaJuntarMais,
  quantidadeRecomendada,
  rotuloDoBotao,
  textoDoConvite,
} from "./pedidosDeDocumentos";

const recibos = (extra = {}) => ({ id: "r", suggested_count: 3, attached_files: [], ...extra });

describe("quantidade recomendada", () => {
  it("suggested_count vence o expected_count legado", () => {
    expect(quantidadeRecomendada({ suggested_count: 3, expected_count: 2 })).toBe(3);
    expect(quantidadeRecomendada({ expected_count: 2 })).toBe(2);
  });

  it("sem valor válido é 1 (nunca 0 nem NaN)", () => {
    expect(quantidadeRecomendada({})).toBe(1);
    expect(quantidadeRecomendada({ suggested_count: 0 })).toBe(1);
    expect(quantidadeRecomendada({ suggested_count: "abc" })).toBe(1);
    expect(quantidadeRecomendada(null)).toBe(1);
  });
});

describe("ficheiros enviados", () => {
  it("a lista manda sobre o contador", () => {
    expect(ficheirosEnviados({ attached_files: [{}, {}], uploaded_count: 9 })).toBe(2);
  });
  it("sem lista usa o contador", () => {
    expect(ficheirosEnviados({ uploaded_count: 2 })).toBe(2);
    expect(ficheirosEnviados({})).toBe(0);
  });
  it("uma lista que não é lista não conta (Array.isArray, nunca || [])", () => {
    expect(ficheirosEnviados({ attached_files: { 0: "x" }, uploaded_count: 1 })).toBe(1);
  });
});

describe("o convite a juntar mais", () => {
  it("pedido de 3 com 1 ficheiro convida", () => {
    const p = recibos({ attached_files: [{}] });
    expect(convidaAJuntarMais(p)).toBe(true);
    expect(textoDoConvite(p)).toBe("Pode juntar mais — recomendado: 3.");
    expect(rotuloDoBotao(p)).toBe("Adicionar mais");
  });

  it("sem ficheiros diz que pode enviar menos (não é obrigatório)", () => {
    expect(textoDoConvite(recibos())).toBe("Recomendado: 3 ficheiros — pode enviar menos.");
    expect(rotuloDoBotao(recibos())).toBe("Submeter");
  });

  it("com a recomendação atingida (ou ultrapassada) deixa de convidar", () => {
    expect(convidaAJuntarMais(recibos({ attached_files: [{}, {}, {}] }))).toBe(false);
    expect(convidaAJuntarMais(recibos({ attached_files: [{}, {}, {}, {}] }))).toBe(false);
    expect(textoDoConvite(recibos({ attached_files: [{}, {}, {}] }))).toBe("");
  });

  it("um pedido de 1 nunca convida", () => {
    expect(convidaAJuntarMais({ suggested_count: 1, attached_files: [{}] })).toBe(false);
    expect(convidaAJuntarMais({ attached_files: [] })).toBe(false);
  });

  it("a secção só lista os recebidos que convidam", () => {
    const lista = [
      recibos({ id: "a", attached_files: [{}] }),
      recibos({ id: "b", attached_files: [{}, {}, {}] }),
      { id: "c", attached_files: [{}] },
    ];
    expect(pedidosParaJuntarMais(lista).map((p) => p.id)).toEqual(["a"]);
    expect(pedidosParaJuntarMais(undefined)).toEqual([]);
  });
});
