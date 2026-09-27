/**
 * Regras do formulário de limiares de SLA.
 */
import { describe, expect, it } from "vitest";

import {
  construirPayload,
  erroDoLimiar,
  errosDoFormulario,
  hidratarLimiares,
  houveAlteracoes,
  LIMIARES_POR_OMISSAO,
} from "./slaThresholds";

describe("hidratarLimiares", () => {
  it("usa as omissões do backend quando o servidor não devolve a secção", () => {
    expect(hidratarLimiares(undefined)).toEqual({
      enabled: true,
      novo: "7",
      analise: "15",
      aprovado: "30",
    });
  });

  it("os valores ficam em TEXTO", () => {
    // Com estado numérico, apagar o campo para escrever outro valor faz
    // reaparecer um 0 a cada tecla.
    const formulario = hidratarLimiares({ novo: 10 });
    expect(formulario.novo).toBe("10");
    expect(typeof formulario.novo).toBe("string");
  });

  it("`enabled: false` sobrevive à hidratação", () => {
    // Um `base.enabled || true` transformava o desligado em ligado.
    expect(hidratarLimiares({ enabled: false }).enabled).toBe(false);
  });
});

describe("erroDoLimiar", () => {
  it("recusa vazio, decimais, negativos e texto", () => {
    expect(erroDoLimiar("")).toBeTruthy();
    expect(erroDoLimiar("  ")).toBeTruthy();
    expect(erroDoLimiar("7.5")).toBeTruthy();
    expect(erroDoLimiar("-3")).toBeTruthy();
    expect(erroDoLimiar("quinze")).toBeTruthy();
    expect(erroDoLimiar("0")).toBeTruthy();
    expect(erroDoLimiar("400")).toBeTruthy();
  });

  it("aceita um inteiro dentro dos limites", () => {
    expect(erroDoLimiar("1")).toBe("");
    expect(erroDoLimiar("15")).toBe("");
    expect(erroDoLimiar("365")).toBe("");
  });
});

describe("construirPayload", () => {
  it("devolve NÚMEROS, não as strings do formulário", () => {
    const payload = construirPayload({
      enabled: true, novo: "7", analise: "15", aprovado: "30",
    });
    expect(payload).toEqual({ enabled: true, novo: 7, analise: 15, aprovado: 30 });
  });

  it("devolve null quando algum campo está inválido", () => {
    expect(
      construirPayload({ enabled: true, novo: "", analise: "15", aprovado: "30" }),
    ).toBeNull();
  });

  it("não grava um limiar inválido só porque os outros estão bem", () => {
    // Guardar parcialmente deixava a configuração incoerente com o que o
    // utilizador vê no ecrã.
    expect(Object.keys(errosDoFormulario({ novo: "7", analise: "x", aprovado: "30" })))
      .toEqual(["analise"]);
  });
});

describe("houveAlteracoes", () => {
  it("é falso para o formulário recém-hidratado", () => {
    const config = { enabled: true, novo: 7, analise: 15, aprovado: 30 };
    expect(houveAlteracoes(hidratarLimiares(config), config)).toBe(false);
  });

  it("apanha a mudança de um número e a do interruptor", () => {
    const config = LIMIARES_POR_OMISSAO;
    expect(houveAlteracoes({ ...hidratarLimiares(config), novo: "9" }, config)).toBe(true);
    expect(houveAlteracoes({ ...hidratarLimiares(config), enabled: false }, config)).toBe(true);
  });
});
