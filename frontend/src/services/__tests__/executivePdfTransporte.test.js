/**
 * O que SAI para o servidor: um nível abaixo dos testes das páginas (que
 * falseiam estas funções). Sem este, trocar o nome do parâmetro ou ligar a
 * análise sempre não tinha teste a morder — e a análise de IA é uma chamada
 * paga que só pode acontecer quando a pessoa a pediu.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import api, { downloadExecutiveWeeklyPdf, downloadTeamPerformancePdf } from "../api";

afterEach(() => vi.restoreAllMocks());

function espiar() {
  return vi.spyOn(api, "get").mockResolvedValue({ data: new Blob(["%PDF-"]), headers: {} });
}

describe("downloadTeamPerformancePdf", () => {
  it("por omissão NÃO pede a análise de IA e preserva os filtros do ecrã", async () => {
    const get = espiar();
    await downloadTeamPerformancePdf({ start_date: "2026-10-05", user_ids: "u1" });
    const [url, opcoes] = get.mock.calls[0];
    expect(url).toBe("/admin/team-performance/pdf");
    expect(opcoes.params).toEqual({ start_date: "2026-10-05", user_ids: "u1" });
    expect(opcoes.params).not.toHaveProperty("ai_analysis");
    expect(opcoes.responseType).toBe("blob");
  });

  it("com a opção, acrescenta ai_analysis=true sem perder os filtros", async () => {
    const get = espiar();
    await downloadTeamPerformancePdf({ start_date: "2026-10-05" }, { analiseIA: true });
    expect(get.mock.calls[0][1].params).toEqual({ start_date: "2026-10-05", ai_analysis: true });
  });

  it("analiseIA=false explícito também não a pede", async () => {
    const get = espiar();
    await downloadTeamPerformancePdf({}, { analiseIA: false });
    expect(get.mock.calls[0][1].params).not.toHaveProperty("ai_analysis");
  });
});

describe("downloadExecutiveWeeklyPdf", () => {
  it("por omissão só leva a semana", async () => {
    const get = espiar();
    await downloadExecutiveWeeklyPdf("2026-10-05");
    const [url, opcoes] = get.mock.calls[0];
    expect(url).toBe("/admin/executive-weekly/pdf");
    expect(opcoes.params).toEqual({ week: "2026-10-05" });
  });

  it("sem semana e sem opção, nenhum parâmetro", async () => {
    const get = espiar();
    await downloadExecutiveWeeklyPdf(undefined);
    expect(get.mock.calls[0][1].params).toEqual({});
  });

  it("com a opção leva a semana E ai_analysis=true", async () => {
    const get = espiar();
    await downloadExecutiveWeeklyPdf("2026-10-05", { analiseIA: true });
    expect(get.mock.calls[0][1].params).toEqual({ week: "2026-10-05", ai_analysis: true });
  });

  it("com a opção e sem semana leva só ai_analysis", async () => {
    const get = espiar();
    await downloadExecutiveWeeklyPdf(undefined, { analiseIA: true });
    expect(get.mock.calls[0][1].params).toEqual({ ai_analysis: true });
  });
});
