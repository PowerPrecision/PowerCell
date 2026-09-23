/**
 * Preparação da revisão de uma extracção — Épico 9, Eixo 4.
 *
 * Esta é a decisão que a regra de ouro do épico protege. Dentro do
 * `ProcessDetails` (2900 linhas) não se conseguia testar; aqui sim.
 *
 * O caso que dá nome ao ficheiro: uma extracção SEM conflitos não é uma
 * extracção sem consequências. Sem conflitos significa que a ficha está
 * vazia e que TUDO o que a IA leu vai entrar. Era exactamente aí que o
 * caminho em lote gravava sozinho.
 */
import { describe, expect, it } from "vitest";

import {
  aplicarDecisaoNaRevisao,
  prepararRevisaoDaExtraccao,
} from "./documentExtraction";

describe("prepararRevisaoDaExtraccao — quando não há nada a rever", () => {
  it("sem argumentos devolve null", () => {
    expect(prepararRevisaoDaExtraccao()).toBeNull();
  });

  it("sem dados extraídos devolve null", () => {
    expect(prepararRevisaoDaExtraccao({ extractedData: null })).toBeNull();
  });

  it("dados extraídos vazios devolvem null", () => {
    // Abrir um diálogo de revisão vazio é pior do que dizer que não deu.
    expect(prepararRevisaoDaExtraccao({ extractedData: {} })).toBeNull();
  });

  it("dados extraídos que não são objecto devolvem null", () => {
    expect(prepararRevisaoDaExtraccao({ extractedData: "nif: 123" })).toBeNull();
  });
});

describe("prepararRevisaoDaExtraccao — separar conflitos de valores novos", () => {
  const EXTRAIDOS = {
    nif: "123456789",
    nome_completo: "Maria Silva",
    rendimento_anual: 28400,
  };
  const CONFLITO = {
    field: "rendimento_anual",
    existing_value: 25000,
    new_value: 28400,
  };

  it("um campo em conflito não aparece como valor novo", () => {
    const revisao = prepararRevisaoDaExtraccao({
      extractedData: EXTRAIDOS,
      conflicts: [CONFLITO],
    });
    expect(revisao.conflicts).toHaveLength(1);
    expect(revisao.newValues.map((v) => v.field)).toEqual([
      "nif",
      "nome_completo",
    ]);
  });

  it("sem conflitos, TUDO é valor novo", () => {
    // O caso perigoso: nada a decidir, mas três campos a serem gravados.
    const revisao = prepararRevisaoDaExtraccao({ extractedData: EXTRAIDOS });
    expect(revisao.conflicts).toEqual([]);
    expect(revisao.newValues).toHaveLength(3);
  });

  it("nenhum campo extraído se perde entre as duas listas", () => {
    const revisao = prepararRevisaoDaExtraccao({
      extractedData: EXTRAIDOS,
      conflicts: [CONFLITO],
    });
    const vistos = new Set([
      ...revisao.conflicts.map((c) => c.field),
      ...revisao.newValues.map((v) => v.field),
    ]);
    expect(vistos).toEqual(new Set(Object.keys(EXTRAIDOS)));
  });

  it("os valores novos levam o valor, não só o nome do campo", () => {
    const revisao = prepararRevisaoDaExtraccao({ extractedData: { nif: "123456789" } });
    expect(revisao.newValues[0]).toEqual({ field: "nif", value: "123456789" });
  });

  it("um valor falsy (0) continua a ser um valor novo", () => {
    // Um rendimento de 0 é um dado, não uma ausência.
    const revisao = prepararRevisaoDaExtraccao({
      extractedData: { rendimento_anual: 0 },
    });
    expect(revisao.newValues).toEqual([{ field: "rendimento_anual", value: 0 }]);
  });

  it("conflitos malformados não partem a separação", () => {
    const revisao = prepararRevisaoDaExtraccao({
      extractedData: { nif: "1" },
      conflicts: [{ existing_value: 1 }, null],
    });
    expect(revisao.newValues.map((v) => v.field)).toEqual(["nif"]);
  });

  it("conflicts que não é array é tratado como lista vazia", () => {
    const revisao = prepararRevisaoDaExtraccao({
      extractedData: { nif: "1" },
      conflicts: "nenhum",
    });
    expect(revisao.conflicts).toEqual([]);
    expect(revisao.newValues).toHaveLength(1);
  });
});

describe("prepararRevisaoDaExtraccao — a quem pertencem os dados", () => {
  const DADOS = { extractedData: { nif: "123456789" } };

  it("sem informação de titular, é o titular 1", () => {
    // Nunca adivinhar o 2.º: escreveria dados na pessoa errada.
    expect(prepararRevisaoDaExtraccao(DADOS).targetTitular).toBe("titular1");
  });

  it("o agregado do processo manda", () => {
    const revisao = prepararRevisaoDaExtraccao({
      ...DADOS,
      titularMatches: [{ scope: "process_aggregate", match: "titular2" }],
    });
    expect(revisao.targetTitular).toBe("titular2");
  });

  it("um match por documento não decide sozinho", () => {
    // Só o agregado decide; um match de documento isolado não chega.
    const revisao = prepararRevisaoDaExtraccao({
      ...DADOS,
      titularMatches: [{ scope: "document", match: "titular2" }],
    });
    expect(revisao.targetTitular).toBe("titular1");
  });

  it("um agregado ambíguo cai no titular 1", () => {
    const revisao = prepararRevisaoDaExtraccao({
      ...DADOS,
      titularMatches: [{ scope: "process_aggregate", match: "ambiguous" }],
    });
    expect(revisao.targetTitular).toBe("titular1");
  });
});

describe("prepararRevisaoDaExtraccao — ficheiro de origem", () => {
  it("é transportado para o diálogo", () => {
    const revisao = prepararRevisaoDaExtraccao({
      extractedData: { nif: "1" },
      sourceDocument: "cc.jpg",
    });
    expect(revisao.sourceDocument).toBe("cc.jpg");
  });

  it("sem origem fica string vazia, nunca undefined", () => {
    // O diálogo decide se mostra o cabeçalho testando a verdade da string.
    expect(prepararRevisaoDaExtraccao({ extractedData: { nif: "1" } }).sourceDocument).toBe("");
  });
});

describe("aplicarDecisaoNaRevisao — a escolha do consultor é que manda", () => {
  const REVISAO = prepararRevisaoDaExtraccao({
    extractedData: { nif: "123456789", monthly_income: 1480 },
    conflicts: [
      { field: "monthly_income", existing_value: 1200, new_value: 1480 },
    ],
    sourceDocument: "recibo.pdf",
  });

  it("escolher o valor existente substitui o da IA nos dados a gravar", () => {
    // O defeito que isto previne: o conflito desaparecia do ecrã e a
    // confirmação gravava o valor da IA na mesma. A interface dizia uma
    // coisa e a ficha ficava com outra.
    const depois = aplicarDecisaoNaRevisao(REVISAO, "monthly_income", 1200);
    expect(depois.extractedData.monthly_income).toBe(1200);
  });

  it("um valor escrito à mão também vence", () => {
    const depois = aplicarDecisaoNaRevisao(REVISAO, "monthly_income", 1350);
    expect(depois.extractedData.monthly_income).toBe(1350);
  });

  it("o conflito decidido sai da lista", () => {
    const depois = aplicarDecisaoNaRevisao(REVISAO, "monthly_income", 1200);
    expect(depois.conflicts).toEqual([]);
  });

  it("os outros campos ficam intactos", () => {
    const depois = aplicarDecisaoNaRevisao(REVISAO, "monthly_income", 1200);
    expect(depois.extractedData.nif).toBe("123456789");
    expect(depois.sourceDocument).toBe("recibo.pdf");
    expect(depois.targetTitular).toBe("titular1");
  });

  it("não muta a revisão original", () => {
    // O contentor guarda isto em estado React; mutar seria um render
    // perdido à espera de acontecer.
    aplicarDecisaoNaRevisao(REVISAO, "monthly_income", 1200);
    expect(REVISAO.extractedData.monthly_income).toBe(1480);
    expect(REVISAO.conflicts).toHaveLength(1);
  });

  it("sem revisão pendente devolve o que recebeu", () => {
    // O caminho em lote passa por aqui com `null`.
    expect(aplicarDecisaoNaRevisao(null, "nif", "1")).toBeNull();
  });

  it("sem campo não decide nada", () => {
    expect(aplicarDecisaoNaRevisao(REVISAO, "", "x")).toBe(REVISAO);
  });

  it("decidir um campo que não era conflito acrescenta-o na mesma", () => {
    const depois = aplicarDecisaoNaRevisao(REVISAO, "nif", "999999999");
    expect(depois.extractedData.nif).toBe("999999999");
    expect(depois.conflicts).toHaveLength(1);
  });
});

describe("prepararRevisaoDaExtraccao — decisões já tomadas pelo consultor", () => {
  const DADOS = { extractedData: { nif: "123456789" } };

  it("um titular explícito vence a dedução dos matches", () => {
    // Na análise em lote o consultor já respondeu "este documento é de
    // quem?" num diálogo anterior. Recalcular a partir dos matches
    // deitaria essa resposta fora e escreveria na pessoa errada.
    const revisao = prepararRevisaoDaExtraccao({
      ...DADOS,
      targetTitular: "titular2",
      titularMatches: [{ scope: "process_aggregate", match: "titular1" }],
    });
    expect(revisao.targetTitular).toBe("titular2");
  });

  it("sem titular explícito, a dedução continua a valer", () => {
    const revisao = prepararRevisaoDaExtraccao({
      ...DADOS,
      titularMatches: [{ scope: "process_aggregate", match: "titular2" }],
    });
    expect(revisao.targetTitular).toBe("titular2");
  });

  it("a contagem de documentos é transportada", () => {
    const revisao = prepararRevisaoDaExtraccao({ ...DADOS, documentsProcessed: 4 });
    expect(revisao.documentsProcessed).toBe(4);
  });

  it("sem contagem assume um documento", () => {
    expect(prepararRevisaoDaExtraccao(DADOS).documentsProcessed).toBe(1);
  });

  it("a decisão sobre um conflito preserva titular e contagem", () => {
    // `aplicarDecisaoNaRevisao` faz spread: se algum campo novo se
    // perdesse aqui, a confirmação escreveria no titular errado.
    const revisao = prepararRevisaoDaExtraccao({
      extractedData: { nif: "1", monthly_income: 1480 },
      conflicts: [{ field: "monthly_income", existing_value: 1200, new_value: 1480 }],
      targetTitular: "titular2",
      documentsProcessed: 3,
    });
    const depois = aplicarDecisaoNaRevisao(revisao, "monthly_income", 1200);
    expect(depois.targetTitular).toBe("titular2");
    expect(depois.documentsProcessed).toBe(3);
  });
});
