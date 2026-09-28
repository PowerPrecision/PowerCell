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

import {
  notaMaisRecenteDoConsultor,
  resolveProcessObservationNotes,
} from "./processObservationNotes";

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

describe("notaMaisRecenteDoConsultor — a coluna da listagem (Ponto 9)", () => {
  it("devolve a nota mais recente do feed", () => {
    expect(
      notaMaisRecenteDoConsultor({
        observation_notes: [
          { id: "1", text: "primeira", created_at: "2026-01-01T10:00:00Z" },
          { id: "2", text: "mais recente", created_at: "2026-02-01T10:00:00Z" },
        ],
      }),
    ).toBe("mais recente");
  });

  it("lê o escalar legado quando é o único que existe", () => {
    // É onde o modal do Kanban escreve. Uma listagem que o ignorasse
    // mostrava "—" a um processo com notas.
    expect(notaMaisRecenteDoConsultor({ notes: "escrita no Kanban" })).toBe(
      "escrita no Kanban",
    );
  });

  it("NÃO apresenta como do consultor o que foi lido pela IA", () => {
    // O cartão do Resumo distingue-as com um crachá; a coluna não tem
    // crachá nenhum, logo deixá-la entrar seria atribuir a uma pessoa um
    // texto que a máquina leu.
    expect(
      notaMaisRecenteDoConsultor({ ai_extracted_notes: "lido de um IRS" }),
    ).toBe("");
  });

  it("com notas de pessoa e da IA, devolve a da pessoa", () => {
    expect(
      notaMaisRecenteDoConsultor({
        observation_notes: [
          { id: "1", text: "escrita à mão", created_at: "2026-01-01T10:00:00Z" },
        ],
        ai_extracted_notes: "lido de um IRS",
      }),
    ).toBe("escrita à mão");
  });

  it("um processo sem notas devolve vazio", () => {
    expect(notaMaisRecenteDoConsultor({ id: "p-1" })).toBe("");
    expect(notaMaisRecenteDoConsultor(null)).toBe("");
  });

  it("NÃO lê atividades — o Histórico deixou de alimentar esta coluna", () => {
    // Contraprova do Ponto 9: era isto que a cascata antiga lia primeiro.
    expect(
      notaMaisRecenteDoConsultor({
        activities: [{ content: "telefonema ao banco" }],
        last_activity: { content: "telefonema ao banco" },
        latest_activity_preview: "telefonema ao banco",
      }),
    ).toBe("");
  });

  it("segue a MESMA ordem do cartão do Resumo", () => {
    // Contraprova de que não há duas ordenações: se divergirem, a coluna
    // mostra uma nota e o cartão destaca outra.
    const processo = {
      observation_notes: [
        { id: "1", text: "antiga", created_at: "2026-01-01T10:00:00Z" },
        { id: "2", text: "recente", created_at: "2026-03-01T10:00:00Z" },
      ],
    };
    const doCartao = resolveProcessObservationNotes(processo).filter(
      (n) => n.origin !== "ai",
    );
    expect(notaMaisRecenteDoConsultor(processo)).toBe(
      doCartao[doCartao.length - 1].text,
    );
  });
});
