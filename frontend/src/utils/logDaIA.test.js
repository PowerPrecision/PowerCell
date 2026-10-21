import { describe, expect, it } from "vitest";

import {
  FILTROS,
  conclusaoDaLinha,
  formatarQuando,
  gatilhoDaLinha,
  linhaPodeSerReanalisada,
  mensagemDaReanalise,
  normalizarPagina,
  notaDaLinha,
  rotuloDoEstado,
  tituloDaLinha,
} from "./logDaIA";

describe("estado e título", () => {
  it("traduz os três estados e não inventa um quarto", () => {
    expect(rotuloDoEstado("sucesso")).toBe("Sucesso");
    expect(rotuloDoEstado("falha")).toBe("Falhou");
    expect(rotuloDoEstado("saltado")).toBe("Não executada");
    expect(rotuloDoEstado("talvez")).toBe("—");
  });

  it("o título leva a acção e o ficheiro", () => {
    expect(tituloDaLinha({ accao_rotulo: "Documento classificado", ficheiro: "cc.pdf" }))
      .toBe("Documento classificado — cc.pdf");
    expect(tituloDaLinha({ accao_rotulo: "Documento classificado" })).toBe("Documento classificado");
    expect(tituloDaLinha({})).toBe("Acção da IA");
  });

  it("os filtros começam em «sem filtro»", () => {
    expect(FILTROS[0].valor).toBe("");
    expect(FILTROS.map((f) => f.valor)).toEqual(["", "sucesso", "falha", "saltado"]);
  });
});

describe("conclusão da linha", () => {
  it("mostra categoria e confiança em percentagem", () => {
    expect(conclusaoDaLinha({ estado: "sucesso", categoria: "Identificação", confianca: 0.934 }))
      .toBe("Identificação · 93 %");
  });

  it("uma confiança já em 0–100 não se multiplica outra vez", () => {
    expect(conclusaoDaLinha({ estado: "sucesso", categoria: "IRS", confianca: 88 })).toBe("IRS · 88 %");
  });

  it("sem confiança mostra só a categoria", () => {
    expect(conclusaoDaLinha({ estado: "sucesso", categoria: "IRS" })).toBe("IRS");
  });

  it("uma confiança ZERO é um valor, não uma ausência", () => {
    expect(conclusaoDaLinha({ estado: "sucesso", categoria: "Outros", confianca: 0 })).toBe("Outros · 0 %");
  });

  it("uma falha ou um salto não têm conclusão", () => {
    expect(conclusaoDaLinha({ estado: "falha", categoria: "IRS", confianca: 0.9 })).toBe("");
    expect(conclusaoDaLinha({ estado: "saltado", categoria: "IRS" })).toBe("");
  });
});

describe("nota da linha", () => {
  it("usa a mensagem do servidor", () => {
    expect(notaDaLinha({ estado: "falha", motivo: "limite_do_fornecedor", motivo_mensagem: "Tente mais tarde." }))
      .toBe("Tente mais tarde.");
  });

  it("uma falha sem mensagem nunca fica muda — e nunca mostra o código", () => {
    const nota = notaDaLinha({ estado: "falha", motivo: "erro_da_ia" });
    expect(nota).toMatch(/não conseguiu/i);
    expect(nota).not.toContain("erro_da_ia");
  });

  it("um sucesso sem aviso não tem nota", () => {
    expect(notaDaLinha({ estado: "sucesso" })).toBe("");
  });
});

describe("gatilho", () => {
  it("manual leva o nome de quem carregou", () => {
    expect(gatilhoDaLinha({ gatilho: "manual", utilizador_nome: "Diana" })).toBe("Manual — Diana");
    expect(gatilhoDaLinha({ gatilho: "manual" })).toBe("Manual");
  });

  it("automático diz a origem quando a conhece", () => {
    expect(gatilhoDaLinha({ gatilho: "automatico", origem: "portal" })).toBe("Automático (Portal do cliente)");
    expect(gatilhoDaLinha({ gatilho: "automatico" })).toBe("Automático");
    expect(gatilhoDaLinha({ gatilho: "automatico", origem: "inventada" })).toBe("Automático");
  });
});

describe("reanalisar", () => {
  it("só linhas de classificação/revisão com documento", () => {
    expect(linhaPodeSerReanalisada({ accao: "categorizar", documento_id: "d1" })).toBe(true);
    expect(linhaPodeSerReanalisada({ accao: "rever", documento_id: "d1" })).toBe(true);
    expect(linhaPodeSerReanalisada({ accao: "categorizar" })).toBe(false);
    // A análise em lote e a extracção partem de ficheiros enviados, sem documento a que voltar.
    expect(linhaPodeSerReanalisada({ accao: "analisar", documento_id: "d1" })).toBe(false);
    expect(linhaPodeSerReanalisada({ accao: "extrair_dados", documento_id: "d1" })).toBe(false);
  });

  it("mensagens do resultado", () => {
    expect(mensagemDaReanalise({ success: true, auto_approved: true, confidence_score: 91 }))
      .toEqual({ tipo: "sucesso", texto: expect.stringContaining("91 %") });
    expect(mensagemDaReanalise({ success: true, auto_approved: false, confidence_score: 60 }).tipo).toBe("info");
    expect(mensagemDaReanalise({ success: false, error: "Erro na categorização IA: X" }).tipo).toBe("erro");
    expect(mensagemDaReanalise(undefined).tipo).toBe("erro");
  });

  it("a mensagem de erro nunca repete o texto técnico do servidor", () => {
    expect(mensagemDaReanalise({ success: false, error: "Incorrect API key sk-123" }).texto).not.toContain("sk-123");
  });
});

describe("normalizar a página", () => {
  it("lê a forma real do servidor", () => {
    const p = normalizarPagina({ items: [{ id: 1 }], total: 61, page: 2, size: 30, pode_reanalisar: true });
    expect(p).toMatchObject({ total: 61, page: 2, size: 30, paginas: 3, podeReanalisar: true });
  });

  it("sobrevive a respostas fora da forma (Array.isArray, nunca || [])", () => {
    expect(normalizarPagina(undefined).items).toEqual([]);
    expect(normalizarPagina({ items: { 0: "x" } }).items).toEqual([]);
    expect(normalizarPagina({ items: "texto" }).items).toEqual([]);
    expect(normalizarPagina(null).paginas).toBe(1);
  });

  it("só um true ESTRITO abre a reanálise", () => {
    expect(normalizarPagina({ pode_reanalisar: "true" }).podeReanalisar).toBe(false);
    expect(normalizarPagina({}).podeReanalisar).toBe(false);
  });
});

describe("data", () => {
  it("formata em pt-PT na hora de Lisboa", () => {
    expect(formatarQuando("2026-10-21T13:07:00+00:00")).toContain("14:07");
  });

  it("texto inválido não vira «Invalid Date»", () => {
    expect(formatarQuando("não é data")).toBe("—");
    expect(formatarQuando(null)).toBe("—");
  });
});
