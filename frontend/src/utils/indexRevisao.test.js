/**
 * Regras puras do ecrã do Index (Lote 12, Fase 4).
 *
 * A propriedade que mais importa: NADA do conteúdo da análise bloqueia «Marcar como Indexado».
 */
import { describe, expect, it } from "vitest";

import {
  alertasAbertos,
  camposARever,
  edicoesDeConfirmacao,
  edicoesDoTrabalho,
  empregadoresParaMarcar,
  eventoDoIndex,
  dataCurta,
  estadoDoFicheiroEmTexto,
  ficheiroPorLimpar,
  formatarDinheiro,
  formularioDoTrabalho,
  haJobActivo,
  mensagemDeErro,
  nifTemForma,
  normalizarBancada,
  normalizarFila,
  ordenarAlertas,
  podeMarcarComoIndexado,
  quantosPorLimpar,
  resumoDaAnalise,
  rotuloDoEstado,
  rotuloDoTipoDeAnalise,
  separadorValido,
  totalDeCamposARever,
  trabalhosSemNifConfirmado,
} from "./indexRevisao";

const campo = (value, extra = {}) => ({ value, needs_review: false, edited_by_human: false, ...extra });

function trabalho(extra = {}) {
  return {
    job_id: "job_a",
    employer_nif: campo("501964843"),
    employer_name: campo("Acme Lda"),
    job_title: campo(null, { needs_review: true }),
    net_salary: campo("1234.50"),
    contract_type: campo("efetivo"),
    period: "2026-09",
    ...extra,
  };
}

describe("separadores", () => {
  it("um separador desconhecido cai no por omissão, nunca num ecrã vazio", () => {
    expect(separadorValido("reviews")).toBe("reviews");
    expect(separadorValido("pending")).toBe("pending");
    expect(separadorValido("tudo")).toBe("pending");
    expect(separadorValido(null)).toBe("pending");
  });
});

describe("rotuloDoEstado", () => {
  it("diz «dispensado» só para o indexado por Via Verde", () => {
    expect(rotuloDoEstado("indexed", true)).toBe("Indexado (dispensado)");
    expect(rotuloDoEstado("indexed", false)).toBe("Indexado");
    expect(rotuloDoEstado("in_review")).toBe("Em tratamento");
    expect(rotuloDoEstado("???")).toBe("Por indexar");
  });
});

describe("«Marcar como Indexado» nunca é bloqueado pela análise", () => {
  const processo = { index_status: "pending" };

  it("com campos em dúvida, alertas e job activo continua permitido", () => {
    // a função nem recebe o conteúdo da análise: não o pode ler
    expect(podeMarcarComoIndexado({ processo, aMarcar: false })).toBe(true);
    expect(podeMarcarComoIndexado.length).toBe(1);
  });

  it("só o próprio pedido a decorrer ou o processo já indexado o desligam", () => {
    expect(podeMarcarComoIndexado({ processo, aMarcar: true })).toBe(false);
    expect(podeMarcarComoIndexado({ processo: { index_status: "indexed" }, aMarcar: false })).toBe(false);
    expect(podeMarcarComoIndexado({ processo: null, aMarcar: false })).toBe(false);
    expect(podeMarcarComoIndexado({ processo: { index_status: "in_review" }, aMarcar: false })).toBe(true);
  });
});

describe("campos a rever", () => {
  it("conta só os campos marcados `needs_review`", () => {
    expect(camposARever(trabalho())).toEqual(["job_title"]);
    expect(totalDeCamposARever([trabalho(), trabalho({ job_id: "b", employer_name: campo(null, { needs_review: true }) })])).toBe(3);
  });

  it("tolera lixo do servidor sem rebentar", () => {
    expect(camposARever(null)).toEqual([]);
    expect(camposARever({})).toEqual([]);
    expect(totalDeCamposARever({ jobs: [] })).toBe(0);
  });
});

describe("edições: só o que MUDOU", () => {
  it("sem alterações não envia nada (reenviar repunha o valor antigo)", () => {
    expect(edicoesDoTrabalho(trabalho(), formularioDoTrabalho(trabalho()))).toEqual({});
  });

  it("envia só os campos tocados", () => {
    const t = trabalho();
    const form = { ...formularioDoTrabalho(t), job_title: "Analista" };
    expect(edicoesDoTrabalho(t, form)).toEqual({ job_title: "Analista" });
  });

  it("apagar um campo envia null (apagou de propósito)", () => {
    const t = trabalho();
    expect(edicoesDoTrabalho(t, { ...formularioDoTrabalho(t), employer_name: "  " })).toEqual({ employer_name: null });
  });

  it("espaços à volta não contam como alteração", () => {
    const t = trabalho();
    expect(edicoesDoTrabalho(t, { ...formularioDoTrabalho(t), employer_name: " Acme Lda " })).toEqual({});
  });

  it("o texto do formulário é texto: um 0 não desaparece", () => {
    const t = trabalho({ net_salary: campo(0) });
    expect(formularioDoTrabalho(t).net_salary).toBe("0");
  });

  it("confirmar reenvia o valor actual dos campos em dúvida", () => {
    expect(edicoesDeConfirmacao(trabalho(), ["job_title", "employer_name"])).toEqual({
      job_title: null,
      employer_name: "Acme Lda",
    });
  });
});

describe("NIFs ao marcar", () => {
  it("só pergunta pelos trabalhos sem NIF ou com NIF em dúvida não confirmado", () => {
    const semNif = trabalho({ job_id: "a", employer_nif: campo(null, { needs_review: true }) });
    const duvida = trabalho({ job_id: "b", employer_nif: campo("123", { needs_review: true }) });
    const confirmado = trabalho({ job_id: "c", employer_nif: campo("501964843", { needs_review: true, edited_by_human: true }) });
    const bom = trabalho({ job_id: "d" });
    expect(trabalhosSemNifConfirmado([semNif, duvida, confirmado, bom]).map((t) => t.job_id)).toEqual(["a", "b"]);
  });

  it("o corpo só leva NIFs com forma de NIF, só dígitos", () => {
    expect(
      empregadoresParaMarcar({ a: "501 964 843", b: "123", c: "", d: "abc" }),
    ).toEqual([{ job_id: "a", nif: "501964843" }]);
    expect(empregadoresParaMarcar(null)).toEqual([]);
  });

  it("nifTemForma", () => {
    expect(nifTemForma("501964843")).toBe(true);
    expect(nifTemForma("50196484")).toBe(false);
    expect(nifTemForma(null)).toBe(false);
  });
});

describe("alertas", () => {
  const alertas = [
    { id: "1", severity: "info", dismissed: false },
    { id: "2", severity: "alerta", dismissed: true },
    { id: "3", severity: "alerta", dismissed: false },
    { id: "4", severity: "aviso", dismissed: false },
  ];

  it("abertos primeiro, do mais grave ao menos grave; dispensados no fim", () => {
    expect(ordenarAlertas(alertas).map((a) => a.id)).toEqual(["3", "4", "1", "2"]);
  });

  it("não altera a lista original", () => {
    const copia = JSON.stringify(alertas);
    ordenarAlertas(alertas);
    expect(JSON.stringify(alertas)).toBe(copia);
  });

  it("conta os abertos", () => {
    expect(alertasAbertos(alertas)).toHaveLength(3);
  });
});

describe("a forma dos dados do servidor normaliza-se UMA vez", () => {
  it("fila: `|| []` não chega — um objecto é truthy", () => {
    expect(normalizarFila({ items: { a: 1 }, total: 3 }).itens).toEqual([]);
    expect(normalizarFila({ items: [{ id: "x" }] }).total).toBe(1);
    expect(normalizarFila(undefined)).toEqual({ itens: [], total: 0, pagina: 1, tamanho: 0 });
  });

  it("bancada: listas que não o são viram listas", () => {
    const b = normalizarBancada({
      process: { id: "p" },
      files: "x",
      professional_metadata: { jobs: { a: 1 }, has_pending_review: true },
      alerts: null,
      active_jobs: { analysis: "t-1" },
    });
    expect(b.ficheiros).toEqual([]);
    expect(b.trabalhos).toEqual([]);
    expect(b.alertas).toEqual([]);
    expect(b.temRevisaoPendente).toBe(true);
    expect(b.jobsActivos).toEqual({ analysis: "t-1", finalize: null, sanitize: null });
  });

  it("bancada vazia não rebenta", () => {
    expect(normalizarBancada(null).processo).toBeNull();
  });
});

describe("jobs e eventos", () => {
  it("haJobActivo", () => {
    expect(haJobActivo({ analysis: null, finalize: null, sanitize: null })).toBe(false);
    expect(haJobActivo({ analysis: null, finalize: "t", sanitize: null })).toBe(true);
    expect(haJobActivo(null)).toBe(false);
  });

  it("só os eventos de jobs do Index deste processo contam", () => {
    expect(eventoDoIndex({ task_type: "INDEX_ANALYSIS", process_id: "p1" }, "p1")).toBe(true);
    expect(eventoDoIndex({ task_type: "INDEX_FINALIZE", process_id: "p2" }, "p1")).toBe(false);
    expect(eventoDoIndex({ task_type: "VOICE_NOTE", process_id: "p1" }, "p1")).toBe(false);
    expect(eventoDoIndex({ task_type: "INDEX_SANITIZE", process_id: "p9" })).toBe(true);
    expect(eventoDoIndex(null, "p1")).toBe(false);
  });
});

describe("apresentação", () => {
  it("dinheiro: zero é um valor, ausente é «—»", () => {
    expect(formatarDinheiro(0)).toMatch(/0,00/);
    expect(formatarDinheiro(null)).toBe("—");
    expect(formatarDinheiro("abc")).toBe("—");
    expect(formatarDinheiro("1234.5")).toMatch(/1\s?234,50/);
  });

  it("a mensagem de erro é a do servidor, nunca a de uma excepção", () => {
    expect(mensagemDeErro({ response: { data: { detail: "Valor inválido." } } })).toBe("Valor inválido.");
    expect(mensagemDeErro(new Error("ECONNRESET at 10.0.0.1"))).toBe("Não foi possível concluir o pedido.");
    expect(mensagemDeErro({ response: { data: { detail: { x: 1 } } } })).toBe("Não foi possível concluir o pedido.");
  });

  it("o resumo é só números", () => {
    expect(resumoDaAnalise({ analisados: 2, saltados: 1, alertas: 3, campos_a_rever: 4 })).toBe(
      "2 analisado(s); 1 já analisado(s); 3 alerta(s); 4 campo(s) a rever",
    );
    expect(resumoDaAnalise(null)).toBe("");
  });
});

describe("PDF limpo: o que está por limpar e o que o ecrã diz", () => {
  const base = { id: "d", uploaded_by_index: true, file_state: "original", has_clean_pdf: false, is_clean_pdf: false };

  it("só conta o que o Index carregou e ainda não tem PDF limpo", () => {
    expect(ficheiroPorLimpar(base)).toBe(true);
    expect(ficheiroPorLimpar({ ...base, uploaded_by_index: false })).toBe(false);
    expect(ficheiroPorLimpar({ ...base, uploaded_by_index: undefined })).toBe(false);
    expect(ficheiroPorLimpar({ ...base, file_state: "sanitizado" })).toBe(false);
    expect(ficheiroPorLimpar({ ...base, has_clean_pdf: true })).toBe(false);
    expect(ficheiroPorLimpar({ ...base, is_clean_pdf: true })).toBe(false);
    expect(ficheiroPorLimpar(null)).toBe(false);
  });

  it("um ficheiro sem file_state conta como original", () => {
    const { file_state, ...semEstado } = base;
    expect(file_state).toBe("original");
    expect(ficheiroPorLimpar(semEstado)).toBe(true);
  });

  it("quantosPorLimpar tolera o que não é lista", () => {
    expect(quantosPorLimpar([base, base, { ...base, uploaded_by_index: false }])).toBe(2);
    expect(quantosPorLimpar({ a: 1 })).toBe(0);
  });

  it("a data de eliminação do original vê-se, em dd/mm/aaaa", () => {
    expect(dataCurta("2026-11-20T12:00:00+00:00")).toBe("20/11/2026");
    expect(dataCurta("lixo")).toBeNull();
    expect(dataCurta(null)).toBeNull();
    expect(estadoDoFicheiroEmTexto({ file_state: "sanitizado", purge_after: "2026-11-20T12:00:00+00:00" })).toBe(
      "Tem PDF limpo — o original é eliminado a partir de 20/11/2026",
    );
    expect(estadoDoFicheiroEmTexto({ file_state: "sanitizado" })).toBe("Tem PDF limpo");
    expect(estadoDoFicheiroEmTexto({ is_clean_pdf: true })).toBe("PDF limpo (sem metadados)");
    expect(estadoDoFicheiroEmTexto({ file_state: "original" })).toBeNull();
    expect(estadoDoFicheiroEmTexto(null)).toBeNull();
  });
});

describe("rotuloDoTipoDeAnalise", () => {
  it("dá nome a todos os tipos que o servidor analisa, a declaração de efetividade incluída", () => {
    expect(rotuloDoTipoDeAnalise("declaracao_efetividade")).toBe("Declaração de efetividade");
    expect(rotuloDoTipoDeAnalise("recibo_vencimento")).toBe("Recibo de vencimento");
    expect(rotuloDoTipoDeAnalise("extrato_bancario")).toBe("Extrato bancário");
    expect(rotuloDoTipoDeAnalise("identificacao")).toBe("Identificação");
  });

  it("um tipo desconhecido não tem rótulo (o ecrã não inventa)", () => {
    expect(rotuloDoTipoDeAnalise("contrato")).toBeNull();
    expect(rotuloDoTipoDeAnalise(undefined)).toBeNull();
  });
});
