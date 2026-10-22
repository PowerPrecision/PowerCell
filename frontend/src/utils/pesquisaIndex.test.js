import { describe, expect, it } from "vitest";

import {
  FILTROS_VAZIOS,
  camposDoTipo,
  chaveDaPesquisa,
  dataDeAdmissao,
  documentosDoResultado,
  filtrosDoUrl,
  filtrosParaPedido,
  filtrosParaUrl,
  haPesquisaNoUrl,
  normalizarFiltros,
  normalizarResultado,
  numeroDoTexto,
  paginaDoUrl,
  rotuloDoDocumento,
  validarFiltros,
} from "./pesquisaIndex";

const com = (extra) => ({ ...FILTROS_VAZIOS, ...extra });

describe("camposDoTipo — a mesma tabela do servidor", () => {
  it("o banco só existe nos extratos", () => {
    expect(camposDoTipo("extrato")).toContain("bank");
    for (const tipo of ["", "recibo", "declaracao_efetividade"]) expect(camposDoTipo(tipo)).not.toContain("bank");
  });

  it("o salário só existe nos recibos e por emprego", () => {
    expect(camposDoTipo("recibo")).toContain("min_salary");
    expect(camposDoTipo("")).toContain("min_salary");
    expect(camposDoTipo("declaracao_efetividade")).not.toContain("min_salary");
    expect(camposDoTipo("extrato")).not.toContain("min_salary");
  });

  it("um extrato não tem entidade nem contrato", () => {
    const extrato = camposDoTipo("extrato");
    for (const campo of ["employer_name", "employer_nif", "employer_location", "contract_type", "job_title"]) {
      expect(extrato).not.toContain(campo);
    }
  });

  it("um tipo desconhecido cai na vista por emprego", () => {
    expect(camposDoTipo("contrato")).toEqual(camposDoTipo(""));
  });
});

describe("filtrosParaPedido", () => {
  it("só leva os campos do tipo: um banco escrito antes de mudar para recibos não segue", () => {
    const pedido = filtrosParaPedido(com({ document_type: "recibo", bank: "CGD", min_salary: "1200" }));
    expect(pedido).toEqual({ document_type: "recibo", min_salary: 1200, size: 25 });
  });

  it("o inverso: mudar para extrato descarta o salário e a entidade", () => {
    const pedido = filtrosParaPedido(com({ document_type: "extrato", bank: " CGD ", min_salary: "900", employer_name: "Empresa" }));
    expect(pedido).toEqual({ document_type: "extrato", bank: "CGD", size: 25 });
  });

  it("o valor exacto são os dois limites iguais, com vírgula à portuguesa", () => {
    const pedido = filtrosParaPedido(com({ document_type: "recibo", min_salary: "1.234,56", max_salary: "1234,56" }));
    expect(pedido.min_salary).toBe(1234.56);
    expect(pedido.max_salary).toBe(1234.56);
  });

  it("o zero é um valor (não um campo por preencher)", () => {
    expect(filtrosParaPedido(com({ document_type: "recibo", min_salary: "0" })).min_salary).toBe(0);
  });

  it("filtros vazios não vão; sem tipo não há document_type", () => {
    expect(filtrosParaPedido(FILTROS_VAZIOS)).toEqual({ size: 25 });
  });

  it("contratos vão como lista e a página só quando não é a primeira", () => {
    const pedido = filtrosParaPedido(com({ contract_type: ["efetivo", "outro"] }), { pagina: 3, tamanho: 10 });
    expect(pedido).toEqual({ contract_type: ["efetivo", "outro"], page: 3, size: 10 });
  });

  it("um número ilegível não vai (nem vira NaN no URL)", () => {
    expect(filtrosParaPedido(com({ document_type: "recibo", min_salary: "abc" }))).toEqual({ document_type: "recibo", size: 25 });
  });
});

describe("numeroDoTexto", () => {
  it.each([["1234", 1234], ["1234.5", 1234.5], ["1234,5", 1234.5], ["1.234,56", 1234.56], [" 900 ", 900]])("%s → %s", (t, n) => {
    expect(numeroDoTexto(t)).toBe(n);
  });
  it.each(["abc", "12,3,4", "-5", "1e3"])("%s não é um número", (t) => expect(Number.isNaN(numeroDoTexto(t))).toBe(true));
  it("vazio é «sem filtro», não zero", () => expect(numeroDoTexto("  ")).toBeNull());
});

describe("validarFiltros — o que o servidor também recusaria", () => {
  it("mínimo acima do máximo", () => {
    expect(validarFiltros(com({ document_type: "recibo", min_salary: "2000", max_salary: "1000" })).max_salary).toMatch(/inferior/);
  });
  it("mínimo igual ao máximo é um valor exacto, não um erro", () => {
    expect(validarFiltros(com({ document_type: "recibo", min_salary: "1200", max_salary: "1200" }))).toEqual({});
  });
  it("período fora do formato e invertido", () => {
    expect(validarFiltros(com({ period_from: "09/2026" })).period_from).toBeTruthy();
    expect(validarFiltros(com({ period_from: "2026-09", period_to: "2026-01" })).period_to).toBeTruthy();
  });
  it("texto curto demais e NIF com menos de 3 dígitos", () => {
    expect(validarFiltros(com({ document_type: "extrato", bank: "x" })).bank).toBeTruthy();
    expect(validarFiltros(com({ employer_nif: "12" })).employer_nif).toBeTruthy();
  });
  it("não valida o que o tipo nem mostra (um salário inválido escondido não bloqueia um extrato)", () => {
    expect(validarFiltros(com({ document_type: "extrato", min_salary: "abc", bank: "cgd" }))).toEqual({});
  });
});

describe("o URL", () => {
  it("ida e volta", () => {
    const f = com({ document_type: "extrato", bank: "CGD", period_from: "2026-01" });
    const params = filtrosParaUrl(new URLSearchParams(), f, 2);
    expect(filtrosDoUrl(params)).toEqual(normalizarFiltros(f));
    expect(paginaDoUrl(params)).toBe(2);
    expect(haPesquisaNoUrl(params)).toBe(true);
  });

  it("uma pesquisa sem filtros também é uma pesquisa (listar tudo)", () => {
    const params = filtrosParaUrl(new URLSearchParams(), FILTROS_VAZIOS);
    expect(haPesquisaNoUrl(params)).toBe(true);
  });

  it("sem marca não há pesquisa", () => {
    expect(haPesquisaNoUrl(new URLSearchParams("ps_banco=cgd"))).toBe(false);
  });

  it("não pisa os parâmetros que não são nossos e substitui os nossos", () => {
    const anterior = new URLSearchParams("outro=1&ps_banco=velho&ps_tipo=extrato&ps_p=4");
    const seguinte = filtrosParaUrl(anterior, com({ document_type: "recibo", min_salary: "900" }), 1);
    expect(seguinte.get("outro")).toBe("1");
    expect(seguinte.get("ps_banco")).toBeNull();
    expect(seguinte.get("ps_p")).toBeNull();
    expect(seguinte.get("ps_tipo")).toBe("recibo");
    expect(seguinte.get("ps_min")).toBe("900");
  });

  it("o URL só leva os campos do tipo", () => {
    const params = filtrosParaUrl(new URLSearchParams(), com({ document_type: "extrato", bank: "CGD", min_salary: "5" }));
    expect(params.get("ps_min")).toBeNull();
  });

  it("valores escritos à mão e ilegíveis caem na omissão", () => {
    const f = filtrosDoUrl(new URLSearchParams("ps_tipo=contrato&ps_contrato=efetivo,xpto&ps_p=abc"));
    expect(f.document_type).toBe("");
    expect(f.contract_type).toEqual(["efetivo"]);
    expect(paginaDoUrl(new URLSearchParams("ps_p=abc"))).toBe(1);
    expect(paginaDoUrl(new URLSearchParams("ps_p=0"))).toBe(1);
  });
});

describe("normalizarResultado — a forma lê-se uma vez", () => {
  it("um objecto onde devia estar a lista não rebenta", () => {
    expect(normalizarResultado({ items: { a: 1 }, total: 3 }).itens).toEqual([]);
    expect(normalizarResultado(null).itens).toEqual([]);
    expect(normalizarResultado(undefined).vista).toBe("jobs");
  });
  it("lê a vista e o total do servidor", () => {
    const r = normalizarResultado({ view: "documents", items: [{ a: 1 }, null, "x"], total: 41, page: 2, size: 25 });
    expect(r).toMatchObject({ vista: "documents", total: 41, pagina: 2, tamanho: 25 });
    expect(r.itens).toEqual([{ a: 1 }]);
  });
});

describe("documentosDoResultado — a referência exacta do «Ver documento»", () => {
  it("por documento é UM, com um rótulo que só usa o que veio", () => {
    const item = { document_id: "d1", document_type: "extrato", bank: "Caixa Geral de Depósitos", period: "2026-09", process_id: "p" };
    expect(documentosDoResultado(item, "documents")).toEqual([{ id: "d1", rotulo: "Extrato · Caixa Geral de Depósitos · 2026-09" }]);
  });
  it("sem referência não há botão (nem na vista por documento nem por emprego)", () => {
    expect(documentosDoResultado({ document_type: "recibo" }, "documents")).toEqual([]);
    expect(documentosDoResultado({ document_id: "" }, "documents")).toEqual([]);
    expect(documentosDoResultado({ document_ids: [] }, "jobs")).toEqual([]);
    expect(documentosDoResultado({}, "jobs")).toEqual([]);
    expect(documentosDoResultado(null, "jobs")).toEqual([]);
  });
  it("por emprego são os que o sustentam, numerados", () => {
    const docs = documentosDoResultado({ document_ids: ["a", "b", 7, ""], employer: { name: "Empresa Lda" } }, "jobs");
    expect(docs.map((d) => d.id)).toEqual(["a", "b"]);
    expect(docs[1].rotulo).toBe("Documento 2 de 2 · Empresa Lda");
  });
  it("o rótulo de uma declaração leva a entidade", () => {
    expect(rotuloDoDocumento({ document_type: "declaracao_efetividade", employer: { name: "Boa, Lda" }, period: "2026-10" }))
      .toBe("Declaração de efetividade · Boa, Lda · 2026-10");
  });
});

describe("pequenas coisas", () => {
  it("a data de admissão lê-se à portuguesa", () => {
    expect(dataDeAdmissao("2021-05-03")).toBe("03/05/2021");
    expect(dataDeAdmissao(null)).toBe("—");
    expect(dataDeAdmissao("03/05/2021")).toBe("—");
  });
  it("a chave da consulta não depende da ordem das chaves", () => {
    expect(chaveDaPesquisa({ a: 1, b: 2 })).toBe(chaveDaPesquisa({ b: 2, a: 1 }));
    expect(chaveDaPesquisa({ a: 1 })).not.toBe(chaveDaPesquisa({ a: 2 }));
  });
});
