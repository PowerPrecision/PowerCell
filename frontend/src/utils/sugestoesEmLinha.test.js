/**
 * Preenchimento em linha — e a regra de ouro intacta (Lote 3, ponto 1).
 *
 * A MUDANÇA
 * O resultado da extracção vivia num diálogo sobreposto que TAPAVA a ficha:
 * para comparar com o resto dos dados era preciso fechá-lo, e a decisão era
 * um bloco (aceitar sete campos para corrigir um). Agora a sugestão aparece
 * no campo, com destaque e aprovar/rejeitar ao lado.
 *
 * O QUE ESTES TESTES PROTEGEM, E É O ESSENCIAL
 * «A IA nunca grava dados pessoais ou financeiros sem confirmação.» Mostrar
 * um valor **não é gravá-lo**. É por isso que `valorAMostrar` e
 * `valoresAprovados` são funções diferentes, e é essa diferença que
 * distingue o preenchimento em linha de uma escrita automática com um passo
 * decorativo por cima.
 *
 * Um campo PENDENTE já aparece no ecrã e **não entra no payload**. Se esta
 * distinção se perder, a interface fica igual e a regra de ouro desaparece
 * sem deixar rasto — o pior tipo de regressão.
 */
import { describe, expect, it } from "vitest";

import {
  APROVADA,
  PENDENTE,
  REJEITADA,
  aprovar,
  aprovarTodas,
  classeDeDestaque,
  contarPorEstado,
  criarSugestoes,
  estadoDoCampo,
  limparDecididas,
  rejeitar,
  rejeitarTodas,
  sugestaoDoCampo,
  temPendentes,
  todasDecididas,
  valorAMostrar,
  valoresAprovados,
} from "./sugestoesEmLinha";

const REVISAO = {
  extractedData: { nif: "123456789", morada_fiscal: "Rua A, 1" },
  conflicts: [{ field: "nif", existing_value: "987654321", new_value: "123456789" }],
  newValues: [{ field: "morada_fiscal", value: "Rua A, 1" }],
  sourceDocument: "cc.pdf",
  targetTitular: "titular1",
  documentsProcessed: 1,
};

describe("Criar as sugestões", () => {
  it("junta conflitos e valores novos", () => {
    const s = criarSugestoes(REVISAO);
    expect(Object.keys(s.campos).sort()).toEqual(["morada_fiscal", "nif"]);
  });

  it("marca o que é CONFLITO", () => {
    // Um conflito tem um valor humano a perder; um campo vazio não. A UI
    // tem de poder dizer a diferença.
    const s = criarSugestoes(REVISAO);
    expect(s.campos.nif.eConflito).toBe(true);
    expect(s.campos.morada_fiscal.eConflito).toBe(false);
  });

  it("guarda o valor anterior de um conflito", () => {
    expect(criarSugestoes(REVISAO).campos.nif.valorAnterior).toBe("987654321");
  });

  it("tudo começa PENDENTE", () => {
    const s = criarSugestoes(REVISAO);
    expect(Object.values(s.campos).every((c) => c.estado === PENDENTE)).toBe(true);
  });

  it("preserva a origem e o titular", () => {
    const s = criarSugestoes(REVISAO);
    expect(s.sourceDocument).toBe("cc.pdf");
    expect(s.targetTitular).toBe("titular1");
  });

  it("sem nada a rever devolve null", () => {
    // Destacar campos sem sugestão nenhuma é pior do que dizer que a leitura
    // não deu nada.
    expect(criarSugestoes(null)).toBeNull();
    expect(criarSugestoes({ conflicts: [], newValues: [] })).toBeNull();
  });

  it("um conflito ganha ao valor novo com o mesmo nome", () => {
    // O conflito traz o valor anterior; o "novo" não. Perder essa informação
    // fazia a UI tratar uma sobreposição como um preenchimento.
    const s = criarSugestoes({
      conflicts: [{ field: "nif", existing_value: "1", new_value: "2" }],
      newValues: [{ field: "nif", value: "3" }],
    });
    expect(s.campos.nif.eConflito).toBe(true);
    expect(s.campos.nif.valorSugerido).toBe("2");
  });

  it("entradas sem nome de campo são ignoradas", () => {
    const s = criarSugestoes({ conflicts: [{ new_value: "x" }], newValues: [{ value: "y" }] });
    expect(s).toBeNull();
  });
});

describe("A REGRA DE OURO: mostrar não é gravar", () => {
  it("um campo PENDENTE já aparece no ecrã", () => {
    const s = criarSugestoes(REVISAO);
    expect(valorAMostrar(s, "nif", "987654321")).toBe("123456789");
  });

  it("mas NÃO entra no payload", () => {
    // É esta a asserção central do ficheiro. Se cair, a interface fica igual
    // e a regra de ouro desaparece sem deixar rasto.
    const s = criarSugestoes(REVISAO);
    expect(valoresAprovados(s)).toEqual({});
  });

  it("só depois de aprovar entra", () => {
    const s = aprovar(criarSugestoes(REVISAO), "nif");
    expect(valoresAprovados(s)).toEqual({ nif: "123456789" });
  });

  it("aprovar um campo não arrasta os outros", () => {
    const s = aprovar(criarSugestoes(REVISAO), "nif");
    expect(valoresAprovados(s)).not.toHaveProperty("morada_fiscal");
  });

  it("um campo rejeitado nunca entra", () => {
    const s = rejeitar(aprovar(criarSugestoes(REVISAO), "nif"), "morada_fiscal");
    expect(valoresAprovados(s)).toEqual({ nif: "123456789" });
  });

  it("sem sugestões o payload é vazio e não rebenta", () => {
    expect(valoresAprovados(null)).toEqual({});
    expect(valoresAprovados({})).toEqual({});
  });
});

describe("O que o input desenha", () => {
  it("rejeitada volta ao valor do formulário", () => {
    const s = rejeitar(criarSugestoes(REVISAO), "nif");
    expect(valorAMostrar(s, "nif", "987654321")).toBe("987654321");
  });

  it("aprovada mostra o sugerido", () => {
    const s = aprovar(criarSugestoes(REVISAO), "nif");
    expect(valorAMostrar(s, "nif", "987654321")).toBe("123456789");
  });

  it("um campo sem sugestão fica como está", () => {
    const s = criarSugestoes(REVISAO);
    expect(valorAMostrar(s, "telefone", "912345678")).toBe("912345678");
  });

  it("sem sugestões nenhumas o formulário manda", () => {
    expect(valorAMostrar(null, "nif", "987654321")).toBe("987654321");
  });
});

describe("Decidir em bloco não desfaz decisões", () => {
  it("aprovar todas aprova as pendentes", () => {
    const s = aprovarTodas(criarSugestoes(REVISAO));
    expect(valoresAprovados(s)).toEqual({ nif: "123456789", morada_fiscal: "Rua A, 1" });
  });

  it("aprovar todas NÃO reabre o que já foi rejeitado", () => {
    // Um "aprovar tudo" que desfizesse rejeições gravava o que o consultor
    // tinha acabado de recusar — em silêncio.
    const s = aprovarTodas(rejeitar(criarSugestoes(REVISAO), "nif"));
    expect(estadoDoCampo(s, "nif")).toBe(REJEITADA);
    expect(valoresAprovados(s)).toEqual({ morada_fiscal: "Rua A, 1" });
  });

  it("rejeitar todas não desfaz o que já foi aprovado", () => {
    const s = rejeitarTodas(aprovar(criarSugestoes(REVISAO), "nif"));
    expect(estadoDoCampo(s, "nif")).toBe(APROVADA);
  });
});

describe("Imutabilidade", () => {
  it("aprovar devolve um objecto novo", () => {
    const antes = criarSugestoes(REVISAO);
    const depois = aprovar(antes, "nif");
    expect(antes.campos.nif.estado).toBe(PENDENTE);
    expect(depois).not.toBe(antes);
  });

  it("aprovar um campo inexistente não altera nada", () => {
    const antes = criarSugestoes(REVISAO);
    expect(aprovar(antes, "campo_que_nao_existe")).toBe(antes);
  });
});

describe("Contagens e estado do lote", () => {
  it("conta por estado", () => {
    const s = rejeitar(aprovar(criarSugestoes(REVISAO), "nif"), "morada_fiscal");
    expect(contarPorEstado(s)).toEqual({ pendente: 0, aprovada: 1, rejeitada: 1 });
  });

  it("temPendentes", () => {
    expect(temPendentes(criarSugestoes(REVISAO))).toBe(true);
    expect(temPendentes(aprovarTodas(criarSugestoes(REVISAO)))).toBe(false);
  });

  it("todasDecididas exige que houvesse algo a decidir", () => {
    // Com zero sugestões, "está tudo decidido" era verdade e disparava o
    // fim do fluxo sem nada ter acontecido.
    expect(todasDecididas(null)).toBe(false);
    expect(todasDecididas({ campos: {} })).toBe(false);
    expect(todasDecididas(aprovarTodas(criarSugestoes(REVISAO)))).toBe(true);
  });
});

describe("O destaque visual", () => {
  it("pendente é amarelo", () => {
    expect(classeDeDestaque(PENDENTE)).toContain("amber");
  });

  it("aprovada é verde", () => {
    expect(classeDeDestaque(APROVADA)).toContain("emerald");
  });

  it("rejeitada não destaca", () => {
    // O valor voltou a ser o da ficha — destacá-lo dizia o contrário.
    expect(classeDeDestaque(REJEITADA)).toBe("");
    expect(classeDeDestaque(null)).toBe("");
  });
});

describe("Limpar depois de gravar", () => {
  it("as decididas saem e as pendentes ficam", () => {
    // As aprovadas passaram a ser o valor da ficha; manter o destaque verde
    // para sempre mentia sobre a origem do dado.
    const s = aprovar(criarSugestoes(REVISAO), "nif");
    const limpo = limparDecididas(s);
    expect(Object.keys(limpo.campos)).toEqual(["morada_fiscal"]);
  });

  it("sem pendentes devolve null", () => {
    expect(limparDecididas(aprovarTodas(criarSugestoes(REVISAO)))).toBeNull();
  });
});

describe("Acesso a uma sugestão", () => {
  it("devolve os dados do campo", () => {
    expect(sugestaoDoCampo(criarSugestoes(REVISAO), "nif").valorSugerido).toBe("123456789");
  });

  it("null para um campo sem sugestão", () => {
    expect(sugestaoDoCampo(criarSugestoes(REVISAO), "x")).toBeNull();
    expect(estadoDoCampo(null, "nif")).toBeNull();
  });
});
