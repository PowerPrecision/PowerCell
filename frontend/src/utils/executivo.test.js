import { describe, expect, it } from "vitest";

import {
  PAPEIS_FILTRAVEIS,
  dadosDoGraficoDePessoas,
  intervaloDaPredefinicao,
  lerData,
  listaOuVazia,
  nomeDoFicheiro,
  parametrosDoRelatorio,
  pontuacao,
  rotuloDaSemana,
  segundaDaSemana,
  taxaDeConclusao,
  validarIntervalo,
  valorOuTraco,
} from "./executivo";

const SEXTA = new Date("2026-10-09T23:30:00Z"); // sexta-feira

describe("intervaloDaPredefinicao", () => {
  it.each([
    ["this_week", "2026-10-05", "2026-10-09"],
    ["last_week", "2026-09-28", "2026-10-04"],
    ["this_month", "2026-10-01", "2026-10-09"],
    ["last_month", "2026-09-01", "2026-09-30"],
    ["7d", "2026-10-03", "2026-10-09"],
    ["14d", "2026-09-26", "2026-10-09"],
    ["30d", "2026-09-10", "2026-10-09"],
    ["90d", "2026-07-12", "2026-10-09"],
  ])("%s", (chave, inicio, fim) => {
    expect(intervaloDaPredefinicao(chave, SEXTA)).toEqual({ inicio, fim });
  });

  it("«últimos 7 dias» são 7 dias, contando hoje", () => {
    const { inicio, fim } = intervaloDaPredefinicao("7d", SEXTA);
    expect((lerData(fim) - lerData(inicio)) / 86_400_000 + 1).toBe(7);
  });

  it("o mês passado de janeiro é dezembro do ano anterior", () => {
    expect(intervaloDaPredefinicao("last_month", new Date("2026-01-15T00:00:00Z"))).toEqual({
      inicio: "2025-12-01", fim: "2025-12-31",
    });
  });

  it("custom e desconhecida não têm intervalo", () => {
    expect(intervaloDaPredefinicao("custom", SEXTA)).toBeNull();
    expect(intervaloDaPredefinicao("xpto", SEXTA)).toBeNull();
  });

  it("a hora do dia não desloca o dia (UTC)", () => {
    expect(intervaloDaPredefinicao("7d", new Date("2026-10-09T00:00:01Z")).fim).toBe("2026-10-09");
  });
});

describe("segundaDaSemana", () => {
  it.each([["2026-10-05", "2026-10-05"], ["2026-10-11", "2026-10-05"], ["2026-10-09", "2026-10-05"]])(
    "%s → %s", (dia, segunda) => {
      expect(segundaDaSemana(lerData(dia)).toISOString().slice(0, 10)).toBe(segunda);
    });
});

describe("validarIntervalo", () => {
  it("aceita um intervalo bom e um só dia", () => {
    expect(validarIntervalo("2026-10-01", "2026-10-09")).toBeNull();
    expect(validarIntervalo("2026-10-09", "2026-10-09")).toBeNull();
  });
  it.each([["", "2026-10-09"], ["2026-10-01", ""], ["2026-13-01", "2026-10-09"], ["01/10/2026", "2026-10-09"]])(
    "datas inválidas (%s, %s)", (a, b) => {
      expect(validarIntervalo(a, b)).toMatch(/duas datas/);
    });
  it("início depois do fim", () => {
    expect(validarIntervalo("2026-10-10", "2026-10-09")).toMatch(/anterior/);
  });
  it("tecto de 366 dias, como o servidor", () => {
    expect(validarIntervalo("2025-10-09", "2026-10-09")).toBeNull();
    expect(validarIntervalo("2025-10-08", "2026-10-09")).toMatch(/366/);
  });
  it("29 de Fevereiro inexistente não passa por 1 de Março", () => {
    expect(lerData("2026-02-29")).toBeNull();
    expect(lerData("2028-02-29")).not.toBeNull();
  });
});

describe("parametrosDoRelatorio", () => {
  it("sem filtros só leva o período", () => {
    expect(parametrosDoRelatorio({ inicio: "a", fim: "b" })).toEqual({ start_date: "a", end_date: "b" });
  });
  it("junta, ordena e limpa os filtros", () => {
    expect(parametrosDoRelatorio({
      inicio: "a", fim: "b", utilizadores: ["u2", " u1 ", "u2", "", null], papeis: ["diretor", "consultor"],
    })).toEqual({ start_date: "a", end_date: "b", user_ids: "u1,u2", roles: "consultor,diretor" });
  });
  it("formas inesperadas não rebentam", () => {
    expect(parametrosDoRelatorio({ inicio: "a", fim: "b", utilizadores: "x", papeis: {} })).toEqual({
      start_date: "a", end_date: "b",
    });
    expect(parametrosDoRelatorio()).toEqual({ start_date: undefined, end_date: undefined });
  });
});

describe("os números", () => {
  it("o histórico desligado é traço e nunca zero", () => {
    expect(valorOuTraco(null)).toBe("—");
    expect(valorOuTraco(undefined)).toBe("—");
    expect(valorOuTraco(0)).toBe("0");
    expect(valorOuTraco(7)).toBe("7");
  });
  it("pontuação trata null como 0 sem dar NaN", () => {
    expect(pontuacao({ processes_moved: null, tasks_completed: 3 })).toBe(3);
    expect(pontuacao({ processes_moved: 2, tasks_completed: 3 })).toBe(5);
    expect(pontuacao(null)).toBe(0);
  });
  it("taxa de conclusão: sem tarefas não é 0 %", () => {
    expect(taxaDeConclusao({ tasks_completed: 0, tasks_pending: 0 })).toBeNull();
    expect(taxaDeConclusao({ tasks_completed: 3, tasks_pending: 1 })).toBe(75);
    expect(taxaDeConclusao({ tasks_completed: 0, tasks_pending: 2 })).toBe(0);
  });
  it("as tarefas em atraso são pendentes, não somam ao denominador", () => {
    // Antes: concluídas + atrasadas + pendentes contava o atraso DUAS vezes.
    expect(taxaDeConclusao({ tasks_completed: 1, tasks_pending: 3, tasks_overdue: 3 })).toBe(25);
  });
  it("listaOuVazia usa Array.isArray", () => {
    expect(listaOuVazia({})).toEqual([]);
    expect(listaOuVazia("x")).toEqual([]);
    expect(listaOuVazia([1])).toEqual([1]);
  });
});

describe("gráfico, ficheiro e semana", () => {
  it("o gráfico usa o primeiro nome e zeros para o traço", () => {
    expect(dadosDoGraficoDePessoas([{ name: "Ana Silva", phase_changes: null, tasks_completed: 2, tasks_overdue: 1 }])).toEqual([
      { nome: "Ana", nomeCompleto: "Ana Silva", "Fases alteradas": 0, "Tarefas concluídas": 2, "Em atraso": 1 },
    ]);
    expect(dadosDoGraficoDePessoas(undefined)).toEqual([]);
  });
  it("lê o nome do Content-Disposition ou usa o recuo", () => {
    expect(nomeDoFicheiro({ "content-disposition": 'attachment; filename="r_2026.pdf"' }, "x.pdf")).toBe("r_2026.pdf");
    expect(nomeDoFicheiro({}, "x.pdf")).toBe("x.pdf");
    expect(nomeDoFicheiro(undefined, "x.pdf")).toBe("x.pdf");
  });
  it("rótulo da semana", () => {
    expect(rotuloDaSemana({ week_start: "2026-10-05", week_end: "2026-10-11" })).toBe("05/10 – 11/10");
    expect(rotuloDaSemana(null)).toBe("");
  });
  it("a Indexação não é um perfil filtrável", () => {
    expect(PAPEIS_FILTRAVEIS).not.toContain("indexacao");
  });
});
