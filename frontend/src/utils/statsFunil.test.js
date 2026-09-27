import { describe, it, expect } from "vitest";

import {
  avisosDaAmostra,
  barrasDeValor,
  barrasDoFunil,
  fatiasDePrioridade,
  linhasDeSla,
  linhasForaDoFunil,
} from "./statsFunil";

/**
 * O funil e os SLAs são APRESENTAÇÃO: a agregação vem do servidor.
 *
 * Estes testes defendem duas coisas: que a ordem e os números do servidor
 * são respeitados sem recálculo, e que um payload em falta dá um gráfico
 * vazio em vez de uma página em branco.
 */

const funil = {
  etapas: [
    { macro_fase: "novo", label: "Novo", processos: 10, alcancaram: 37, conversao_para_seguinte: 73.0, valor_imovel: 1_500_000 },
    { macro_fase: "analise", label: "Análise", processos: 20, alcancaram: 27, conversao_para_seguinte: 25.9, valor_imovel: 3_200_000 },
    { macro_fase: "aprovado", label: "Aprovado", processos: 5, alcancaram: 7, conversao_para_seguinte: 28.6, valor_imovel: 900_000 },
    { macro_fase: "concluido", label: "Concluído", processos: 2, alcancaram: 2, conversao_para_seguinte: null, valor_imovel: 400_000 },
  ],
  perdidos: { macro_fase: "perdido", label: "Perdido", processos: 8 },
  desconhecidos: { macro_fase: "__desconhecidas__", label: "Fases desconhecidas", processos: 3 },
  total_processos: 48,
  por_prioridade: { alta: 4, media: 0, baixa: 7, sem: 37 },
  macro_fases_sem_classificacao: ["renegociacao"],
};

const sla = {
  macro_fases: [
    {
      macro_fase: "analise",
      limiar_dias: 15,
      em_curso: 20,
      acima_do_limiar: 6,
      dias_medios_em_curso: 18.4,
      banda_mediana_em_curso: "8-15",
      dias_medios_historico: 12.5,
      amostra_historico: 37,
      bandas: [
        { banda: "0-7", processos: 4 },
        { banda: "8-15", processos: 10 },
        { banda: "61+", processos: 6 },
      ],
    },
  ],
  bandas: ["0-7", "8-15", "16-30", "31-60", "61+"],
  excluidos_da_amostra: ["nunca_tocado", "tocado_apos_fecho"],
};

describe("barrasDoFunil", () => {
  it("respeita a ordem que o servidor mandou", () => {
    // Reordenar aqui era duplicar a regra do funil em dois sítios.
    expect(barrasDoFunil(funil).map((b) => b.key)).toEqual([
      "novo",
      "analise",
      "aprovado",
      "concluido",
    ]);
  });

  it("leva as contagens e a conversão sem as recalcular", () => {
    const analise = barrasDoFunil(funil)[1];
    expect(analise.processos).toBe(20);
    expect(analise.alcancaram).toBe(27);
    expect(analise.conversao).toBe(25.9);
  });

  it("um payload em falta dá um gráfico vazio", () => {
    expect(barrasDoFunil(null)).toEqual([]);
    expect(barrasDoFunil({})).toEqual([]);
  });
});

describe("barrasDeValor", () => {
  it("converte para milhares", () => {
    expect(barrasDeValor(funil)[0].valor).toBe(1500);
  });

  it("aceita outro campo de valor", () => {
    const com = { etapas: [{ macro_fase: "novo", label: "Novo", valor_financiado: 250_000 }] };
    expect(barrasDeValor(com, "valor_financiado")[0].valor).toBe(250);
  });

  it("um valor ausente vale zero e não NaN", () => {
    const sem = { etapas: [{ macro_fase: "novo", label: "Novo" }] };
    expect(barrasDeValor(sem)[0].valor).toBe(0);
  });
});

describe("linhasForaDoFunil", () => {
  it("mostra os perdidos e a reconciliação", () => {
    // Esconder qualquer uma fazia a soma das barras não dar o total sem
    // nada no ecrã a dizê-lo.
    expect(linhasForaDoFunil(funil).map((l) => l.key)).toEqual([
      "perdido",
      "__desconhecidas__",
    ]);
  });

  it("omite as que estão a zero", () => {
    const limpo = {
      perdidos: { macro_fase: "perdido", label: "Perdido", processos: 0 },
      desconhecidos: { macro_fase: "__desconhecidas__", label: "X", processos: 0 },
    };
    expect(linhasForaDoFunil(limpo)).toEqual([]);
  });

  it("a soma das barras mais as linhas de fora é o total", () => {
    const barras = barrasDoFunil(funil).reduce((s, b) => s + b.processos, 0);
    const fora = linhasForaDoFunil(funil).reduce((s, l) => s + l.processos, 0);
    expect(barras + fora).toBe(funil.total_processos);
  });
});

describe("fatiasDePrioridade", () => {
  it("traduz as chaves do servidor", () => {
    expect(fatiasDePrioridade(funil).map((f) => f.name)).toEqual([
      "Alta",
      "Baixa",
      "Sem prioridade",
    ]);
  });

  it("omite as fatias vazias", () => {
    expect(fatiasDePrioridade(funil).find((f) => f.key === "media")).toBeUndefined();
  });

  it("sem prioridades não rebenta", () => {
    expect(fatiasDePrioridade({})).toEqual([]);
  });
});

describe("linhasDeSla", () => {
  it("usa o `acima_do_limiar` do servidor e não o recalcula", () => {
    // Recalcular obrigava a UI a saber o limiar e a regra das bandas —
    // duas verdades sobre o mesmo número.
    expect(linhasDeSla(sla)[0].emRisco).toBe(6);
    expect(linhasDeSla(sla)[0].limiarDias).toBe(15);
  });

  it("leva a mediana ao lado da média", () => {
    const linha = linhasDeSla(sla)[0];
    expect(linha.diasMedios).toBe(18.4);
    expect(linha.bandaMediana).toBe("8-15");
  });

  it("leva a amostra do histórico", () => {
    expect(linhasDeSla(sla)[0].amostraHistorico).toBe(37);
  });

  it("sem SLAs devolve lista vazia", () => {
    expect(linhasDeSla(undefined)).toEqual([]);
  });
});

describe("avisosDaAmostra", () => {
  it("avisa das fases sem grupo atribuído", () => {
    const avisos = avisosDaAmostra(funil, sla);
    expect(avisos.some((a) => a.includes("renegociacao"))).toBe(true);
  });

  it("avisa que as médias excluem estimativas aberrantes", () => {
    const avisos = avisosDaAmostra(funil, sla);
    expect(avisos.some((a) => a.includes("estimativa"))).toBe(true);
  });

  it("avisa quando ainda não há histórico medido", () => {
    const semHistorico = {
      macro_fases: [{ macro_fase: "analise", amostra_historico: 0 }],
    };
    const avisos = avisosDaAmostra(funil, semHistorico);
    expect(avisos.some((a) => a.includes("de agora em diante"))).toBe(true);
  });

  it("não avisa do histórico quando ele existe", () => {
    const avisos = avisosDaAmostra({}, sla);
    expect(avisos.some((a) => a.includes("de agora em diante"))).toBe(false);
  });

  it("sem nada a avisar devolve lista vazia", () => {
    expect(avisosDaAmostra({}, {})).toEqual([]);
  });
});
