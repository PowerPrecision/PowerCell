/**
 * "UI de Fases Mentirosa" — a timeline tinha de dizer a verdade do motor
 * (Lote 5, Prioridade 0).
 *
 * O MOTOR ESTÁ CERTO; ERA A UI QUE INVENTAVA
 *   As fases vêm de `workflow_statuses` (configuráveis pelo admin: criar,
 *   renomear, reordenar, apagar). O `ProcessTimeline` recebia-as e depois
 *   passava-lhes por cima com lógica própria. Três defeitos:
 *
 *   1. ALIASES A MANDAR NO MOTOR. Um mapa cravado em código traduzia
 *      `cpcv → fase_escritura`, `escriturado → concluidos`, etc. — e era
 *      aplicado ao estado ACTUAL e ao histórico, nunca à lista de fases.
 *      Se o admin criar mesmo uma fase chamada `cpcv` (nome natural num
 *      CRM de crédito), o processo que lá está era reescrito para uma
 *      fase diferente: a actual deixava de ser encontrada, o crachá do
 *      cabeçalho desaparecia e — porque `currentOrder` caía para 0 — TODAS
 *      as fases passavam a ler-se como pendentes. Um alias é recurso para
 *      dados antigos; nunca pode vencer um nome que o motor tem mesmo.
 *
 *   2. OS DIAS ERAM SEMPRE CONTRA HOJE. `differenceInDays(agora, entrada)`
 *      para CADA fase concluída. Uma fase que durou 2 dias há seis meses
 *      mostrava "180d", e o cabeçalho somava tudo: "5 fases • 812 dias"
 *      num processo com 6 meses. Uma fase dura da sua entrada até à
 *      entrada na SEGUINTE.
 *
 *   3. `currentOrder` NÃO DISTINGUIA "fase 0" DE "fase desconhecida".
 *      `currentPhaseInfo?.order || 0` dá 0 nos dois casos — e com 0 tudo
 *      o que vem a seguir parece futuro.
 */
import { describe, expect, it } from "vitest";

import { construirTimeline, normalizarEstado } from "./processTimeline";

const FASES = [
  { name: "clientes_espera", label: "Em Espera", color: "yellow", order: 1 },
  { name: "fase_documental", label: "Documentos", color: "blue", order: 2 },
  { name: "fase_bancaria", label: "Banca", color: "indigo", order: 3 },
  { name: "fase_escritura", label: "Escritura", color: "green", order: 4 },
];

const D = (dia) => `2026-03-${String(dia).padStart(2, "0")}T10:00:00Z`;

describe("normalizarEstado — o alias nunca vence o motor", () => {
  const nomes = new Set(FASES.map((f) => f.name));

  it("traduz um nome antigo que o motor já não tem", () => {
    expect(normalizarEstado("cpcv", nomes)).toBe("fase_escritura");
  });

  it("NÃO traduz um nome que o motor tem mesmo", () => {
    // O caso que partia a página: o admin cria a fase `cpcv` e o alias
    // mandava o processo para `fase_escritura`, que é outra coisa.
    const comCpcv = new Set([...nomes, "cpcv"]);
    expect(normalizarEstado("cpcv", comCpcv)).toBe("cpcv");
  });

  it("não traduz para um destino que o motor não tem", () => {
    // Se o admin apagou `concluidos`, reescrever `escriturado` para lá
    // trocava um nome desconhecido por outro — sem ganho nenhum.
    expect(normalizarEstado("escriturado", nomes)).toBe("escriturado");
  });

  it("sem lista de fases devolve o valor tal e qual", () => {
    expect(normalizarEstado("cpcv", null)).toBe("cpcv");
    expect(normalizarEstado("", nomes)).toBe("");
  });
});

describe("construirTimeline — a fase actual", () => {
  it("marca como actual a fase em que o processo está", () => {
    const linha = construirTimeline({ fases: FASES, estadoActual: "fase_bancaria", historico: [] });
    expect(linha.find((f) => f.isCurrent)?.phase).toBe("fase_bancaria");
  });

  it("uma fase que o motor não conhece não empurra tudo para pendente", () => {
    // `currentOrder` caía para 0 e todas as fases ficavam "depois da
    // actual" — a página inteira mentia por causa de um nome só.
    const linha = construirTimeline({
      fases: FASES,
      estadoActual: "fase_inventada",
      historico: [{ new_value: "fase_documental", timestamp: D(1) }],
    });
    expect(linha.some((f) => f.isCurrent)).toBe(false);
    expect(linha.find((f) => f.phase === "fase_documental").isCompleted).toBe(true);
    // Sem fase actual não se sabe o que é passado: nada é "saltado".
    expect(linha.some((f) => f.isSkipped)).toBe(false);
  });

  it("uma fase de ordem 0 é uma fase real, não uma desconhecida", () => {
    const fases = [{ name: "inicio", label: "Início", order: 0 }, ...FASES];
    const linha = construirTimeline({ fases, estadoActual: "inicio", historico: [] });
    expect(linha.find((f) => f.phase === "inicio").isCurrent).toBe(true);
    expect(linha.find((f) => f.phase === "fase_documental").isPendente).toBe(true);
  });
});

describe("construirTimeline — fases concluídas e saltadas", () => {
  const historico = [
    { new_value: "clientes_espera", timestamp: D(1) },
    { new_value: "fase_bancaria", timestamp: D(11) },
  ];

  it("só é concluída a fase com registo no histórico", () => {
    const linha = construirTimeline({ fases: FASES, estadoActual: "fase_escritura", historico });
    const porNome = Object.fromEntries(linha.map((f) => [f.phase, f]));
    expect(porNome.clientes_espera.isCompleted).toBe(true);
    expect(porNome.fase_bancaria.isCompleted).toBe(true);
    expect(porNome.fase_documental.isSkipped).toBe(true);
    expect(porNome.fase_escritura.isCurrent).toBe(true);
  });

  it("uma fase saltada não inventa data", () => {
    const linha = construirTimeline({ fases: FASES, estadoActual: "fase_escritura", historico });
    expect(linha.find((f) => f.phase === "fase_documental").date).toBeNull();
  });
});

describe("construirTimeline — a duração de cada fase", () => {
  const agora = new Date("2026-09-23T10:00:00Z");
  const historico = [
    { new_value: "clientes_espera", timestamp: D(1) },
    { new_value: "fase_bancaria", timestamp: D(11) },
  ];

  it("uma fase dura até à entrada na seguinte, não até hoje", () => {
    // Era aqui que estava a mentira grande: `clientes_espera` durou 10
    // dias e mostrava ~206 (a distância até hoje).
    const linha = construirTimeline({ fases: FASES, estadoActual: "fase_escritura", historico, agora });
    expect(linha.find((f) => f.phase === "clientes_espera").daysInPhase).toBe(10);
  });

  it("a fase actual conta-se até hoje", () => {
    const linha = construirTimeline({
      fases: FASES,
      estadoActual: "fase_bancaria",
      historico,
      agora,
    });
    expect(linha.find((f) => f.phase === "fase_bancaria").daysInPhase).toBe(196);
  });

  it("o total não soma a mesma janela de tempo várias vezes", () => {
    // O cabeçalho mostrava "5 fases • 812 dias" num processo com 6 meses.
    const linha = construirTimeline({ fases: FASES, estadoActual: "fase_escritura", historico, agora });
    const total = linha.reduce((acc, f) => acc + (f.daysInPhase || 0), 0);
    const inicio = new Date(D(1));
    const decorridos = Math.round((agora - inicio) / 86400000);
    expect(total).toBeLessThanOrEqual(decorridos);
  });
});

describe("construirTimeline — degradação graciosa", () => {
  it("sem fases devolve lista vazia em vez de rebentar", () => {
    expect(construirTimeline({ fases: [], estadoActual: "x", historico: [] })).toEqual([]);
    expect(construirTimeline()).toEqual([]);
  });

  it("um histórico com datas inválidas não parte a linha", () => {
    const linha = construirTimeline({
      fases: FASES,
      estadoActual: "fase_bancaria",
      historico: [{ new_value: "clientes_espera", timestamp: "não é uma data" }],
    });
    expect(linha).toHaveLength(4);
    expect(linha.find((f) => f.phase === "clientes_espera").isCompleted).toBe(true);
  });
});
