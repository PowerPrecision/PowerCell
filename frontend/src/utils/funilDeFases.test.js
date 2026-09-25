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
    // INVERTIDO (Épico 10, Parte 2). Antes cada grupo trazia a sua lista
    // de fases e a asserção percorria-as à procura de repetições — era
    // assim que `escritura` tinha aparecido em "Aprovado" E "Concluído".
    //
    // As listas saíram daqui: quem classifica é o motor, e uma fase
    // resolve para UM grupo por construção. A asserção que resta é sobre
    // o RESULTADO — que é o que o utilizador vê.
    const funil = agruparEmFunil(
      processos(
        "clientes_espera", "ch_aprovado", "concluidos",
        "desistencias", "fase_que_ninguem_conhece",
      ),
      [],
    );
    const vistas = new Set();
    for (const grupo of funil) {
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

describe("agruparEmFunil — o motor classifica, o recurso só socorre", () => {
  const fase = (name, macro_fase, label) => ({ name, macro_fase, label });

  it("o `macro_fase` do motor ganha à classificação de recurso", () => {
    // `concluidos` é "concluido" no mapa de recurso. Se o administrador
    // decidir que é "perdido", é "perdido" — senão a UI de edição era
    // decorativa.
    const funil = agruparEmFunil(processos("concluidos"), [
      fase("concluidos", "perdido"),
    ]);
    expect(funil.find((g) => g.key === "perdido").value).toBe(1);
    expect(funil.find((g) => g.key === "concluido").value).toBe(0);
  });

  it("uma fase nova classificada no motor entra no grupo, sem deploy", () => {
    // Era isto que uma lista cravada tornava impossível.
    const funil = agruparEmFunil(processos("renegociacao_2026"), [
      fase("renegociacao_2026", "analise", "Renegociação 2026"),
    ]);
    expect(funil.find((g) => g.key === "analise").value).toBe(1);
    expect(funil.some((g) => g.key === "outras")).toBe(false);
  });

  it("uma fase que o motor ainda não classificou cai no recurso", () => {
    // Instalação que não correu o backfill: continua a funcionar.
    const funil = agruparEmFunil(processos("ch_aprovado"), [
      fase("ch_aprovado", null, "CH Aprovado"),
    ]);
    expect(funil.find((g) => g.key === "aprovado").value).toBe(1);
  });

  it("um `macro_fase` fora do enum é ignorado, não inventa grupo", () => {
    // O backend recusa ao gravar, mas um documento antigo pode trazê-lo.
    const funil = agruparEmFunil(processos("ch_aprovado"), [
      fase("ch_aprovado", "quase_aprovado", "CH Aprovado"),
    ]);
    expect(funil.map((g) => g.key)).not.toContain("quase_aprovado");
    // Cai no recurso, que conhece esta fase.
    expect(funil.find((g) => g.key === "aprovado").value).toBe(1);
  });

  it("as desistências deixaram de cair em «Outras»", () => {
    // O buraco que a Parte 2 fecha: num funil de negócio, o processo
    // perdido é informação, não sobra.
    const funil = agruparEmFunil(processos("desistencias"), []);
    expect(funil.find((g) => g.key === "perdido").value).toBe(1);
    expect(funil.some((g) => g.key === "outras")).toBe(false);
  });

  it("o grupo diz que fases lhe deram origem", () => {
    // `statuses` passou a ser o que REALMENTE caiu no grupo, não a
    // lista declarada — é o que serve para clicar e filtrar.
    const funil = agruparEmFunil(
      processos("clientes_espera", "fase_documental", "clientes_espera"),
      [],
    );
    const novo = funil.find((g) => g.key === "novo");
    expect(novo.value).toBe(3);
    expect(novo.statuses.sort()).toEqual(["clientes_espera", "fase_documental"]);
  });

  it("os cinco grupos aparecem sempre, mesmo a zero", () => {
    const funil = agruparEmFunil([], []);
    expect(funil.map((g) => g.key)).toEqual([
      "novo", "analise", "aprovado", "concluido", "perdido",
    ]);
  });

  it("o total continua a bater certo com o motor a mandar", () => {
    const lista = processos(
      "clientes_espera", "concluidos", "desistencias", "xpto", null,
    );
    const funil = agruparEmFunil(lista, [fase("concluidos", "perdido")]);
    expect(funil.reduce((t, g) => t + g.value, 0)).toBe(lista.length);
  });
});
