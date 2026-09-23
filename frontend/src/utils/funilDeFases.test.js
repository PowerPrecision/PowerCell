/**
 * O funil do dashboard deixava cair processos em silêncio (Lote 5, P0).
 *
 * `FUNNEL_MACRO` era uma lista cravada no `ConsultorDashboard`: quatro
 * grupos com os nomes das fases escritos à mão. Duas consequências, as
 * duas invisíveis:
 *
 *   1. UM PROCESSO NUMA FASE NÃO LISTADA NÃO CONTA PARA LADO NENHUM. O
 *      admin pode criar fases; nenhuma delas entra aqui. A soma das
 *      quatro colunas era menor do que o total de processos e nada no
 *      ecrã dizia isso. Um consultor com processos numa fase nova via o
 *      funil a dizer que não tinha trabalho.
 *   2. `escritura` estava em DOIS grupos ("Aprovado" e "Concluído") — o
 *      mesmo processo contado conforme a ordem de iteração.
 *
 * A REGRA: o funil é uma VISTA agrupada do motor, não uma segunda
 * verdade. Nenhum processo pode desaparecer dele, e nenhum pode ser
 * contado duas vezes.
 */
import { describe, expect, it } from "vitest";

import { MACRO_FASES, agruparEmFunil } from "./funilDeFases";

const processos = (...estados) => estados.map((status, i) => ({ id: `p${i}`, status }));

describe("agruparEmFunil — nada se perde", () => {
  it("um processo numa fase que nenhum grupo lista continua a contar", () => {
    const funil = agruparEmFunil(processos("fase_inventada_pelo_admin"));
    const total = funil.reduce((acc, g) => acc + g.value, 0);
    expect(total).toBe(1);
  });

  it("a soma do funil é sempre o total de processos", () => {
    const lista = processos(
      "clientes_espera", "fase_bancaria", "ch_aprovado", "concluidos",
      "uma_fase_nova", "outra_fase_nova", "desistencias",
    );
    const total = agruparEmFunil(lista).reduce((acc, g) => acc + g.value, 0);
    expect(total).toBe(lista.length);
  });

  it("um processo sem estado não desaparece nem rebenta", () => {
    const funil = agruparEmFunil([{ id: "p1" }, { id: "p2", status: null }]);
    expect(funil.reduce((acc, g) => acc + g.value, 0)).toBe(2);
  });
});

describe("agruparEmFunil — nada conta duas vezes", () => {
  it("nenhuma fase aparece em mais do que um grupo", () => {
    // `escritura` estava em "Aprovado" E em "Concluído".
    const vistas = new Set();
    for (const grupo of MACRO_FASES) {
      for (const fase of grupo.statuses) {
        expect(vistas.has(fase), `"${fase}" está em mais do que um grupo`).toBe(false);
        vistas.add(fase);
      }
    }
  });

  it("um processo conta exactamente uma vez", () => {
    const funil = agruparEmFunil(processos("escritura"));
    expect(funil.filter((g) => g.value > 0)).toHaveLength(1);
  });
});

describe("agruparEmFunil — o grupo das restantes", () => {
  it("só aparece quando tem alguma coisa lá dentro", () => {
    // Uma coluna "Outras: 0" permanente é ruído no ecrã de toda a gente.
    const funil = agruparEmFunil(processos("clientes_espera", "concluidos"));
    expect(funil.some((g) => g.key === "outras")).toBe(false);
  });

  it("aparece, e nomeado, quando há fases fora dos grupos conhecidos", () => {
    const funil = agruparEmFunil(processos("clientes_espera", "fase_nova"));
    const outras = funil.find((g) => g.key === "outras");
    expect(outras).toBeTruthy();
    expect(outras.value).toBe(1);
    expect(outras.statuses).toContain("fase_nova");
  });

  it("usa a etiqueta do motor quando o motor a conhece", () => {
    // Clicar no grupo filtra por uma fase concreta: o nome tem de ser o
    // que o admin configurou, não o nome técnico.
    const funil = agruparEmFunil(processos("fase_nova"), [
      { name: "fase_nova", label: "Pré-Avaliação", order: 9 },
    ]);
    expect(funil.find((g) => g.key === "outras").name).toContain("Pré-Avaliação");
  });
});

describe("agruparEmFunil — degradação graciosa", () => {
  it("sem processos devolve os grupos a zero, não uma lista vazia", () => {
    const funil = agruparEmFunil([]);
    expect(funil.length).toBe(MACRO_FASES.length);
    expect(funil.every((g) => g.value === 0)).toBe(true);
  });

  it("sem argumentos não rebenta", () => {
    expect(Array.isArray(agruparEmFunil())).toBe(true);
  });
});
