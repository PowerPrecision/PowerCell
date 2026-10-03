/**
 * O indicador de confiança da IA olha para o VALOR (Lote 3, ponto 2).
 *
 * O DEFEITO
 * `getConfidenceIndicator` decidia com o número e nada mais:
 *
 *     const conf = aiFieldConfidence?.[fieldName];
 *     if (conf === undefined || conf === null || !aiExtractedData) return null;
 *
 * O campo NIF tem `placeholder="9 dígitos"`. Um NIF vazio desenha esse texto
 * cinzento no input, e ao lado dele aparecia o badge «IA 100%».
 *
 * É **o badge que faz o placeholder parecer um dado**: sem ele, um campo
 * vazio lê-se como um campo vazio. Dar confiança máxima a uma extracção
 * nula é pior do que não mostrar confiança nenhuma — desliga a
 * desconfiança exactamente no campo que mais precisa dela.
 */
import { describe, expect, it } from "vitest";

import {
  PATAMARES,
  PLACEHOLDERS_POR_CAMPO,
  indicadorDeConfianca,
  pareceOPlaceholder,
  validadoresPadrao,
} from "./aiConfidence";
import { validateNIF } from "./validateNIF";

const validadores = validadoresPadrao({ validateNIF });

describe("Um valor vazio não tem confiança nenhuma", () => {
  it("string vazia", () => {
    expect(indicadorDeConfianca({ valor: "", confianca: 1 })).toBeNull();
  });

  it("só espaços", () => {
    expect(indicadorDeConfianca({ valor: "   ", confianca: 1 })).toBeNull();
  });

  it("null e undefined", () => {
    expect(indicadorDeConfianca({ valor: null, confianca: 1 })).toBeNull();
    expect(indicadorDeConfianca({ valor: undefined, confianca: 1 })).toBeNull();
  });

  it("CONTRAPROVA: com valor, a confiança aparece", () => {
    // Sem isto, "nunca mostra nada" passava todos os testes acima e o
    // indicador desaparecia do produto.
    const ind = indicadorDeConfianca({ valor: "123456789", confianca: 1 });
    expect(ind).not.toBeNull();
    expect(ind.label).toBe("100%");
  });

  it("o ZERO é um valor, não um vazio", () => {
    // Um rendimento de 0 € é um dado. Tratá-lo como vazio escondia a
    // proveniência de um campo que foi mesmo extraído.
    const ind = indicadorDeConfianca({ valor: 0, confianca: 0.9 });
    expect(ind).not.toBeNull();
  });
});

describe("O texto do placeholder não é um dado", () => {
  it("o caso exacto que foi reportado: NIF com «9 dígitos»", () => {
    expect(
      indicadorDeConfianca({
        valor: "9 dígitos",
        confianca: 1,
        placeholder: PLACEHOLDERS_POR_CAMPO.nif,
      }),
    ).toBeNull();
  });

  it("a comparação ignora maiúsculas, acentos e espaços", () => {
    // «9 Digitos » e «9 dígitos» são o mesmo texto; a IA que lê um
    // formulário em branco não garante a ortografia.
    expect(pareceOPlaceholder("9 Digitos ", "9 dígitos")).toBe(true);
    expect(pareceOPlaceholder("  9 DÍGITOS", "9 dígitos")).toBe(true);
  });

  it("um valor legítimo que só CONTÉM a palavra do placeholder passa", () => {
    // A comparação é por igualdade e não por `includes`: um `includes`
    // largo recusaria dados reais.
    expect(pareceOPlaceholder("Rua dos 9 dígitos, 12", "9 dígitos")).toBe(false);
  });

  it("sem placeholder declarado, não há nada a comparar", () => {
    expect(pareceOPlaceholder("qualquer coisa", undefined)).toBe(false);
    expect(pareceOPlaceholder("qualquer coisa", "")).toBe(false);
  });

  it("os placeholders vivem num só sítio", () => {
    // Escritos ao lado de cada `placeholder=` divergiriam dele em silêncio,
    // e a divergência fazia o indicador voltar a aprovar o placeholder.
    expect(PLACEHOLDERS_POR_CAMPO.nif).toBe("9 dígitos");
    expect(PLACEHOLDERS_POR_CAMPO.niss).toBe("11 dígitos");
  });
});

describe("Um valor que o formulário recusa não leva selo", () => {
  it("um NIF de 3 dígitos não tem confiança", () => {
    expect(
      indicadorDeConfianca({ valor: "123", confianca: 1, validar: validadores.nif }),
    ).toBeNull();
  });

  it("um NIF com letras também não", () => {
    expect(
      indicadorDeConfianca({ valor: "12345678a", confianca: 1, validar: validadores.nif }),
    ).toBeNull();
  });

  it("CONTRAPROVA: um NIF válido leva", () => {
    expect(
      indicadorDeConfianca({ valor: "123456789", confianca: 0.95, validar: validadores.nif }),
    ).not.toBeNull();
  });

  it("o validador apanha o placeholder mesmo sem o placeholder declarado", () => {
    // Duas defesas para o mesmo caso, de propósito: o campo que tiver
    // validação fica coberto mesmo que alguém esqueça o placeholder, e o
    // campo que não tiver (NISS) fica coberto pelo placeholder.
    expect(
      indicadorDeConfianca({ valor: "9 dígitos", confianca: 1, validar: validadores.nif }),
    ).toBeNull();
  });

  it("um validador que rebenta não esconde confiança legítima", () => {
    // Um erro nosso não pode apagar informação verdadeira — mas também não
    // a abençoa: o vazio e o placeholder continuam a ser recusados antes.
    const rebenta = () => {
      throw new Error("validador partido");
    };
    expect(
      indicadorDeConfianca({ valor: "123456789", confianca: 0.9, validar: rebenta }),
    ).not.toBeNull();
    expect(indicadorDeConfianca({ valor: "", confianca: 0.9, validar: rebenta })).toBeNull();
  });
});

describe("Sem extracção não há indicador", () => {
  it("houveExtraccao=false cala tudo", () => {
    expect(
      indicadorDeConfianca({ valor: "123456789", confianca: 1, houveExtraccao: false }),
    ).toBeNull();
  });

  it("confiança ausente ou não-numérica cala tudo", () => {
    expect(indicadorDeConfianca({ valor: "123456789" })).toBeNull();
    expect(indicadorDeConfianca({ valor: "123456789", confianca: null })).toBeNull();
    expect(indicadorDeConfianca({ valor: "123456789", confianca: "alta" })).toBeNull();
    expect(indicadorDeConfianca({ valor: "123456789", confianca: NaN })).toBeNull();
  });
});

describe("Os patamares não mudaram", () => {
  it("≥0.8 é alto, ≥0.6 médio, abaixo baixo", () => {
    expect(indicadorDeConfianca({ valor: "x", confianca: 0.95 }).nivel).toBe("high");
    expect(indicadorDeConfianca({ valor: "x", confianca: 0.8 }).nivel).toBe("high");
    expect(indicadorDeConfianca({ valor: "x", confianca: 0.7 }).nivel).toBe("medium");
    expect(indicadorDeConfianca({ valor: "x", confianca: 0.6 }).nivel).toBe("medium");
    expect(indicadorDeConfianca({ valor: "x", confianca: 0.3 }).nivel).toBe("low");
  });

  it("a percentagem é arredondada", () => {
    expect(indicadorDeConfianca({ valor: "x", confianca: 0.876 }).label).toBe("88%");
  });

  it("há três patamares e o último apanha tudo", () => {
    expect(PATAMARES).toHaveLength(3);
    expect(PATAMARES[PATAMARES.length - 1].minimo).toBe(0);
  });

  it("devolve a classe da borda para o input", () => {
    expect(indicadorDeConfianca({ valor: "x", confianca: 0.9 }).borderClass).toContain(
      "border-l-4",
    );
  });
});

describe("O validador de NIF é o do formulário", () => {
  it("um NIF vazio não é um erro de validação — é um vazio", () => {
    // `validateNIF("")` devolve `{valid: true}`. É a guarda do vazio que
    // tem de apanhar este caso, não o validador.
    expect(validadores.nif("")).toBe(true);
    expect(indicadorDeConfianca({ valor: "", confianca: 1, validar: validadores.nif })).toBeNull();
  });

  it("sem validateNIF não se inventa validador nenhum", () => {
    expect(validadoresPadrao({}).nif).toBeUndefined();
    expect(validadoresPadrao().nif).toBeUndefined();
  });
});
