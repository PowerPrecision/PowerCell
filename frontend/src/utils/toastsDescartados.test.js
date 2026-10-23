import { beforeEach, describe, expect, it } from "vitest";

import { criarRegistoDeToastsDescartados } from "./toastsDescartados";

function armazenamentoFalso(inicial = {}) {
  const dados = { ...inicial };
  return {
    getItem: (k) => (k in dados ? dados[k] : null),
    setItem: (k, v) => { dados[k] = String(v); },
    dados,
  };
}

describe("registo de toasts descartados", () => {
  let armazenamento;
  beforeEach(() => { armazenamento = armazenamentoFalso(); });

  it("um id fechado pelo utilizador fica descartado", () => {
    const r = criarRegistoDeToastsDescartados(armazenamento);
    expect(r.foiDescartado("a")).toBe(false);
    expect(r.aoFechar("a")).toBe("utilizador");
    expect(r.foiDescartado("a")).toBe(true);
  });

  it("um fecho do CÓDIGO não conta como descarte (o tecto de cinco toasts não apaga a tarefa para sempre)", () => {
    const r = criarRegistoDeToastsDescartados(armazenamento);
    r.prepararFechoNosso("a");
    expect(r.aoFechar("a")).toBe("nosso");
    expect(r.foiDescartado("a")).toBe(false);
  });

  it("o fecho nosso só vale uma vez: o seguinte é do utilizador", () => {
    const r = criarRegistoDeToastsDescartados(armazenamento);
    r.prepararFechoNosso("a");
    r.aoFechar("a");
    expect(r.aoFechar("a")).toBe("utilizador");
  });

  it("recriar o toast esquece um fecho nosso que nunca chegou", () => {
    const r = criarRegistoDeToastsDescartados(armazenamento);
    r.prepararFechoNosso("a");
    r.aoCriar("a");
    expect(r.aoFechar("a")).toBe("utilizador");
  });

  it("sobrevive a um registo novo sobre o mesmo armazenamento (recarregamento)", () => {
    criarRegistoDeToastsDescartados(armazenamento).aoFechar("a");
    expect(criarRegistoDeToastsDescartados(armazenamento).foiDescartado("a")).toBe(true);
  });

  it("esquecer o descarte permite um aviso novo", () => {
    const r = criarRegistoDeToastsDescartados(armazenamento);
    r.aoFechar("a");
    r.esquecerDescarte("a");
    expect(r.foiDescartado("a")).toBe(false);
    expect(criarRegistoDeToastsDescartados(armazenamento).foiDescartado("a")).toBe(false);
  });

  it("o armazenamento tem tecto (200 ids): os mais antigos saem", () => {
    const r = criarRegistoDeToastsDescartados(armazenamento);
    for (let i = 0; i < 250; i += 1) r.marcarDescartado(`id-${i}`);
    expect(r.foiDescartado("id-0")).toBe(false);
    expect(r.foiDescartado("id-249")).toBe(true);
    expect(JSON.parse(armazenamento.dados["powercell.toasts.descartados"])).toHaveLength(200);
  });

  it("lixo no armazenamento não rebenta", () => {
    for (const lixo of ["{", "null", '{"a":1}', "[1,2]"]) {
      const r = criarRegistoDeToastsDescartados(armazenamentoFalso({ "powercell.toasts.descartados": lixo }));
      expect(r.foiDescartado("a")).toBe(false);
    }
  });

  it("sem armazenamento funciona em memória", () => {
    const r = criarRegistoDeToastsDescartados(null);
    r.aoFechar("a");
    expect(r.foiDescartado("a")).toBe(true);
  });

  it("um armazenamento que lança ao escrever não impede de marcar", () => {
    const r = criarRegistoDeToastsDescartados({ getItem: () => null, setItem: () => { throw new Error("cheio"); } });
    expect(() => r.aoFechar("a")).not.toThrow();
    expect(r.foiDescartado("a")).toBe(true);
  });
});
