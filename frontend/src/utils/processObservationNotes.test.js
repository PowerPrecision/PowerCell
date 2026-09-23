/**
 * O texto livre do processo — Lote 5, Secção B, ponto 14.
 *
 * O PEDIDO: "o Resumo tem de apresentar o texto livre escrito pelos
 * utilizadores, poupando-lhes cliques para procurar contexto."
 *
 * O QUE ESTAVA A ACONTECER: há TRÊS campos de texto livre e o Resumo lia
 * um e meio.
 *
 *   - `observation_notes` — o feed, escrito no cartão do Resumo.
 *   - `notes` / `observations` — o escalar legado, que é onde o modal do
 *     Kanban ainda escreve hoje (`ProcessDetailsModal`).
 *   - `ai_extracted_notes` — o que a IA leu, visível SÓ no modal do
 *     Kanban.
 *
 * `resolveProcessObservationNotes` fazia `if (feed.length > 0) return
 * feed;` — o escalar era um FALLBACK. Bastava alguém acrescentar uma nota
 * no Resumo para o que tinha sido escrito no Kanban desaparecer de vez.
 * Não é um fallback: são dois sítios onde as pessoas escrevem.
 *
 * A REGRA: o Resumo JUNTA as origens em vez de escolher uma. Cada nota
 * diz de onde vem, e nada é descartado em silêncio.
 */
import { describe, expect, it } from "vitest";

import { resolveProcessObservationNotes } from "./processObservationNotes";

describe("resolveProcessObservationNotes — o feed", () => {
  it("devolve as notas do feed", () => {
    const notas = resolveProcessObservationNotes({
      observation_notes: [{ id: "n1", text: "nova" }],
    });
    expect(notas).toHaveLength(1);
    expect(notas[0].text).toBe("nova");
  });

  it("sem nada guardado devolve lista vazia", () => {
    expect(resolveProcessObservationNotes({})).toEqual([]);
    expect(resolveProcessObservationNotes()).toEqual([]);
    expect(resolveProcessObservationNotes(null)).toEqual([]);
  });
});

describe("resolveProcessObservationNotes — o escalar legado não é um fallback", () => {
  it("aparece MESMO quando o feed já tem notas", () => {
    // O defeito do ponto 14: escrito no Kanban, invisível no Resumo.
    const notas = resolveProcessObservationNotes({
      observation_notes: [{ id: "n1", text: "nova" }],
      observations: "escrito no Kanban",
    });
    expect(notas.map((n) => n.text)).toContain("escrito no Kanban");
    expect(notas.map((n) => n.text)).toContain("nova");
  });

  it("continua a aparecer quando o feed está vazio", () => {
    const notas = resolveProcessObservationNotes({ observations: "nota livre" });
    expect(notas).toHaveLength(1);
    expect(notas[0].text).toBe("nota livre");
  });

  it("não se duplica quando o feed já tem o mesmo texto", () => {
    // `process_update` sincroniza `notes` e `observations`, e o modal do
    // Kanban chegou a copiar a última nota do feed para o escalar: sem
    // esta regra a mesma frase apareceria duas vezes.
    const notas = resolveProcessObservationNotes({
      observation_notes: [{ id: "n1", text: "  mesma frase " }],
      observations: "mesma frase",
    });
    expect(notas).toHaveLength(1);
  });

  it("`notes` e `observations` iguais contam uma vez só", () => {
    const notas = resolveProcessObservationNotes({
      notes: "a mesma",
      observations: "a mesma",
    });
    expect(notas).toHaveLength(1);
  });

  it("`notes` e `observations` diferentes aparecem ambos", () => {
    // Não devia acontecer (o backend sincroniza-os), mas se acontecer é
    // texto que alguém escreveu: não se escolhe um e deita-se o outro.
    const notas = resolveProcessObservationNotes({
      notes: "uma coisa",
      observations: "outra coisa",
    });
    expect(notas).toHaveLength(2);
  });

  it("a nota legada diz de onde vem", () => {
    const [nota] = resolveProcessObservationNotes({ observations: "nota livre" });
    expect(nota.origin).toBe("legacy");
  });
});

describe("resolveProcessObservationNotes — o que a IA leu", () => {
  it("aparece no Resumo, marcado como sendo da IA", () => {
    // Estava só no modal do Kanban: para o ver era preciso sair do
    // processo, abrir o quadro e encontrar o cartão.
    const notas = resolveProcessObservationNotes({
      observation_notes: [{ id: "n1", text: "nova" }],
      ai_extracted_notes: "IRS indica rendimento anual de 24.000 EUR",
    });
    const daIA = notas.find((n) => n.origin === "ai");
    expect(daIA).toBeTruthy();
    expect(daIA.text).toContain("24.000");
  });

  it("um texto da IA vazio não cria uma nota em branco", () => {
    expect(resolveProcessObservationNotes({ ai_extracted_notes: "   " })).toEqual([]);
  });
});

describe("resolveProcessObservationNotes — ordem e robustez", () => {
  it("a nota mais recente fica no fim", () => {
    const notas = resolveProcessObservationNotes({
      observation_notes: [
        { id: "a", text: "antiga", created_at: "2026-01-01T10:00:00Z" },
        { id: "b", text: "recente", created_at: "2026-06-01T10:00:00Z" },
      ],
    });
    expect(notas[notas.length - 1].text).toBe("recente");
  });

  it("notas sem data não desaparecem", () => {
    const notas = resolveProcessObservationNotes({
      observation_notes: [
        { id: "a", text: "sem data" },
        { id: "b", text: "com data", created_at: "2026-06-01T10:00:00Z" },
      ],
    });
    expect(notas).toHaveLength(2);
  });

  it("entradas inválidas no feed não partem a leitura", () => {
    const notas = resolveProcessObservationNotes({
      observation_notes: [null, { id: "a", text: "boa" }, { id: "b" }, "texto solto"],
    });
    expect(notas.map((n) => n.text)).toEqual(["boa"]);
  });
});
