import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import {
  estadoDaValidacao,
  estaPorValidar,
  motivoDaRejeicao,
  podeDecidir,
  validarMotivo,
} from "./validacaoFinanceira";

describe("estado", () => {
  it("lê o estado de um objecto ou de uma string (listas)", () => {
    expect(estadoDaValidacao({ validacao_financeira: { estado: "pendente" } })).toBe("pendente");
    expect(estadoDaValidacao({ validacao_financeira: "validado" })).toBe("validado");
  });

  it.each([undefined, null, {}, { validacao_financeira: 1 }, { validacao_financeira: { estado: "x" } }])(
    "sem validação reconhecida = null (%j)",
    (registo) => expect(estadoDaValidacao(registo)).toBeNull()
  );

  it("por validar: pendente e rejeitado; nunca validado nem sem validação", () => {
    expect(estaPorValidar({ validacao_financeira: { estado: "pendente" } })).toBe(true);
    expect(estaPorValidar({ validacao_financeira: { estado: "rejeitado" } })).toBe(true);
    expect(estaPorValidar({ validacao_financeira: { estado: "validado" } })).toBe(false);
    expect(estaPorValidar({})).toBe(false);
  });

  it("o motivo vem aparado", () => {
    expect(motivoDaRejeicao({ validacao_financeira: { estado: "rejeitado", motivo: "  x  " } })).toBe("x");
    expect(motivoDaRejeicao({})).toBe("");
  });
});

describe("quem decide", () => {
  it.each(["ceo", "diretor", "administrativo", "CEO", "Diretor"])("%s decide", (p) => expect(podeDecidir(p)).toBe(true));
  it.each(["admin", "master", "consultor", "intermediario", "indexacao", "parceiro", "", null, undefined])(
    "%s não decide",
    (p) => expect(podeDecidir(p)).toBe(false)
  );
});

describe("o motivo", () => {
  it("é obrigatório, com mínimo e máximo", () => {
    expect(validarMotivo("")).not.toBe("");
    expect(validarMotivo("  ab ")).not.toBe("");
    expect(validarMotivo("abc")).toBe("");
    expect(validarMotivo("x".repeat(501))).not.toBe("");
  });
});

/**
 * A decisão de produto: um processo não validado trabalha-se até ao fim. Se um
 * ecrã passar a ler a validação para desactivar um botão, é um travão — e um
 * travão exige uma decisão, não um efeito lateral.
 */
describe("a validação financeira nunca bloqueia o ecrã", () => {
  const PERMITIDOS = new Set([
    "components/validacao/ValidacaoFinanceira.jsx",
    "components/validacao/ValidacaoFinanceira.test.jsx",
    "utils/validacaoFinanceira.js",
    "utils/validacaoFinanceira.test.js",
    "pages/ProcessDetails.js", // monta o selo
    "pages/ClientRegistrationsPage.js", // monta o selo compacto na lista
  ]);

  const ficheiros = (pasta, acumulado = []) => {
    for (const nome of readdirSync(pasta)) {
      const caminho = join(pasta, nome);
      if (statSync(caminho).isDirectory()) {
        if (nome !== "node_modules" && nome !== "fixtures") ficheiros(caminho, acumulado);
      } else if (/\.(jsx?|mjs)$/.test(nome)) {
        acumulado.push(caminho);
      }
    }
    return acumulado;
  };

  it("só o selo e as duas páginas que o montam referem o campo", () => {
    const raiz = join(process.cwd(), "src");
    const refere = ficheiros(raiz)
      .filter((f) => !/__tests__|\.test\./.test(f) || f.includes("validacao"))
      .filter((f) => readFileSync(f, "utf8").includes("validacao_financeira"))
      .map((f) => f.slice(raiz.length + 1).replaceAll("\\", "/"));
    const fora = refere.filter((f) => !PERMITIDOS.has(f));
    expect(fora).toEqual([]);
    expect(refere.length).toBeGreaterThanOrEqual(3); // o leitor lê mesmo (contraprova)
  });

  it("nas páginas que montam o selo, o campo nunca aparece perto de `disabled`", () => {
    for (const rel of ["pages/ProcessDetails.js", "pages/ClientRegistrationsPage.js"]) {
      const linhas = readFileSync(join(process.cwd(), "src", rel), "utf8").split("\n");
      linhas.forEach((linha, i) => {
        if (!linha.includes("validacao_financeira")) return;
        const vizinhas = linhas.slice(Math.max(0, i - 2), i + 3).join("\n");
        expect(vizinhas, `${rel}:${i + 1}`).not.toMatch(/disabled|readOnly/);
      });
    }
  });
});
